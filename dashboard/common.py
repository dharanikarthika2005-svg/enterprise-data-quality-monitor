"""Shared dashboard helpers: number formatting, consistent Plotly styling, and empty-state messages."""
import plotly.express as px
import streamlit as st


def money(value) -> str:
    return "Not available" if value is None else f"{value:,.2f}"


def line_chart(frame, x, y, title, y_label=None):
    fig = px.line(frame, x=x, y=y, markers=True, title=title)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), yaxis_title=y_label or y, xaxis_title="")
    return fig


def bar_chart(frame, x, y, title, orientation="v"):
    fig = px.bar(frame, x=x, y=y, title=title, orientation=orientation)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    return fig


def empty_state(message: str) -> None:
    st.info(message)
