"""Streamlit entry point: navigation across the five dashboard pages.

Runs with layout="wide" and st.navigation over Home, Sales, Delivery,
Satisfaction, and Sellers. The dashboard reads only from MongoDB; it never
imports pyspark and never opens a CSV or Parquet file.
"""

from __future__ import annotations

import streamlit as st

from lib import theme

st.set_page_config(
    page_title="Olist commerce insights",
    page_icon=theme.FAVICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

theme.register_template()
theme.inject_css()

pages = [
    st.Page("views/home.py", title="Home", default=True),
    st.Page("views/sales.py", title="Sales"),
    st.Page("views/delivery.py", title="Delivery"),
    st.Page("views/satisfaction.py", title="Satisfaction"),
    st.Page("views/sellers.py", title="Sellers"),
]

st.navigation(pages).run()
