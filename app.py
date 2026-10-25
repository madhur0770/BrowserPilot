"""BrowserPilot - Streamlit front end.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from browserpilot.config import Settings, has_llm_credentials
from browserpilot.runner import AgentRunner, AgentUnavailable
from browserpilot.safety import CommandRejected

EXAMPLES = {
    "Read a page": "Open https://example.com and summarise what the page says.",
    "Follow a link": "Open https://example.com, click the first link on the page and tell me where it leads.",
    "Extract data": "Open https://en.wikipedia.org/wiki/Model_Context_Protocol and list its key facts as bullet points.",
}

st.set_page_config(page_title="BrowserPilot", page_icon=":globe_with_meridians:", layout="wide")
st.title("BrowserPilot")
st.caption("Describe what to do in a browser; a model drives Playwright through the Model Context Protocol and reports back.")


@st.cache_resource(show_spinner=False)
def get_runner() -> AgentRunner:
    return AgentRunner(Settings.from_env())


if "command" not in st.session_state:
    st.session_state.command = ""
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.subheader("Examples")
    for label, text in EXAMPLES.items():
        if st.button(label, use_container_width=True):
            st.session_state.command = text
    st.divider()
    st.subheader("Safety defaults")
    st.markdown(
        "- Headless, isolated browser profile\n"
        "- Localhost, private and metadata addresses blocked\n"
        "- Page content is treated as untrusted data\n"
        "- No logins, payments or downloads unless you ask"
    )
    if not has_llm_credentials():
        st.warning("No LLM credentials found. Set `OPENAI_API_KEY` or create `mcp_agent.secrets.yaml`.")

st.text_area(
    "Instruction",
    key="command",
    height=120,
    placeholder="For example: Open https://example.com and summarise the page.",
)

if st.button("Execute", type="primary", icon=":material/play_arrow:"):
    st.session_state.attempted = True
    with st.spinner("Driving the browser..."):
        try:
            report = get_runner().run(st.session_state.command)
            st.session_state.history.insert(0, (st.session_state.command, report))
            st.session_state.history = st.session_state.history[:5]
        except CommandRejected as exc:
            st.error(str(exc))
        except AgentUnavailable as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001 - show unexpected failures instead of a stack trace
            st.error(f"The agent failed: {exc}")

if not st.session_state.history and not st.session_state.get("attempted"):
    st.info(
        "Type an instruction above (or pick an example in the sidebar) and press Execute. "
        "The agent plans the steps, drives a headless browser through Playwright MCP tools, and reports back here."
    )

for command, report in st.session_state.history[:1]:
    st.subheader("Execution summary")
    st.caption(f"Instruction: {command}")
    with st.container(border=True):
        st.markdown(report)

if len(st.session_state.history) > 1:
    with st.expander("Earlier runs"):
        for command, report in st.session_state.history[1:]:
            st.markdown(f"**{command}**")
            st.markdown(report)
            st.divider()
