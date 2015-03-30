import mock
import unittest
from testconfig import config
import time


from cloudify import mocks as cfy_mocks
from cloudify import exceptions as cfy_exceptions

from vcloud_plugin_common import Config, VcloudAirClient

SUBSCRIPTION = 'subcription'
ONDEMAND = 'ondemand'


class IntegrationSubscriptionTestConfig(Config):
    VCLOUD_CONFIG_PATH_ENV_VAR = 'VCLOUD_INTEGRATION_TEST_CONFIG_PATH'
    VCLOUD_CONFIG_PATH_DEFAULT = '~/vcloud_integration_subscription_test_config.json'


class IntegrationOndemandTestConfig(Config):
    VCLOUD_CONFIG_PATH_ENV_VAR = 'VCLOUD_INTEGRATION_TEST_CONFIG_PATH'
    VCLOUD_CONFIG_PATH_DEFAULT = '~/vcloud_integration_ondemand_test_config.json'


class VcloudSubscriptionTestConfig(Config):
    VCLOUD_CONFIG_PATH_ENV_VAR = 'VCLOUD_CONFIG_PATH'
    VCLOUD_CONFIG_PATH_DEFAULT = '~/vcloud_config_subscription.json'


class VcloudOndemandTestConfig(Config):
    VCLOUD_CONFIG_PATH_ENV_VAR = 'VCLOUD_CONFIG_PATH'
    VCLOUD_CONFIG_PATH_DEFAULT = '~/vcloud_config_ondemand.json'


class TestCase(unittest.TestCase):

    def __init__(self, testname):
        super(TestCase, self).__init__(testname)
        test_configs = {SUBSCRIPTION: (VcloudSubscriptionTestConfig().get(), IntegrationSubscriptionTestConfig().get()),
                        ONDEMAND: (VcloudOndemandTestConfig().get(), IntegrationOndemandTestConfig().get())}
        if not config:
            raise RuntimeError("""Vcloud Service type not defined.
To define servist type for tests, add one of command line key to nosetest command:
 --tc=ondemand:
 --tc=subscription:""")
        if len(config) != 1:
            raise RuntimeError("Config must contain 1 element")
        self.service_type = config.keys()[0]
        service_config = test_configs.get(self.service_type)
        if not service_config:
            raise RuntimeError("Unknown service_type: {0}. Parameter must one of {1}".
                               format(self.service_type, (SUBSCRIPTION, ONDEMAND)))
        self.vcloud_config = service_config[0]
        self.test_config = service_config[1]

        if not self.vcloud_config:
            raise RuntimeError("vcloud_config empty")
        if not self.test_config:
            raise RuntimeError("test_config empty")

    def setUp(self):
        print "\nUsed config: {0}".format(self.service_type)
        fake_ctx = cfy_mocks.MockCloudifyContext(
            node_id='test',
            node_name='test',
            properties={})
        with mock.patch('vcloud_plugin_common.ctx', fake_ctx):
            self.vca_client = VcloudAirClient().get(config=self.vcloud_config)

    def _run_with_retry(self, func, ctx):
        while True:
            try:
                return func(ctx=ctx)
            except cfy_exceptions.OperationRetry as e:
                ctx.operation._operation_retry = None
                ctx.logger.info(format(str(e)))
                time.sleep(e.retry_after)
