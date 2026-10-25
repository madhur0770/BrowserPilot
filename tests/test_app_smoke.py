"""Smoke-test the Streamlit UI with Streamlit's AppTest. Skipped when Streamlit is not installed."""
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover
    AppTest = None

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@unittest.skipIf(AppTest is None, "streamlit is not installed")
class AppSmokeTests(unittest.TestCase):
    def test_app_renders_without_exceptions(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        self.assertEqual(at.title[0].value, "BrowserPilot")
        self.assertTrue(any(b.label == "Execute" for b in at.button))

    def test_empty_instruction_is_rejected_with_clear_message(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        next(b for b in at.button if b.label == "Execute").click().run()
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        self.assertIn("Enter an instruction", at.error[0].value)

    def test_unsafe_target_is_rejected(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        at.text_area(key="command").set_value("Open http://169.254.169.254/latest/meta-data").run()
        next(b for b in at.button if b.label == "Execute").click().run()
        self.assertIn("blocked by default", at.error[0].value)

    def test_example_button_fills_the_instruction(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        next(b for b in at.button if b.label == "Read a page").click().run()
        self.assertIn("example.com", at.text_area(key="command").value)


if __name__ == "__main__":
    unittest.main()
