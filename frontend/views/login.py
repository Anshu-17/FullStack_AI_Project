"""Login page: email + password in a centred card. The backend checks them and returns a token."""
import streamlit as st

import api_client
import ui
from api_client import ApiError

_, middle, _ = st.columns([1, 2, 1])  # centred on wide screens; full width on a phone (columns stack)
with middle, st.container(border=True):
    ui.html_block(f'<div style="text-align:center"><div style="font-size:2.2rem">🌾</div>'
                  f'<h2 style="margin:.2rem 0 0 0">{ui.APP_NAME}</h2>'
                  f'<div class="bep-muted">{ui.SUBTITLE}</div></div>')
    if st.session_state.get("flash"):
        st.warning(st.session_state["flash"])

    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary", width="stretch")

    if submitted:
        if not email or not password:
            st.error("Enter your email and password.")
        else:
            try:
                with st.spinner("Checking..."):
                    api_client.login(email, password)
            except ApiError as exc:
                st.error(exc.message)  # "Invalid email or password." (the backend never says which)
            else:
                st.rerun()  # app.py now shows the real pages (and saves the login cookie)

    st.caption("Demo accounts are created by `python -m app.db.seed`; passwords are shared privately.")
