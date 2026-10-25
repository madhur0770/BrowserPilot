"""Guards against dependency drift: the agent stack must import when it is installed."""
import importlib.util
import unittest


class AgentDependencyTests(unittest.TestCase):
    @unittest.skipIf(importlib.util.find_spec("mcp_agent") is None, "mcp-agent is not installed")
    def test_agent_stack_imports(self):
        # These are the exact imports browserpilot.runner performs lazily at run time.
        from mcp_agent.agents.agent import Agent  # noqa: F401
        from mcp_agent.app import MCPApp  # noqa: F401
        from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM  # noqa: F401


if __name__ == "__main__":
    unittest.main()
