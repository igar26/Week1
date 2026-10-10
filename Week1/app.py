from datetime import date
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from hockey.data import DB_PATH
from hockey.demo import EXAMPLES, ask_demo

st.set_page_config(page_title="Hockey Analytics", page_icon="🏒", layout="wide")
st.title("🏒 Aurora Hockey Analytics")
st.caption("Week 1 · Synthetic data · LangChain + LangGraph + Codex")
if not DB_PATH.exists():
    st.info("Generate the dataset first: python -m hockey.data")
    st.stop()
mode = st.sidebar.radio("Mode", ["Offline demo", "Codex agent"])
as_of = st.sidebar.date_input("Reference date", date(2026, 10, 9)).isoformat()
st.sidebar.caption("The fixed date makes the synthetic season demo reproducible.")
if mode == "Offline demo":
    st.warning("Offline examples run Python functions directly. No LLM or LangSmith tracing is used.")
    question = st.selectbox("Example question", EXAMPLES)
else:
    st.info("Codex chooses tools for your question. Uses your saved Codex CLI login and account usage limits. LangSmith traces the Python workflow when enabled.")
    example = st.selectbox("Example prompt", EXAMPLES)
    question = st.text_area("Ask a question", value=example)
if st.button("Run query", type="primary"):
    try:
        with st.spinner("Analyzing hockey data..."):
            if mode == "Offline demo":
                answer, calls = ask_demo(question, as_of)
            else:
                from hockey.agent import ask_codex
                answer, calls = ask_codex(question, as_of)
        st.subheader(answer.title)
        st.write(answer.explanation)
        records = answer.records()
        if answer.type == "chart" and records:
            frame = pd.DataFrame(records)
            plot = {"bar": px.bar, "line": px.line, "scatter": px.scatter}[answer.chart_kind]
            st.plotly_chart(plot(frame, x=answer.x, y=answer.y, color=answer.color or None, hover_data=[c for c in ["matchup", "date"] if c in frame.columns]), width="stretch")
        elif records:
            st.dataframe(pd.DataFrame(records), hide_index=True, width="stretch")
        elif answer.type != "text":
            st.info("No matching data for this query.")
        with st.expander("Tool calls" if mode == "Codex agent" else "Direct function calls (offline)", expanded=True):
            st.json(calls)
        with st.expander("Structured output JSON"):
            st.json(answer.model_dump())
        st.download_button("Download answer JSON", answer.model_dump_json(indent=2), "hockey-answer.json", "application/json")
    except Exception as exc:
        from hockey.agent import CodexError
        if isinstance(exc, CodexError):
            st.error(str(exc))
            st.stop()
        st.error(f"Query failed ({type(exc).__name__}). Check your setup, model access, reference date and tool inputs.")
        st.caption("For Codex failures, run codex login status and check your account usage limits. Secrets and raw provider errors are not displayed.")
