# Architecture and threat model

## Flow

1. **UI** (`app.py`): a Streamlit page collects an instruction.
2. **Validation** (`browserpilot/safety.py`): length limit, http/https only, and loopback, private, link-local and cloud-metadata targets rejected. Malformed URLs are rejected (fail closed).
3. **Runner** (`browserpilot/runner.py`): Streamlit re-runs the script on every interaction, so one `AgentRunner` per process (cached) owns a background thread with an asyncio loop. The `mcp-agent` application, the `Agent`, its LLM and the Playwright MCP server process live there. Heavy imports are lazy.
4. **Agent**: an `mcp-agent` `Agent` with the system prompt in `browserpilot/prompts.py` and the `playwright` MCP server attached, plus an OpenAI-compatible LLM.
5. **Tools**: `@playwright/mcp` (version pinned in `browserpilot/policy.json`) exposes tools such as `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_evaluate` and `browser_take_screenshot` over MCP stdio. It runs a headless Chromium with an in-memory profile.
6. **Result**: the model's final markdown report is shown in the UI.

## Threat model

| Risk | Mitigation | Residual risk |
|---|---|---|
| User asks for a local or internal address | Pre-flight rejection; `--blocked-origins` for loopback and metadata hosts | Private ranges other than literals in the instruction cannot be expressed as origin globs; redirects are not covered |
| Malicious page text instructs the model (prompt injection) | System prompt treats page content as data; no login/payment/download without explicit request | Not eliminated; models can still be fooled |
| Credential leakage | Keys come from the environment or a git-ignored file; the repository contains only placeholders | Anyone with access to the host can read them |
| Persistent browser state | `--isolated` in-memory profile | State persists for the life of the server process |

## Testing strategy

- **Pure logic** (validation, settings, policy/config sync, repository hygiene) is tested with the standard library only.
- **Tool layer** is tested against the real pinned Playwright MCP server and a real browser, using a small dependency-free JSON-RPC client (`scripts/mcp_smoke_test.mjs`) and a bundled fictional site.
- **UI** is exercised with Streamlit's `AppTest` in CI.
- **LLM loop** is not automatically tested: it depends on a model and is non-deterministic.
