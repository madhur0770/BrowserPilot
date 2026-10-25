"""Runtime settings and the default network policy.

This module must stay importable without Streamlit, mcp-agent or OpenAI installed,
so the policy and validation logic can be unit-tested with the standard library only.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
POLICY_PATH = PACKAGE_DIR / "policy.json"


def load_policy() -> dict:
    with POLICY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Settings read from environment variables (all optional)."""

    allow_private_network: bool = False
    max_command_chars: int = 2000
    request_timeout_seconds: int = 300
    max_tokens: int = 10000
    extra_blocked_origins: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> "Settings":
        extra = tuple(
            item.strip()
            for item in os.environ.get("BROWSERPILOT_EXTRA_BLOCKED_ORIGINS", "").split(";")
            if item.strip()
        )
        return cls(
            allow_private_network=_env_flag("BROWSERPILOT_ALLOW_PRIVATE_NETWORK"),
            max_command_chars=int(os.environ.get("BROWSERPILOT_MAX_COMMAND_CHARS", "2000")),
            request_timeout_seconds=int(os.environ.get("BROWSERPILOT_TIMEOUT_SECONDS", "300")),
            max_tokens=int(os.environ.get("BROWSERPILOT_MAX_TOKENS", "10000")),
            extra_blocked_origins=extra,
        )


def has_llm_credentials(project_root: Path = PROJECT_ROOT) -> bool:
    """True if an API key is available via environment or the local secrets file."""
    if os.environ.get("OPENAI_API_KEY"):
        return True
    return (project_root / "mcp_agent.secrets.yaml").is_file()
