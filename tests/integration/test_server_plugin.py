import mock
import socket
import time
import unittest

from cloudify import mocks as cfy_mocks

from network_plugin.network import VCLOUD_NETWORK_NAME
from server_plugin import server

from tests.integration import TestCase, IntegrationTestConfig


class ServerNoNetworkTestCase(TestCase):

    def setUp(self):
        super(ServerNoNetworkTestCase, self).setUp()

        server_test_dict = IntegrationTestConfig().get()['server']
        name = self.name_prefix + 'server'

        self.ctx = cfy_mocks.MockCloudifyContext(
            node_id=name,
            node_name=name,
            properties={
                'server':
                {
                    'name': name,
                    'catalog': server_test_dict['catalog'],
                    'template': server_test_dict['template']
                }
            }
        )
        self.ctx.instance.relationships = []
        ctx_patch1 = mock.patch('server_plugin.server.ctx', self.ctx)
        ctx_patch2 = mock.patch('vcloud_plugin_common.ctx', self.ctx)
        ctx_patch1.start()
        ctx_patch2.start()
        self.addCleanup(ctx_patch1.stop)
        self.addCleanup(ctx_patch2.stop)

    def tearDown(self):
        try:
            server.stop()
            server.delete()
        except Exception:
            pass
        super(ServerNoNetworkTestCase, self).tearDown()

    def test_server_create_delete(self):
        server.create()
        vapp = self.vcd_client.get_vApp(
            self.ctx.node.properties['server']['name'])
        self.assertFalse(vapp is None)
        self.assertTrue(server._vm_is_on(vapp))

        server.stop()
        vapp = self.vcd_client.get_vApp(
            self.ctx.node.properties['server']['name'])
        self.assertFalse(server._vm_is_on(vapp))

        server.delete()
        vapp = self.vcd_client.get_vApp(
            self.ctx.node.properties['server']['name'])
        self.assertTrue(vapp is None)

    def test_server_stop_start(self):
        server.create()
        vapp = self.vcd_client.get_vApp(
            self.ctx.node.properties['server']['name'])
        self.assertFalse(vapp is None)
        self.assertTrue(server._vm_is_on(vapp))

        server.stop()
        vapp = self.vcd_client.get_vApp(
            self.ctx.node.properties['server']['name'])
        self.assertFalse(server._vm_is_on(vapp))

        server.start()
        vapp = self.vcd_client.get_vApp(
            self.ctx.node.properties['server']['name'])
        self.assertTrue(server._vm_is_on(vapp))


class ServerWithNetworkTestCase(TestCase):

    def setUp(self):
        super(ServerWithNetworkTestCase, self).setUp()

        server_test_dict = IntegrationTestConfig().get()['server']
        name = self.name_prefix + 'server'
        self.network_name = server_test_dict['network']

        network_runtime_properties = {VCLOUD_NETWORK_NAME: self.network_name}
        network_instance_context = cfy_mocks.MockNodeInstanceContext(
            runtime_properties=network_runtime_properties)
        network_node_context = cfy_mocks.MockNodeContext(
            properties={'management': True})

        network_relationship = mock.Mock()
        network_relationship.target = mock.Mock()
        network_relationship.target.instance = network_instance_context
        network_relationship.target.node = network_node_context

        self.ctx = cfy_mocks.MockCloudifyContext(
            node_id=name,
            node_name=name,
            properties={
                'server':
                {
                    'name': name,
                    'catalog': server_test_dict['catalog'],
                    'template': server_test_dict['template']
                }
            }
        )
        self.ctx.instance.relationships = [network_relationship]
        ctx_patch1 = mock.patch('server_plugin.server.ctx', self.ctx)
        ctx_patch2 = mock.patch('vcloud_plugin_common.ctx', self.ctx)
        ctx_patch1.start()
        ctx_patch2.start()
        self.addCleanup(ctx_patch1.stop)
        self.addCleanup(ctx_patch2.stop)

    def tearDown(self):
        try:
            server.stop()
            server.delete()
        except Exception:
            pass
        super(ServerWithNetworkTestCase, self).tearDown()

    def test_create(self):
        server.create()
        server.start()
        vapp = self.vcd_client.get_vApp(
            self.ctx.node.properties['server']['name'])
        self.assertFalse(vapp is None)
        networks = server._get_vm_network_connections(vapp)
        self.assertEqual(1, len(networks))
        self.assertEqual(self.network_name, networks[0]['network_name'])

    def test_get_state(self):
        num_tries = 5
        verified = False
        server.create()
        server.start()
        for _ in range(num_tries):
            result = server.get_state()
            if result is True:
                self.assertTrue('ip' in self.ctx.instance.runtime_properties)
                self.assertTrue('networks'
                                in self.ctx.instance.runtime_properties)
                self.assertEqual(1,
                                len(self.ctx.instance.\
                                    runtime_properties['networks'].keys()))
                self.assertEqual(self.network_name,
                                 self.ctx.instance.\
                                    runtime_properties['networks'].keys()[0])
                ip_valid = True
                try:
                    socket.inet_aton(
                        self.ctx.instance.runtime_properties['ip'])
                except socket.error:
                    ip_valid = False
                self.assertTrue(ip_valid)
                verified = True
                break
            time.sleep(2)
        self.assertTrue(verified)

if __name__ == '__main__':
    unittest.main()