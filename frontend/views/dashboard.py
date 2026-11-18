"""Dashboard: backend status, live metrics and the most recent runs (all from the API)."""
import streamlit as st

import api_client
import ui
from api_client import ApiError

ui.page_header("Dashboard", "Live numbers from the backend: companies, research runs, outcomes and AI usage.")

try:
    with st.spinner("Loading..."):
        ready = api_client.get("/ready")
        metrics = api_client.get("/api/metrics")
        runs = api_client.get("/api/runs", page_size=5)
except ApiError as exc:
    st.error(exc.message)
    st.stop()

st.success(f"Backend connected · database {ready['database']} · migration {ready['migration']}")

jobs = metrics["jobs"]
ai_calls = sum(sum(outcomes.values()) for outcomes in metrics["ai_calls"].values())
# Main cards (they wrap onto several rows on a narrow screen)
cards = [("Companies", metrics["companies"], None), ("Runs", metrics["runs"], None),
         ("Completed", jobs.get("completed", 0), "Jobs finished with nothing to review"),
         ("Needs review", jobs.get("review_required", 0), "Jobs with Possible answers, dropped quotes or conflicts"),
         ("Failed", jobs.get("failed", 0), "Jobs that could not be researched (see Runs for the reason)"),
         ("AI calls", ai_calls, "Every call to an AI provider, including retries")]
for column, (label, value, help_text) in zip(st.columns(6), cards, strict=True):
    column.metric(label, f"{value:,}", help=help_text, border=True)

c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1.5])  # the cost card is wider: "unknown" must fit
c1.metric("Answers saved", f"{metrics['classifications']:,}", border=True)
c2.metric("Human corrections", metrics["overrides"], border=True)
c3.metric("Retries", metrics["retries"], border=True)
avg = metrics["job_duration_seconds"]["avg"]
c4.metric("Avg job time", f"{avg:.0f} s" if avg is not None else "-", border=True)
cost = metrics["est_cost_usd"]
c5.metric("Estimated AI cost", f"${cost:.4f}" if cost is not None else "unknown", border=True,
          help="Unknown when no prices are configured (free tier). Never guessed.")
st.caption(f"AI tokens: {metrics['ai_tokens']['input']:,} in / {metrics['ai_tokens']['output']:,} out")

left, right = st.columns(2)
with left, st.container(border=True):
    st.subheader("Jobs by status")
    if sum(jobs.values()) == 0:
        st.info("No jobs yet. Add companies and start a run to see progress here.")
    else:
        ui.html_block(ui.pills(jobs))
        st.bar_chart(jobs, color="#2E6B3F", height=220)
with right, st.container(border=True):
    st.subheader("AI calls by provider")
    if not metrics["ai_calls"]:
        st.info("No AI calls yet.")
    else:
        outcome_names = sorted({o for outcomes in metrics["ai_calls"].values() for o in outcomes})
        st.dataframe([{"provider": p, **{o: outcomes.get(o, 0) for o in outcome_names}}  # 0, not "None"
                      for p, outcomes in metrics["ai_calls"].items()], hide_index=True, width="stretch")

with st.container(border=True):
    st.subheader("Recent runs")
    if not runs["items"]:
        st.info("No runs yet.")
    else:
        st.dataframe([{"run": f"#{r['id']}", "status": r["status"].replace("_", " "),
                       "progress": r["progress"]["percent"] / 100,
                       "done": f"{r['progress']['done']} / {r['progress']['total']}",
                       "created": ui.when(r["created_at"])} for r in runs["items"]],
                     hide_index=True, width="stretch",
                     column_config={"progress": st.column_config.ProgressColumn("progress", min_value=0, max_value=1,
                                                                                format="percent")})
        o1, o2 = st.columns([3, 1], vertical_alignment="bottom")
        choice = o1.selectbox("Open run", [r["id"] for r in runs["items"]], format_func=lambda i: f"Run #{i}")
        if o2.button("Open run", icon=":material/open_in_new:", width="stretch"):
            st.session_state["run_id"] = choice
            st.switch_page("views/runs.py")

if st.button("Refresh", icon=":material/refresh:"):
    st.rerun()
