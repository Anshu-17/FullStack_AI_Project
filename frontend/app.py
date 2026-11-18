"""Streamlit entry point:  streamlit run app.py

Not logged in -> only the Login page. Logged in -> the pages below, and a sidebar with the
user, a Logout button, the backend address and the source legend.
A browser refresh keeps you logged in: the token cookie is checked once per session (browser_session.py).
Reviewer-only buttons are hidden from viewers (the backend enforces the rule anyway).
"""
import streamlit as st

import api_client
import browser_session
import ui

st.set_page_config(page_title=ui.APP_NAME, page_icon="🌾", layout="wide")
ui.inject_css()

api_client.restore_from_cookie()   # after a refresh: log in again from the cookie (if the token is still valid)
browser_session.apply_pending()    # write / delete the cookie that login / logout asked for

if not api_client.is_logged_in():
    nav = st.navigation([st.Page("views/login.py", title="Log in", icon=":material/login:")])
else:
    pages = [st.Page("views/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True)]
    if api_client.is_reviewer():
        pages.append(st.Page("views/add_companies.py", title="Add companies", icon=":material/add_business:"))
    pages += [
        st.Page("views/companies.py", title="Companies", icon=":material/table_view:"),
        st.Page("views/company_detail.py", title="Company detail", icon=":material/fact_check:"),
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
