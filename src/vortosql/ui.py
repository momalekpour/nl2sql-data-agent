import pandas as pd
import streamlit as st

from vortosql.app import DEPARTMENTS, NL2SQLApp
from vortosql.core.logger import Logger

logger = Logger(__name__)

st.set_page_config(page_title="NL2SQL Data Agent", page_icon="🔍", layout="wide")

st.markdown(
    """
<style>
    .block-container { padding-top: 2rem; padding-bottom: 0; }
    .stChatMessage { background: transparent; }
    code { font-size: 0.78rem; }

    /* Page title */
    .page-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0f0f0f;
        letter-spacing: -0.01em;
    }
    .dept-badge {
        display: inline-block;
        background: #f0f2f6;
        border-radius: 20px;
        padding: 2px 12px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #555;
        vertical-align: middle;
    }

    /* Empty state */
    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 50vh;
        color: #bbb;
        font-size: 0.95rem;
        gap: 0.5rem;
    }
    .empty-state .icon { font-size: 2rem; }

    /* SQL caption */
    .sql-meta {
        font-size: 0.72rem;
        color: #aaa;
        margin-top: 0.3rem;
        font-family: monospace;
    }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_app(department: str) -> "NL2SQLApp":
    return NL2SQLApp(department=department)


# ── Hero landing page ─────────────────────────────────────────────────────────
if "started" not in st.session_state:
    st.markdown(
        """
    <div style="display:flex; flex-direction:column; align-items:center;
                justify-content:center;
                min-height:70vh; text-align:center;">
        <div style="font-size:0.85rem; font-weight:600; letter-spacing:0.15em;
                    text-transform:uppercase; color:#888; margin-bottom:1rem;">
            AI-Powered
        </div>
        <div style="font-size:3.2rem; font-weight:800; line-height:1.15;
                    letter-spacing:-0.02em; color:#0f0f0f; margin-bottom:1rem;">
            NL2SQL Data Agent
        </div>
        <div style="font-size:1.1rem; color:#666; margin-bottom:2.5rem;">
            Ask questions in plain English.<br>Get SQL results instantly.
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
    _, btn_col, _ = st.columns([3, 1, 3])
    with btn_col:
        if st.button("Get Started →", type="primary", use_container_width=True):
            st.session_state["started"] = True
            st.session_state["department"] = DEPARTMENTS[0]
            st.session_state["history"] = []
            st.rerun()
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("**NL2SQL Data Agent**")
    st.markdown(
        "<hr style='margin:0.4rem 0 0.8rem 0; border:none;"
        " border-top:1px solid #eee;'>",
        unsafe_allow_html=True,
    )
    selected = st.radio(
        "Department",
        options=DEPARTMENTS,
        index=DEPARTMENTS.index(st.session_state.get("department", DEPARTMENTS[0])),
    )
    if selected != st.session_state.get("department"):
        st.session_state["department"] = selected
        st.session_state["history"] = []
        st.rerun()

    st.caption(f"Queries are scoped to **{selected}** employees only.")

# ── Main chat ─────────────────────────────────────────────────────────────────
app = get_app(st.session_state["department"])


if not st.session_state.get("history"):
    st.markdown(
        "<div class='empty-state'>"
        "<div class='icon'>💬</div>"
        "<div>Ask anything about employees, certifications, or benefits.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

for entry in st.session_state.get("history", []):
    with st.chat_message("user"):
        st.markdown(f"**{entry['question']}**")
    with st.chat_message("assistant"):
        if entry.get("early_stop"):
            st.warning(entry["early_stop"])
        elif entry["error"]:
            st.error(entry["error"])
        elif entry["row_count"] == 0:
            st.info("No results found.")
            st.markdown(
                f"<div class='sql-meta'>{entry['sql']}"
                f" &nbsp;·&nbsp; {entry['latency']:.2f}s</div>",
                unsafe_allow_html=True,
            )
        else:
            if entry.get("answer"):
                st.markdown(entry["answer"])
            df = pd.DataFrame(entry["rows"], columns=entry["columns"])
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.markdown(
                f"<div class='sql-meta'>{entry['sql']}"
                f" &nbsp;·&nbsp; {entry['row_count']} row(s)"
                f" &nbsp;·&nbsp; {entry['latency']:.2f}s</div>",
                unsafe_allow_html=True,
            )

question = st.chat_input("Ask a question about your team...")
if question:
    question = str(question)
    logger.log(
        "info", "USER_QUESTION", {"question": question, "department": app.department}
    )
    with st.spinner("Thinking..."):
        result = app.ask(question)
    st.session_state["history"].append(
        {
            "question": question,
            "early_stop": result.get("pipeline_early_stop", ""),
            "sql": result.get("sql_executor_sql_query", ""),
            "columns": result.get("sql_executor_columns", []),
            "rows": result.get("sql_executor_rows", []),
            "row_count": result.get("sql_executor_row_count", 0),
            "latency": result.get("pipeline_latency", 0),
            "error": result.get("sql_executor_error"),
            "answer": result.get("answer_generator_answer", ""),
        }
    )
    st.rerun()
