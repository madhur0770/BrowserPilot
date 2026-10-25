"""Thin wrapper that runs one MCP agent on a dedicated asyncio loop.

Streamlit re-executes the script on every interaction, so the agent, its MCP server
processes and its event loop live on a background thread owned by this object. Heavy
dependencies (mcp-agent, openai) are imported lazily so the rest of the package stays
importable and testable without them.
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import TimeoutError as FutureTimeout

from .config import Settings, has_llm_credentials
from .prompts import AGENT_INSTRUCTION, AGENT_NAME
from .safety import CommandRejected, validate_command


class AgentUnavailable(RuntimeError):
    """The agent cannot run (missing dependency or credentials). Message is user-safe."""


class AgentRunner:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="browserpilot-loop", daemon=True)
        self._thread.start()
        self._context = None
        self._agent = None
        self._llm = None

    # -- public API -------------------------------------------------------------
    def run(self, command: str) -> str:
        """Validate and execute one instruction; return the agent's markdown report."""
        command = validate_command(command, self.settings)  # raises CommandRejected
        if not has_llm_credentials():
            raise AgentUnavailable(
                "No LLM credentials found. Set OPENAI_API_KEY, or copy "
                "mcp_agent.secrets.yaml.example to mcp_agent.secrets.yaml (for Ollama use any placeholder key)."
            )
        future = asyncio.run_coroutine_threadsafe(self._execute(command), self._loop)
        try:
            return future.result(timeout=self.settings.request_timeout_seconds)
        except FutureTimeout as exc:
            future.cancel()
            raise AgentUnavailable(
                f"The agent did not finish within {self.settings.request_timeout_seconds} seconds."
            ) from exc

    def close(self) -> None:
        if self._context is not None:
            future = asyncio.run_coroutine_threadsafe(self._context.__aexit__(None, None, None), self._loop)
            try:
                future.result(timeout=30)
            except Exception:  # noqa: BLE001 - best-effort shutdown
                pass
            self._context = None
        self._loop.call_soon_threadsafe(self._loop.stop)

    # -- internals --------------------------------------------------------------
    async def _ensure_started(self) -> None:
        if self._llm is not None:
            return
        try:
            from mcp_agent.agents.agent import Agent
            from mcp_agent.app import MCPApp
            from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise AgentUnavailable("mcp-agent is not installed. Run: pip install -r requirements.txt") from exc

        app = MCPApp(name="browserpilot")
        self._context = app.run()
        agent_app = await self._context.__aenter__()
        self._agent = Agent(name=AGENT_NAME, instruction=AGENT_INSTRUCTION, server_names=["playwright"])
        initialize = getattr(self._agent, "initialize", None)
        if initialize is not None:
            await initialize()
        self._llm = await self._agent.attach_llm(OpenAIAugmentedLLM)
        tools = await self._agent.list_tools()
        agent_app.logger.info("Registered tools", data=tools)

    async def _execute(self, command: str) -> str:
        await self._ensure_started()
        from mcp_agent.workflows.llm.augmented_llm import RequestParams

        return await self._llm.generate_str(
            message=command,
            request_params=RequestParams(use_history=True, maxTokens=self.settings.max_tokens),
        )


__all__ = ["AgentRunner", "AgentUnavailable", "CommandRejected"]
