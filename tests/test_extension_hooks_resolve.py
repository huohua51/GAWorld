"""Guard against silently-disabled extension hooks.

Regression: the economy hooks were registered under the defunct flat name
'economy_module', which raised ImportError at load time and silently disabled
the entire economy subsystem (tax, spending, shocks, econ_security updates).
Every registered "module:function" hook must resolve to a callable.
"""

import importlib
import unittest

from gaworld.settings.integrations import integration_settings


class TestExtensionHooksResolve(unittest.TestCase):
    def test_all_registered_hooks_import(self):
        hooks = integration_settings()["extensions"]["hooks"]
        unresolved = []
        for event, paths in hooks.items():
            for path in paths:
                self.assertIn(":", path, f"{event}: '{path}' must be module:function")
                module_name, fn_name = path.split(":", 1)
                try:
                    module = importlib.import_module(module_name)
                except ImportError as exc:
                    unresolved.append(f"{path} ({exc})")
                    continue
                if not callable(getattr(module, fn_name, None)):
                    unresolved.append(f"{path} (not callable)")
        self.assertEqual(unresolved, [], f"unresolved hooks: {unresolved}")

    def test_economy_hooks_are_registered(self):
        hooks = integration_settings()["extensions"]["hooks"]
        joined = " ".join(p for paths in hooks.values() for p in paths)
        self.assertIn("on_simulation_start", joined)
        self.assertIn("on_day_start", joined)
        # must point at the real package, not the defunct flat shim
        self.assertNotIn("economy_module:", joined)


if __name__ == "__main__":
    unittest.main()
