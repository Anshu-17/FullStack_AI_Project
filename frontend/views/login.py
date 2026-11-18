"""Login page: email + password. The backend checks them and returns a token."""
import streamlit as st

import api_client
from api_client import ApiError

st.title("Business Evidence Platform")
st.subheader("Log in")

if st.session_state.get("flash"):
    st.warning(st.session_state["flash"])

with st.form("login"):
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    submitted = st.form_submit_button("Log in", type="primary")

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
            st.rerun()  # app.py now shows the real pages

st.caption("Demo accounts are created by `python -m app.db.seed`; passwords are shared privately.")
