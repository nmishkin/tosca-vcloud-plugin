import mock
import unittest

from cloudify import exceptions as cfy_exc
import test_mock_base
import network_plugin
import vcloud_plugin_common


class NetworkPluginMockTestCase(test_mock_base.TestBase):

    def test_get_vm_ip(self):
        """
            check get vm ip from conected networks
        """
        fake_client = self.generate_client(vms_networks=[])
        fake_ctx = self.generate_relation_context()
        fake_ctx._source.node.properties = {
            'vcloud_config': {
                'edge_gateway': 'some_edge_gateway',
                'vdc': 'vdc_name'
            }
        }
        # empty connections/no connection name
        with mock.patch('vcloud_plugin_common.ctx', fake_ctx):
            with self.assertRaises(cfy_exc.NonRecoverableError):
                network_plugin.get_vm_ip(
                    fake_client, fake_ctx, fake_client._vdc_gateway
                )
        vms_networks = [{
            'is_connected': True,
            'network_name': 'network_name',
            'is_primary': True,
            'ip': '1.1.1.1'
        }]
        fake_client = self.generate_client(vms_networks=vms_networks)
        # not routed
        with mock.patch('vcloud_plugin_common.ctx', fake_ctx):
            with self.assertRaises(cfy_exc.NonRecoverableError):
                network_plugin.get_vm_ip(
                    fake_client, fake_ctx, fake_client._vdc_gateway
                )
        # routed
        self.set_network_routed_in_client(fake_client)
        with mock.patch('vcloud_plugin_common.ctx', fake_ctx):
            self.assertEqual(
                network_plugin.get_vm_ip(
                    fake_client, fake_ctx, fake_client._vdc_gateway
                ),
                '1.1.1.1'
            )
        # TODO add negative tests

    def test_collectAssignedIps(self):
        # empty gateway
        self.assertEqual(
            network_plugin.collectAssignedIps(None),
            set([])
        )
        # snat
        gateway = self.generate_gateway()
        rule_inlist = self.generate_nat_rule(
            'SNAT', 'external', 'any', 'internal', '11', 'TCP'
        )
        gateway.get_nat_rules = mock.MagicMock(
            return_value=[rule_inlist]
        )
        self.assertEqual(
            network_plugin.collectAssignedIps(gateway),
            set(
                [network_plugin.AssignedIPs(
                    external='internal', internal='external'
                )]
            )
        )
        # dnat
        gateway = self.generate_gateway()
        rule_inlist = self.generate_nat_rule(
            'DNAT', 'external', 'any', 'internal', '11', 'TCP'
        )
        gateway.get_nat_rules = mock.MagicMock(return_value=[
            rule_inlist
        ])
        self.assertEqual(
            network_plugin.collectAssignedIps(gateway),
            set(
                [network_plugin.AssignedIPs(
                    external='external', internal='internal'
                )]
            )
        )

    def test_getFreeIP(self):
        # exist free ip
        gateway = self.generate_gateway()
        gateway.get_public_ips = mock.MagicMock(return_value=[
            '10.18.1.1', '10.18.1.2'
        ])
        rule_inlist = self.generate_nat_rule(
            'DNAT', '10.18.1.1', 'any', 'internal', '11', 'TCP'
        )
        gateway.get_nat_rules = mock.MagicMock(return_value=[rule_inlist])
        self.assertEqual(
            network_plugin.getFreeIP(gateway),
            '10.18.1.2'
        )
        # no free ips
        gateway.get_public_ips = mock.MagicMock(return_value=[
            '10.18.1.1'
        ])
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.getFreeIP(gateway)

    def test_del_ondemand_public_ip(self):
        vca_client = self.generate_client()
        gateway = self.generate_gateway()
        fake_ctx = self.generate_node_context()
        # cant deallocate ip
        gateway.deallocate_public_ip = mock.MagicMock(return_value=None)
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.del_ondemand_public_ip(
                vca_client, gateway, '127.0.0.1', fake_ctx
            )
        gateway.deallocate_public_ip.assert_called_with('127.0.0.1')
        # successfully dropped public ip
        gateway.deallocate_public_ip = mock.MagicMock(
            return_value=self.generate_task(
                vcloud_plugin_common.TASK_STATUS_SUCCESS
            )
        )
        network_plugin.del_ondemand_public_ip(
            vca_client, gateway, '127.0.0.1', fake_ctx
        )

    def test_save_gateway_configuration(self):
        gateway = self.generate_gateway()
        vca_client = self.generate_client()
        # cant save configuration - error in first call
        self.set_services_conf_result(
            gateway, None
        )
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.save_gateway_configuration(
                gateway, vca_client
            )
        # error in status
        self.set_services_conf_result(
            gateway, vcloud_plugin_common.TASK_STATUS_ERROR
        )
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.save_gateway_configuration(
                gateway, vca_client
            )
        # everything fine
        self.set_services_conf_result(
            gateway, vcloud_plugin_common.TASK_STATUS_SUCCESS
        )
        self.assertTrue(
            network_plugin.save_gateway_configuration(
                gateway, vca_client
            )
        )
        # server busy
        self.set_services_conf_result(
            gateway, None
        )
        self.set_gateway_busy(gateway)
        self.assertFalse(
            network_plugin.save_gateway_configuration(
                gateway, vca_client
            )
        )

    def test_is_network_routed(self):
        fake_client = self.generate_client(
            vms_networks=[{
                'is_connected': True,
                'network_name': 'network_name',
                'is_primary': True,
                'ip': '1.1.1.1'
            }]
        )
        fake_ctx = self.generate_node_context()
        with mock.patch('vcloud_plugin_common.ctx', fake_ctx):
            # not routed by nat
            network = self.gen_vca_client_network("not_routed")
            fake_client.get_network = mock.MagicMock(return_value=network)
            self.assertFalse(
                network_plugin.is_network_routed(
                    fake_client, 'network_name',
                    fake_client._vdc_gateway
                )
            )
            # nat routed
            self.set_network_routed_in_client(fake_client)
            self.assertTrue(
                network_plugin.is_network_routed(
                    fake_client, 'network_name',
                    fake_client._vdc_gateway
                )
            )
            # nat routed but for other network
            self.assertFalse(
                network_plugin.is_network_routed(
                    fake_client, 'other_network_name',
                    fake_client._vdc_gateway
                )
            )

    def test_get_vapp_name(self):
        """
            check get vapp name
        """
        self.assertEqual(
            network_plugin.get_vapp_name({
                network_plugin.VCLOUD_VAPP_NAME: "name"
            }),
            "name"
        )
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.get_vapp_name({
                "aa": "aaa"
            })

    def test_check_port(self):
        """
            check port
        """
        # port int
        network_plugin.check_port(10)
        # port int to big
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.check_port(65536)
        # port any
        network_plugin.check_port('any')
        # port not any and not int
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.check_port('some')

    def test_CheckAssignedExternalIp(self):
        gateway = self.generate_gateway()
        gateway.get_public_ips = mock.MagicMock(return_value=[
            '10.1.1.1', '10.1.1.2'
        ])
        rule_inlist = self.generate_nat_rule(
            'DNAT', '10.1.1.1', 'any', '123.1.1.1', '11', 'TCP'
        )
        gateway.get_nat_rules = mock.MagicMock(
            return_value=[rule_inlist]
        )
        # free ip
        network_plugin.CheckAssignedExternalIp(
            '10.10.1.2', gateway
        )
        # assigned ip
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.CheckAssignedExternalIp(
                '10.1.1.1', gateway
            )

    def test_CheckAssignedInternalIp(self):
        gateway = self.generate_gateway()
        gateway.get_public_ips = mock.MagicMock(return_value=[
            '10.1.1.1', '10.1.1.2'
        ])
        rule_inlist = self.generate_nat_rule(
            'DNAT', '10.1.1.1', 'any', '123.1.1.1', '11', 'TCP'
        )
        gateway.get_nat_rules = mock.MagicMock(
            return_value=[rule_inlist]
        )
        # free ip
        network_plugin.CheckAssignedInternalIp(
            '123.1.1.2', gateway
        )
        # assigned ip
        with self.assertRaises(cfy_exc.NonRecoverableError):
            network_plugin.CheckAssignedInternalIp(
                '123.1.1.1', gateway
            )

    def test_get_public_ip(self):
        gateway = self.generate_gateway()
        gateway.get_public_ips = mock.MagicMock(return_value=[
            '10.18.1.1', '10.18.1.2'
        ])
        rule_inlist = self.generate_nat_rule(
            'DNAT', '10.18.1.1', 'any', 'internal', '11', 'TCP'
        )
        gateway.get_nat_rules = mock.MagicMock(
            return_value=[rule_inlist]
        )
        fake_ctx = self.generate_node_context()
        # for subscription we dont use client
        self.assertEqual(
            network_plugin.get_public_ip(
                None, gateway,
                vcloud_plugin_common.SUBSCRIPTION_SERVICE_TYPE, fake_ctx
            ),
            '10.18.1.2'
        )
        #TODO add ondemand test

if __name__ == '__main__':
    unittest.main()
