"""Streamlit entry point.  Run with:  streamlit run app.py"""
import logging

import streamlit as st

from dashboard import analytics, batch_history, data_quality, overview, upload
from src import config
from src.database import init_db
from src.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("app")

st.set_page_config(page_title="Enterprise Data Quality Monitor", page_icon="📊", layout="wide")
st.markdown(
    """<style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    div[data-testid="stMetricValue"] {font-size: 1.6rem;}
    </style>""",
    unsafe_allow_html=True,
)

init_db(config.DB_PATH)

PAGES = {
    "Overview": overview.render,
    "Upload & Process": upload.render,
    "Data Quality": data_quality.render,
    "Batch History": batch_history.render,
    "Sales Analytics": analytics.render,
}

with st.sidebar:
    st.title("Data Quality Monitor")
    st.caption("Enterprise sales pipeline · local SQLite demo")
    choice = st.radio("Navigate", list(PAGES), label_visibility="collapsed")
    st.divider()
    st.caption("All data is synthetic. No personal information is collected.")

try:
    PAGES[choice]()
except Exception:
    logger.exception("Page '%s' failed to render", choice)
    st.error("This page could not be displayed. The technical details were written to the application log.")
