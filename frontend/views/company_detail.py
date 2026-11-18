"""Company detail: the 7 final answers with evidence, reviewer corrections, history, rescan."""
import uuid

import streamlit as st

import api_client
import ui
from api_client import ApiError

company_id = st.session_state.get("company_id")
if not company_id:
    st.title("Company detail")
    st.info("Choose a company on the Companies page first.")
    st.page_link("views/companies.py", label="Go to Companies", icon=":material/list:")
    st.stop()

company = ui.load("company", api_client.get, f"/api/companies/{company_id}")
history = ui.load("corrections", api_client.get, f"/api/companies/{company_id}/overrides")["items"]
scans = company["scan_history"]
latest_job = scans[0] if scans else None
last_scanned = next((j["finished_at"] for j in scans if j["status"] in ("completed", "review_required")), None)

# ------------------------------------------------------------------ header
st.title(company["name"])
if company.get("is_test_data"):
    st.markdown(f"{ui.test_data_badge(company)} This is test data ({company['source']}), not a real company.")
st.markdown(f"[{company['website_url']}]({company['website_url']}) · last scanned **{ui.when(last_scanned)}** · "
            f"latest job: **{latest_job['status'] if latest_job else 'never scanned'}**")
if api_client.is_reviewer() and st.button("Rescan this company", icon=":material/refresh:"):
    try:
        run = api_client.post(f"/api/companies/{company_id}/rescan", headers={"Idempotency-Key": str(uuid.uuid4())})
        st.success(f"Rescan started: run #{run['run_id']}.")
    except ApiError as exc:
        ui.show_error(exc)

# ------------------------------------------------------------------ the 7 answers
NEW_STATUS = {"Yes": "yes", "Possible": "possible", "Not found": "not_found", "Remove correction": None}

st.subheader("Answers")
for answer in company["answers"]:
    cat = answer["category"]
    title = f"{ui.CATEGORY_LABEL[cat]} — {ui.status_label(answer['status'])}"
    with st.expander(title, expanded=answer["status"] in ("yes", "possible") or answer["conflict"]):
        st.markdown(f"{ui.status_badge(answer['status'])} {ui.source_badge(answer['provenance'])}")
        st.write(answer["explanation"])

        automated = answer["automated"]
        if answer["conflict"] and automated:
            st.warning(f"⚠ Conflicts with the latest automated scan: the scan says "
                       f"**{ui.status_label(automated['status'])}**, the reviewer says "
                       f"**{ui.status_label(answer['status'])}**. The reviewer's answer is shown.")
        if answer["provenance"] == "human" and automated:
            st.caption(f"Automated answer: {ui.status_label(automated['status'])} — {automated['explanation']}")

        if automated:
            for e in automated.get("evidence") or []:
                st.markdown(f"> {e['quote']}")
                st.caption(f"Source: [{e['source_url']}]({e['source_url']}) · fetched {ui.when(e['fetched_at'])}")
            model = f"{automated['model_provider']} / {automated['model_name']}" if automated["model_provider"] \
                else "business rule"
            st.caption(f"Model: {model} · prompt {automated['prompt_version'] or '-'} · "
                       f"policy {automated['policy_version']}")

        if api_client.is_reviewer():
            with st.form(f"correct_{cat}", clear_on_submit=True):
                st.markdown("**Correct this answer**")
                choice = st.selectbox("New answer", list(NEW_STATUS), key=f"new_{cat}")
                reason = st.text_area("Reason (required)", key=f"reason_{cat}", max_chars=1000)
                save = st.form_submit_button("Save correction")
            if save:
                try:
                    api_client.post(f"/api/companies/{company_id}/overrides", json={
                        "category": cat, "new_status": NEW_STATUS[choice], "reason": reason,
                        "expected_version": answer["version"]})  # optimistic locking: the version shown here
                except ApiError as exc:
                    if exc.code == "VERSION_CONFLICT":
                        d = exc.details
                        st.error(f"Someone else changed this answer (by {d.get('changed_by')} at "
                                 f"{ui.when(d.get('changed_at'))}). Reload to see it.")
                        if st.button("Reload", key=f"reload_{cat}"):
                            st.rerun()
                    else:
                        ui.show_error(exc)
                else:
                    st.success("Correction saved.")
                    st.rerun()

# ------------------------------------------------------------------ history
st.subheader("Correction history")
if not history:
    st.info("No corrections yet.")
else:
    st.dataframe([{"when": ui.when(h["created_at"]), "category": ui.CATEGORY_LABEL[h["category"]],
                   "change": f"{ui.status_label(h['old_status'])} → "
                             f"{ui.status_label(h['new_status']) if h['new_status'] else 'correction removed'}",
                   "reason": h["reason"], "reviewer": h["reviewer_email"], "version": h["version"]}
                  for h in history], hide_index=True)

st.subheader("Scan history")
if not scans:
    st.info("This company has not been scanned yet.")
else:
    st.dataframe([{"job": j["id"], "run": j["run_id"], "status": j["status"], "attempts": j["attempt_count"],
                   "error": j["last_error_code"] or "", "started": ui.when(j["started_at"]),
                   "finished": ui.when(j["finished_at"])} for j in scans], hide_index=True)
