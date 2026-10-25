"""Pre-flight validation of user instructions.

These checks are a best-effort first layer. They catch obviously unsafe targets in the
text of an instruction (non-web schemes, loopback and private addresses, cloud metadata
endpoints). They cannot see where a page later redirects the browser or which links the
model decides to follow. The second layer is the ``--blocked-origins`` policy passed to
the Playwright MCP server, which its documentation also describes as not being a
security boundary. Run BrowserPilot in an environment with no access to sensitive
internal services.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from .config import Settings, load_policy

URL_PATTERN = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://(?:\[[0-9a-fA-F:.]+\]|[^\s<>\"')\[\]])[^\s<>\"')]*")
# Schemes that never use "//" but are dangerous when a browser is told to open them.
OPAQUE_SCHEME_PATTERN = re.compile(r"\b(javascript|data|blob|vbscript|about|chrome|view-source):", re.IGNORECASE)


class CommandRejected(ValueError):
    """Raised when an instruction fails validation. The message is safe to show to users."""


def extract_urls(text: str) -> list[str]:
    return [match.rstrip(".,;:") for match in URL_PATTERN.findall(text)]


def _is_blocked_host(host: str, policy: dict) -> bool:
    host = host.strip("[]").lower().rstrip(".")
    if not host:
        return True
    if host in policy["blocked_hosts"]:
        return True
    if any(host.endswith(suffix) for suffix in policy["blocked_host_suffixes"]):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        or address.is_multicast
    )


def validate_command(text: str, settings: Settings | None = None) -> str:
    """Return the cleaned instruction or raise :class:`CommandRejected`."""
    settings = settings or Settings.from_env()
    policy = load_policy()
    command = (text or "").strip()
    if not command:
        raise CommandRejected("Enter an instruction for the browser agent.")
    if len(command) > settings.max_command_chars:
        raise CommandRejected(
            f"Instruction is too long ({len(command)} characters; limit {settings.max_command_chars})."
        )
    if OPAQUE_SCHEME_PATTERN.search(command):
        raise CommandRejected("Only http and https pages are supported.")
    for url in extract_urls(command):
        try:
            parsed = urlparse(url)
            parsed.port  # noqa: B018 - raises ValueError for malformed ports
        except ValueError:
            raise CommandRejected(f"Could not parse the URL '{url}'.") from None
        if parsed.scheme.lower() not in policy["allowed_url_schemes"]:
            raise CommandRejected(f"Unsupported URL scheme '{parsed.scheme}'. Only http and https pages are supported.")
        if not settings.allow_private_network and _is_blocked_host(parsed.hostname or "", policy):
            raise CommandRejected(
                "Local, private and cloud-metadata addresses are blocked by default. "
                "Set BROWSERPILOT_ALLOW_PRIVATE_NETWORK=1 only if you understand the risk."
            )
    return command
