import unittest

from ci.select_consumers import select


class SelectionTests(unittest.TestCase):
    def test_documentation_skips_products(self):
        self.assertEqual(
            select(["README.md", "docs/testing.md"]), {"dos": False, "juku": False}
        )

    def test_backends_select_only_their_product(self):
        self.assertEqual(
            select(["src/ravi/backends/dos/client.py"]), {"dos": True, "juku": False}
        )
        self.assertEqual(
            select(["src/ravi/protocols/monitor_v2.py"]), {"dos": False, "juku": True}
        )

    def test_shared_unknown_and_missing_diff_select_both(self):
        for paths in (
            [],
            ["src/ravi/transport.py"],
            ["new-backend/agent.py"],
            ["README.md", "src/ravi/targets.py"],
        ):
            self.assertEqual(select(paths), {"dos": True, "juku": True})
