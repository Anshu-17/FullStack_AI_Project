"""Dashboard: backend status, live metrics and the most recent runs (all from the API)."""
import streamlit as st

import api_client
import ui
from api_client import ApiError

st.title("Dashboard")

try:
    with st.spinner("Loading..."):
        ready = api_client.get("/ready")
        metrics = api_client.get("/api/metrics")
        runs = api_client.get("/api/runs", page_size=5)
except ApiError as exc:
    st.error(exc.message)
    st.stop()

st.success(f"Backend connected · database {ready['database']} · migration {ready['migration']}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Companies", metrics["companies"])
c2.metric("Runs", metrics["runs"])
c3.metric("Answers saved", metrics["classifications"])
c4.metric("Human corrections", metrics["overrides"])

c5, c6, c7, c8 = st.columns(4)
c5.metric("Retries", metrics["retries"])
avg = metrics["job_duration_seconds"]["avg"]
c6.metric("Avg job time", f"{avg:.0f} s" if avg is not None else "-")
c7.metric("AI tokens (in / out)", f"{metrics['ai_tokens']['input']:,} / {metrics['ai_tokens']['output']:,}")
cost = metrics["est_cost_usd"]
c8.metric("Estimated AI cost", f"${cost:.4f}" if cost is not None else "unknown",
          help="Unknown when no prices are configured (free tier). Never guessed.")

left, right = st.columns(2)
with left:
    st.subheader("Jobs by status")
    jobs = metrics["jobs"]
    if sum(jobs.values()) == 0:
        st.info("No jobs yet. Add companies and start a run to see progress here.")
    else:
        st.bar_chart(jobs)
with right:
    st.subheader("AI calls")
    calls = metrics["ai_calls"]
    if not calls:
        st.info("No AI calls yet.")
    else:
        st.dataframe([{"provider": p, **outcomes} for p, outcomes in calls.items()], hide_index=True)

st.subheader("Recent runs")
if not runs["items"]:
    st.info("No runs yet.")
else:
    st.dataframe([{"run": r["id"], "status": r["status"],
                   "progress": f"{r['progress']['done']}/{r['progress']['total']}",
                   "created": ui.when(r["created_at"])} for r in runs["items"]], hide_index=True)
    choice = st.selectbox("Open run", [r["id"] for r in runs["items"]], format_func=lambda i: f"Run {i}")
    if st.button("Open run", icon=":material/open_in_new:"):
        st.session_state["run_id"] = choice
        st.switch_page("views/runs.py")

if st.button("Refresh"):
    st.rerun()
