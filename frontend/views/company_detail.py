"""Company detail: header card, the 7 final answers as cards with evidence, reviewer corrections, history.

Every website-derived string (quote, explanation, name, URL) is escaped by ui.esc() before it goes into HTML.
"""
import uuid

import streamlit as st

import api_client
import ui
from api_client import ApiError

company_id = st.session_state.get("company_id")
if not company_id:
    ui.page_header("Company detail", "Evidence, answers and corrections for one company.")
    st.info("Choose a company on the Companies page first.")
    st.page_link("views/companies.py", label="Go to Companies", icon=":material/table_view:")
    st.stop()

company = ui.load("company", api_client.get, f"/api/companies/{company_id}")
history = ui.load("corrections", api_client.get, f"/api/companies/{company_id}/overrides")["items"]
scans = company["scan_history"]
latest_job = scans[0] if scans else None
last_scanned = next((j["finished_at"] for j in scans if j["status"] in ("completed", "review_required")), None)

ui.page_header(company["name"], "Final answers with their verified evidence. A reviewer's correction wins over "
                                "the automated scan; disagreements are flagged.")

# ------------------------------------------------------------------ header card
with st.container(border=True):
    info, action = st.columns([3, 1], vertical_alignment="center")
    with info:
        job_status = latest_job["status"] if latest_job else None
        job_badge = ui.badge(job_status.replace("_", " "), ui.JOB_PILL.get(job_status, "notfound")) if job_status \
            else ui.badge("never scanned", "notscanned")
        url = ui.esc(company["website_url"])
        ui.html_block(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a> '
                      f'{ui.test_data_badge(company)}<br>'
                      f'<span class="bep-muted">Last scanned <b>{ui.esc(ui.when(last_scanned))}</b> · latest job</span> '
                      f'{job_badge}')
        if company.get("is_test_data"):
            st.caption(f"This is test data ({company['source']}), not a real company.")
    with action:
        if api_client.is_reviewer():
            # "Start research" for a company never scanned, "Rescan" otherwise. One Idempotency-Key per click.
            label, icon = ("Rescan this company", ":material/refresh:") if scans else \
                ("Start research", ":material/play_arrow:")
            if st.button(label, type="primary", icon=icon, key="rescan", width="stretch"):
                run = ui.start_research([company_id], f"rescan-{company_id}-{uuid.uuid4()}")
                if run:
                    st.session_state["detail_run"] = {**run, "company_id": company_id}
started = st.session_state.get("detail_run")
if started and started["company_id"] == company_id:
    ui.run_started(started, "detail")

# ------------------------------------------------------------------ the 7 answers (3 per row; 1 per row on a phone)
NEW_STATUS = {"Yes": "yes", "Possible": "possible", "Not found": "not_found", "Remove correction": None}


def answer_card(answer: dict) -> None:
    cat = answer["category"]
    automated = answer["automated"]
    with st.container(border=True):
        ui.html_block(f'<div style="font-weight:700;font-size:1.05rem;margin-bottom:.3rem">'
                      f'{ui.CATEGORY_ICON[cat]} {ui.CATEGORY_LABEL[cat]}</div>'
                      f'{ui.status_badge(answer["status"])}{ui.source_badge(answer["provenance"])}')
        st.caption(answer["explanation"])

        if answer["conflict"] and automated:
            st.warning(f"Conflicts with the latest automated scan: the scan says "
                       f"**{ui.status_label(automated['status'])}**, the reviewer says "
                       f"**{ui.status_label(answer['status'])}**. The reviewer's answer is shown.", icon="⚠️")
        if answer["provenance"] == "human" and automated:
            st.caption(f"Automated answer: {ui.status_label(automated['status'])} — {automated['explanation']}")

        if automated:
            for e in automated.get("evidence") or []:
                ui.html_block(ui.quote_html(e))
            model = f"{automated['model_provider']} / {automated['model_name']}" if automated["model_provider"] \
                else "business rule"
            st.caption(f"Model: {model} · prompt {automated['prompt_version'] or '-'} · "
                       f"policy {automated['policy_version']}")

        if api_client.is_reviewer():
            with st.expander("Correct this answer", icon=":material/edit:"):
                with st.form(f"correct_{cat}", clear_on_submit=True):
                    choice = st.selectbox("New answer", list(NEW_STATUS), key=f"new_{cat}")
                    reason = st.text_area("Reason (required)", key=f"reason_{cat}", max_chars=1000)
                    save = st.form_submit_button("Save correction", type="primary")
                if save:
                    try:
                        api_client.post(f"/api/companies/{company_id}/overrides", json={
                            "category": cat, "new_status": NEW_STATUS[choice], "reason": reason,
                            "expected_version": answer["version"]})  # optimistic locking: the version shown
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


st.subheader("Answers")
answers = company["answers"]
for start in range(0, len(answers), 3):
    for column, answer in zip(st.columns(3), answers[start:start + 3], strict=False):
        with column:
            answer_card(answer)

# ------------------------------------------------------------------ history
with st.container(border=True):
    st.subheader("Correction history")
    if not history:
        st.info("No corrections yet.")
    else:
        st.dataframe([{"when": ui.when(h["created_at"]), "category": ui.CATEGORY_LABEL[h["category"]],
                       "change": f"{ui.status_label(h['old_status'])} → "
                                 f"{ui.status_label(h['new_status']) if h['new_status'] else 'correction removed'}",
                       "reason": h["reason"], "reviewer": h["reviewer_email"], "version": h["version"]}
                      for h in history], hide_index=True, width="stretch")

with st.container(border=True):
    st.subheader("Scan history")
    if not scans:
        st.info("This company has not been scanned yet.")
    else:
        st.dataframe([{"job": j["id"], "run": j["run_id"], "status": j["status"], "attempts": j["attempt_count"],
                       "error": j["last_error_code"] or "", "started": ui.when(j["started_at"]),
                       "finished": ui.when(j["finished_at"])} for j in scans], hide_index=True, width="stretch")
