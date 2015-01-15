from cloudify import ctx
from cloudify import exceptions as cfy_exc
from cloudify.decorators import operation
from vcloud_plugin_common import with_vcd_client, wait_for_task
from network_plugin import check_ip, collectExternalIps
from server_plugin import VAppOperations
from server_plugin.server import VCLOUD_VAPP_NAME

CREATE = 1
DELETE = 2
PUBLIC_IP = 'public_ip'


@operation
@with_vcd_client
def connect_floatingip(vcd_client, **kwargs):
    _floatingip_operation(CREATE, vcd_client, ctx)


@operation
@with_vcd_client
def disconnect_floatingip(vcd_client, **kwargs):
    _floatingip_operation(DELETE, vcd_client, ctx)


def _floatingip_operation(operation, vcd_client, ctx):
    def isExternalIpExsists():
        return external_ip in collectExternalIps(gateway)

    def showMessage(message):
        ctx.logger.info(message.format(external_ip))

    gateway = vcd_client.get_gateway(
        ctx.node.properties['floatingip']['gateway'])
    if not gateway:
        raise cfy_exc.NonRecoverableError("Gateway not found")

    external_ip = check_ip(
        ctx.node.properties['floatingip']['public_ip'])
    internal_ip = check_ip(_get_vm_ip(vcd_client, ctx))

    function = None
    description = None

    if operation == CREATE:
        if isExternalIpExsists():
            showMessage("Rule with IP: {0} already exists")
            return
        function = gateway.add_nat_rule
        description = "create"
    elif operation == DELETE:
        if not isExternalIpExsists():
            showMessage("Rule with IP: {0} absent")
            return
        function = gateway.del_nat_rule
        description = "delete"
    else:
        raise cfy_exc.NonRecoverableError(
            "Unknown operation {0}").format(operation)

    _nat_operation(function, description, vcd_client, "SNAT",
                   internal_ip, external_ip)
    _nat_operation(function, description, vcd_client, "DNAT",
                   external_ip, internal_ip)

    if operation == CREATE:
        ctx.instance.runtime_properties[PUBLIC_IP] = external_ip
    else:
        del ctx.instance.runtime_properties[PUBLIC_IP]


def _nat_operation(function, description, vcd_client,
                   rule_type, original_ip, translated_ip):
    any_type = None

    if rule_type == "DNAT":
        any_type = "Any"

    ctx.logger.info("{0} floating ip NAT rule: original_ip '{1}',"
                    "translated_ip '{2}', rule type '{3}'"
                    .format(description, original_ip,
                            translated_ip, rule_type))

    success, task, _ = function(rule_type, original_ip, any_type,
                                translated_ip, any_type, any_type)
    if not success:
        raise cfy_exc.NonRecoverableError(
            "Could not {0} {1} rule").format(description, rule_type)
    wait_for_task(vcd_client, task)


def _get_vm_ip(vcd_client, ctx):
    try:
        vappName = _get_vapp_name(ctx.instance.relationships)
        vapp = vcd_client.get_vApp(vappName)
        if not vapp:
            raise cfy_exc.NonRecoverableError("Could not find vApp")
        vapp_ops = VAppOperations(vcd_client, vapp)
        vm_info = vapp_ops.get_vms_network_info()
        # assume that we have 1 vm per vApp with minium 1 connection
        connection = vm_info[0][0]
        if connection['is_connected']:
            return connection['ip']
        else:
            raise cfy_exc.NonRecoverableError("Network not connected")
    except IndexError:
        raise cfy_exc.NonRecoverableError("Could not get vm IP address")


def _get_vapp_name(relationships):
    try:
        return [relationship.target.instance.runtime_properties for relationship in relationships
                if VCLOUD_VAPP_NAME
                in relationship.target.instance.runtime_properties][0][VCLOUD_VAPP_NAME]
    except (IndexError, AttributeError):
        raise cfy_exc.NonRecoverableError("Could not find vApp by name")
