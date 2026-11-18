"""Streamlit entry point:  streamlit run app.py

Not logged in -> only the Login page. Logged in -> the pages below, and a sidebar with the
user, a Logout button, the backend address and the source legend.
Reviewer-only buttons are hidden from viewers (the backend enforces the rule anyway).
"""
import streamlit as st

import api_client
import ui

st.set_page_config(page_title="Business Evidence Platform", layout="wide")

if not api_client.is_logged_in():
    nav = st.navigation([st.Page("views/login.py", title="Log in", icon=":material/login:")])
else:
    pages = [st.Page("views/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True)]
    if api_client.is_reviewer():
        pages.append(st.Page("views/add_companies.py", title="Add companies", icon=":material/add_business:"))
    pages += [
        st.Page("views/companies.py", title="Companies", icon=":material/list:"),
        st.Page("views/company_detail.py", title="Company detail", icon=":material/info:"),
        st.Page("views/runs.py", title="Runs", icon=":material/sync:"),
    ]
    nav = st.navigation(pages)

    with st.sidebar:
        user = api_client.current_user()
        st.markdown(f"**{user.get('email', '')}**  \nRole: `{user.get('role', '')}`")
        if st.button("Log out", icon=":material/logout:"):
            api_client.logout()
            st.rerun()
        st.divider()
        st.caption(f"Backend: {api_client.API_URL}")
        ui.legend()

nav.run()
