"""Add companies: one website, or a CSV file; then start research for the upload (reviewers only)."""
import uuid

import streamlit as st

import api_client
import ui
from api_client import ApiError

st.title("Add companies")

if not api_client.is_reviewer():
    st.info("Only reviewers can add companies or start research.")
    st.stop()

SAMPLE_CSV = (
    "company_name,website\n"
    "Agtegra Cooperative,https://www.agtegra.com\n"
    "Insight FS,insightfs.com\n"
    "Example Farm Supply,https://www.example.com\n"
)

# ------------------------------------------------------------------ one website
st.subheader("One website")
with st.form("single", clear_on_submit=True):
    name = st.text_input("Company name")
    website = st.text_input("Website", placeholder="https://www.example.com")
    add = st.form_submit_button("Add company", type="primary")
if add:
    try:
        with st.spinner("Saving..."):
            result = api_client.post("/api/companies", json={"name": name, "website": website})
    except ApiError as exc:
        ui.show_error(exc)
    else:
        company = result["company"]
        if result["created"]:
            st.success(f"Created **{company['name']}** ({company['canonical_domain']}).")
        else:
            st.info(f"**{company['canonical_domain']}** already existed as **{company['name']}** - nothing duplicated.")

st.divider()

# ------------------------------------------------------------------ CSV upload
st.subheader("Upload a CSV")
st.caption("Columns: `company_name`, `website`. UTF-8, up to 5,000 rows / 2 MB.")
st.download_button("Download a sample CSV", SAMPLE_CSV, file_name="companies-sample.csv", mime="text/csv",
                   icon=":material/download:")

file = st.file_uploader("CSV file", type=["csv"])
if file is not None and st.button("Upload", type="primary", icon=":material/upload:"):
    try:
        with st.spinner("Checking rows..."):
            upload = api_client.upload_file(file.name, file.getvalue())
    except ApiError as exc:
        ui.show_error(exc)
    else:
        # One Idempotency-Key per upload, created now and reused for every click on "Start research":
        # a double click can never create two runs.
        st.session_state["last_upload"] = upload
        st.session_state["last_upload_key"] = f"upload-{upload['upload_id']}-{uuid.uuid4()}"
        st.session_state.pop("last_upload_run", None)

upload = st.session_state.get("last_upload")
if upload:
    counts = upload["counts"]
    st.markdown(f"**Upload #{upload['upload_id']}** ({upload['file_name']}) - {counts['total']} rows")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Accepted (new)", counts["accepted"])
    c2.metric("Existing", counts["existing"])
    c3.metric("Duplicate in file", counts["duplicate"])
    c4.metric("Invalid", counts["invalid"])
    if upload["rows"]:
        st.markdown("Rows that were not added as new companies:")
        st.dataframe([{"row": r["row_no"], "name": r["name"], "website": r["website"], "result": r["result"],
                       "reason": r["message"] or r["error_code"]} for r in upload["rows"]], hide_index=True)
    else:
        st.success("Every row was accepted.")

    if counts["accepted"] + counts["existing"] == 0:
        st.info("No valid companies in this upload - nothing to research.")
    elif st.button("Start research for this upload", type="primary", icon=":material/play_arrow:"):
        try:
            with st.spinner("Starting..."):
                st.session_state["last_upload_run"] = api_client.post(
                    "/api/runs", json={"upload_id": upload["upload_id"]},
                    headers={"Idempotency-Key": st.session_state["last_upload_key"]})
        except ApiError as exc:
            ui.show_error(exc)
            skipped = exc.details.get("skipped") or []
            if skipped:
                st.caption(f"{len(skipped)} companies are already being researched in another run.")

    run = st.session_state.get("last_upload_run")
    if run:
        st.success(f"Run **#{run['run_id']}** with {run['total_items']} companies"
                   + (" (already started earlier - same run)." if not run["created"] else " started."))
        busy = [s for s in run["skipped"] if s["reason"] == "already_in_progress"]
        if busy:
            st.warning(f"{len(busy)} companies skipped: already in progress in another run.")
        if st.button("Open this run", icon=":material/open_in_new:"):
            st.session_state["run_id"] = run["run_id"]
            st.switch_page("views/runs.py")
