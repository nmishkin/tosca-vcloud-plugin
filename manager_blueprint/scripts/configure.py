import tempfile
import json

import fabric

import vcloud_plugin_common
from cloudify import ctx
from network_plugin import get_network_name


PROVIDER_CONTEXT_RUNTIME_PROPERTY = 'provider_context'

def configure(vcloud_config):
    _copy_vsphere_configuration_to_manager(vcloud_config)
    _update_vm()
    _save_context()


def _copy_vsphere_configuration_to_manager(vcloud_config):
    tmp = tempfile.mktemp()
    with open(tmp, 'w') as f:
        json.dump(vcloud_config, f)
    fabric.api.put(tmp,
                   vcloud_plugin_common.Config.VCLOUD_CONFIG_PATH_DEFAULT)


def _get_distro():
    """ detect current distro """
    return fabric.api.run('python -c "import platform; print platform.dist()[0]"')


def _update_vm():
    """ install some packeges for future deployments creation """
    distro = _get_distro()
    if 'Ubuntu' in distro:
        # update system to last version
        fabric.api.run("sudo apt-get update -q -y 2>&1")
        fabric.api.run("sudo apt-get dist-upgrade -q -y 2>&1")
        # install:
        # * zram-config for minimize out-of-memory cases with zswap
        # * other packages for create deployments from source
        fabric.api.run("sudo apt-get install zram-config gcc python-dev libxml2-dev libxslt-dev -q -y 2>&1")


def _save_context():

    resources = dict()

    node_instances = ctx._endpoint.storage.get_node_instances()
    nodes_by_id = \
        {node.id: node for node in ctx._endpoint.storage.get_nodes()}

    for node_instance in node_instances:
        run_props = node_instance.runtime_properties
        props = nodes_by_id[node_instance.node_id].properties

        if "management_network" == node_instance.node_id:
            resources['int_network'] = {
                "name": props.get('resource_id'),
                "use_external_resource": props.get('use_external_resource')
            }
        if "manager_floating_ip" == node_instance.node_id:
            resources['floating_ip'] = {
                "ip": run_props.get('public_ip')
            }

    return {
        'resources': resources
    }
