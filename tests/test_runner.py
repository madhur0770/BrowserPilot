import os
import unittest
from unittest import mock

from browserpilot.config import Settings
from browserpilot.runner import AgentRunner, AgentUnavailable, CommandRejected


class RunnerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.runner = AgentRunner(Settings(request_timeout_seconds=5))
        self.addCleanup(self.runner.close)

    def test_invalid_command_is_rejected_before_any_agent_work(self):
        with self.assertRaises(CommandRejected):
            self.runner.run("Open http://169.254.169.254/latest/meta-data")

    def test_missing_credentials_give_actionable_error(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("browserpilot.runner.has_llm_credentials", return_value=False):
            with self.assertRaises(AgentUnavailable) as ctx:
                self.runner.run("Open https://example.com")
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    def test_missing_mcp_agent_dependency_is_reported_clearly(self):
        with mock.patch("browserpilot.runner.has_llm_credentials", return_value=True):
            try:
                import mcp_agent  # noqa: F401
            except ImportError:
                with self.assertRaises(AgentUnavailable) as ctx:
                    self.runner.run("Open https://example.com")
                self.assertIn("mcp-agent", str(ctx.exception))
            else:
                self.skipTest("mcp-agent is installed")


if __name__ == "__main__":
    unittest.main()
