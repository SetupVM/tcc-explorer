import importlib.util
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
sys.path.insert(0, str(APP.parent))


class AppSmokeTests(unittest.TestCase):
    def test_app_defines_main(self):
        spec = importlib.util.spec_from_file_location("expenses_app", APP)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
