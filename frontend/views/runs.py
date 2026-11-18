"""Runs: list, live progress (refreshes every 3 s while active), cancel / retry, job drill-down.

Progress always comes from the server (finished jobs / total), never estimated in the browser.
"""
import streamlit as st

import api_client
import ui
from api_client import ApiError

st.title("Runs")

runs = ui.load("runs", api_client.get, "/api/runs", page_size=50)["items"]
if not runs:
    st.info("No runs yet. Start one from 'Add companies' or a company's Rescan button.")
    st.stop()

st.dataframe([{"run": r["id"], "status": r["status"], "progress": f"{r['progress']['done']}/{r['progress']['total']}",
               "created": ui.when(r["created_at"])} for r in runs], hide_index=True)

ids = [r["id"] for r in runs]
wanted = st.session_state.get("run_id")
run_id = st.selectbox("Run", ids, index=ids.index(wanted) if wanted in ids else 0, format_func=lambda i: f"Run {i}")
st.session_state["run_id"] = run_id


def act(label: str, path: str) -> None:
    """A reviewer action button (cancel / retry) that reports the API's answer."""
    try:
        api_client.post(path)
        st.toast(f"{label}: done")
    except ApiError as exc:
        ui.show_error(exc)


def show_run(run_id: int) -> None:
    run = api_client.get(f"/api/runs/{run_id}")
    items = api_client.get(f"/api/runs/{run_id}/items", page_size=200)["items"]
    active = run["status"] in ui.ACTIVE_RUN

    progress = run["progress"]
    st.progress(progress["percent"] / 100, text=f"Run {run_id}: **{run['status']}** — "
                                                 f"{progress['done']} of {progress['total']} finished")
    counts = {k: v for k, v in run["counts"].items() if v}
    st.caption(" · ".join(f"{k}: {v}" for k, v in counts.items()) + (" · refreshing every 3 s" if active else ""))
    if run["skipped"]:
        st.caption(f"Skipped when started: {len(run['skipped'])} (already in progress or unknown)")

    if api_client.is_reviewer():
        b1, b2 = st.columns(2)
        if active and b1.button("Cancel run", icon=":material/cancel:"):
            act("Cancel", f"/api/runs/{run_id}/cancel")
            st.rerun()
        if any(i["status"] in ("failed", "cancelled") for i in items) and b2.button("Retry failed",
                                                                                     icon=":material/replay:"):
            act("Retry failed", f"/api/runs/{run_id}/retry-failed")
            st.rerun()

    st.dataframe([{"job": i["job_id"], "company": i["company_name"], "status": i["status"],
                   "attempts": f"{i['attempt_count']}/{i['max_attempts']}", "error": i["last_error_code"] or "",
                   "message": i["last_error_message"] or "", "finished": ui.when(i["finished_at"])}
                  for i in items], hide_index=True, width="stretch")

    # The page outside this fragment shows the run as "active"; once it finishes, redraw everything
    # once so the 3-second refresh stops.
    if not active and st.session_state.get("run_was_active"):
        st.session_state["run_was_active"] = False
        st.rerun()
    st.session_state["run_was_active"] = active


first = ui.load("run", api_client.get, f"/api/runs/{run_id}")
if first["status"] in ui.ACTIVE_RUN:
    st.fragment(run_every=3)(show_run)(run_id)  # only this part re-runs, every 3 s
else:
    show_run(run_id)

# ------------------------------------------------------------------ job drill-down
st.subheader("Job details")
items = ui.load("jobs", api_client.get, f"/api/runs/{run_id}/items", page_size=200)["items"]
job_id = st.selectbox("Job", [i["job_id"] for i in items],
                      format_func=lambda j: next(f"Job {j} — {i['company_name']} ({i['status']})"
                                                 for i in items if i["job_id"] == j))
if job_id:
    job = ui.load("job", api_client.get, f"/api/jobs/{job_id}")
    if api_client.is_reviewer() and job["status"] in ("failed", "cancelled") and st.button("Retry this job"):
        act("Retry", f"/api/jobs/{job_id}/retry")
        st.rerun()
    with st.expander("Attempts", expanded=True):
        st.dataframe([{"attempt": a["attempt_no"], "status": a["status"], "worker": a["worker_id"],
                       "error": a["error_code"] or "", "message": a["error_message"] or "",
                       "started": ui.when(a["started_at"]), "finished": ui.when(a["finished_at"])}
                      for a in job["attempts"]], hide_index=True)
    with st.expander("Status changes"):
        st.dataframe([{"when": ui.when(e["created_at"]), "from": e["from_status"] or "", "to": e["to_status"],
                       "reason": e["reason"] or ""} for e in job["events"]], hide_index=True)
    with st.expander(f"Pages fetched ({len(job['pages'])})"):
        st.dataframe([{"url": p["url"], "outcome": p["outcome"], "http": p["http_status"], "title": p["title"] or ""}
                      for p in job["pages"]], hide_index=True,
                     column_config={"url": st.column_config.LinkColumn("url")})
