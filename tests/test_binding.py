"""The bind-address check gates whether an unauthenticated app is exposed."""

import unittest

from het.server import _describe_binding


class TestDescribeBinding(unittest.TestCase):
    def test_loopback_is_silent(self):
        for host in ("127.0.0.1", "::1"):
            is_loopback, warning = _describe_binding(host)
            self.assertTrue(is_loopback, host)
            self.assertIsNone(warning, host)

    def test_tailnet_address_warns_but_is_not_loopback(self):
        is_loopback, warning = _describe_binding("100.101.102.103")
        self.assertFalse(is_loopback)
        self.assertIn("tailnet", warning)

    def test_all_interfaces_warns_loudly(self):
        is_loopback, warning = _describe_binding("0.0.0.0")
        self.assertFalse(is_loopback)
        self.assertIn("YOK", warning)

    def test_public_address_warns(self):
        is_loopback, warning = _describe_binding("5.75.130.20")
        self.assertFalse(is_loopback)
        self.assertIn("PUBLIC", warning)

    def test_private_lan_address_warns(self):
        is_loopback, warning = _describe_binding("192.168.1.10")
        self.assertFalse(is_loopback)
        self.assertIsNotNone(warning)

    def test_hostname_is_treated_as_unknown(self):
        is_loopback, warning = _describe_binding("localhost")
        self.assertFalse(is_loopback)
        self.assertIsNotNone(warning)


if __name__ == "__main__":
    unittest.main()
