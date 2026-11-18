"""Dashboard: backend status and live counts from the database (via the API)."""
import streamlit as st

import api_client
from api_client import ApiError

st.title("Dashboard")

try:
    ready = api_client.get("/ready")
    stats = api_client.get("/api/stats")
except ApiError as exc:
    st.error(exc.message)
    st.stop()

st.success(f"Backend connected · database {ready['database']} · migration {ready['migration']}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Companies", stats["companies"])
c2.metric("Runs", stats["runs"])
c3.metric("Answers saved", stats["classifications"])
c4.metric("Human corrections", stats["overrides"])

st.subheader("Jobs by status")
jobs = stats["jobs"]
if sum(jobs.values()) == 0:
    st.info("No jobs yet. Add companies and start a run to see progress here.")
else:
    st.bar_chart(jobs)

if st.button("Refresh"):
    st.rerun()
