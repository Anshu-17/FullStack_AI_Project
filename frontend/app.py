"""Streamlit entry point:  streamlit run app.py

Pages live in views/. More pages (Upload, Companies, Runs, ...) are added stage by stage.
"""
import streamlit as st

from api_client import API_URL

st.set_page_config(page_title="Business Evidence Platform", layout="wide")

pages = [
    st.Page("views/dashboard.py", title="Dashboard", default=True),
]

nav = st.navigation(pages)

with st.sidebar:
    st.caption(f"Backend: {API_URL}")
    st.caption(
        "Sources: :blue[Website] from crawled pages · :violet[Rule] business rule · "
        ":orange[Human] reviewer correction · :gray[Test] local fixture data"
    )

nav.run()
