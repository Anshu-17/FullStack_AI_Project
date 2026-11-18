"""Companies: search and filter on the FINAL answers, open a company, start research, export."""
import uuid

import pandas as pd
import streamlit as st

import api_client
import ui
from api_client import ApiError

ui.page_header("Companies", "Final answer per business line (a reviewer's correction wins). Filter, open a "
                            "company to see its evidence, start research, export.")

PAGE_SIZE = 25
STATUS_FILTER = {"Any": None, "Yes": "yes", "Possible": "possible", "Not found": "not_found"}


def cell_style(value: str) -> str:
    """Colour of an answer cell: 'Yes (H) ⚠' -> green, 'Possible' -> amber, ... (same colours as the badges)."""
    for label, (background, text) in ui.CELL_COLOURS.items():
        if str(value).startswith(label):
            return f"background-color: {background}; color: {text}; font-weight: 600"
    return ""


with st.container(border=True):
    f1, f2, f3 = st.columns([2, 1, 1])
    search = f1.text_input("Search name or website", placeholder="e.g. agtegra")
    category = f2.selectbox("Category", ["Any", *ui.CATEGORIES],
                            format_func=lambda c: c if c == "Any" else ui.CATEGORY_LABEL[c])
    status = f3.selectbox("Final answer", list(STATUS_FILTER))
    hide_test = st.checkbox("Hide test data", help="Fixture and synthetic companies used for testing")
filters = {"search": search, "category": None if category == "Any" else category, "status": STATUS_FILTER[status],
           "include_test": "false" if hide_test else None}
page = st.session_state.get("companies_page", 1)

data = ui.load("companies", api_client.get, "/api/companies", page=page, page_size=PAGE_SIZE, **filters)

if data["total"] == 0:
    st.info("No companies match." if any(v for k, v in filters.items() if k != "include_test")
            else "No companies yet. Add some on 'Add companies'.")
else:
    rows = []
    for c in data["items"]:
        job = c["latest_job"] or {}
        row = {"id": c["id"], "name": c["name"], "domain": c["canonical_domain"],
               "data": "Test data" if c.get("is_test_data") else "",
               "last scanned": ui.when(c["last_scanned_at"]), "latest job": job.get("status", "-")}
        for cat in ui.CATEGORIES:
            answer = c["answers"][cat]
            mark = " (H)" if answer["provenance"] == "human" else ""
            row[ui.SHORT_LABEL[cat]] = ui.status_label(answer["status"]) + mark + (" ⚠" if answer["conflict"] else "")
        rows.append(row)
    answer_columns = [ui.SHORT_LABEL[cat] for cat in ui.CATEGORIES]
    styled = pd.DataFrame(rows).style.map(cell_style, subset=answer_columns)
    st.dataframe(styled, hide_index=True, width="stretch",
                 column_config={"id": st.column_config.NumberColumn("id", width="small"),
                                "data": st.column_config.TextColumn("data", help="Test data = fixture / synthetic")})
    st.caption("(H) = corrected by a reviewer · ⚠ = the latest automated scan disagrees with the correction · "
               "Not scanned = never researched (not the same as Not found)")

    pages = max(1, -(-data["total"] // PAGE_SIZE))  # ceiling division
    p1, p2, p3 = st.columns([1, 2, 1])
    if p1.button("Previous", disabled=page <= 1):
        st.session_state["companies_page"] = page - 1
        st.rerun()
    p2.caption(f"Page {page} of {pages} · {data['total']} companies")
    if p3.button("Next", disabled=page >= pages):
        st.session_state["companies_page"] = page + 1
        st.rerun()

    choice = st.selectbox("Open company", [c["id"] for c in data["items"]],
                          format_func=lambda i: next(c["name"] for c in data["items"] if c["id"] == i))
    if st.button("Open details", type="primary", icon=":material/open_in_new:"):
        st.session_state["company_id"] = choice
        st.switch_page("views/company_detail.py")


def never_researched_ids() -> list[int]:
    """Ids of companies (matching the search / test-data filters) that have never had a job, from ALL pages."""
    ids, page_no = [], 1
    while True:
        batch = api_client.get("/api/companies", page=page_no, page_size=200, search=search,
                               include_test=filters["include_test"])
        ids += [c["id"] for c in batch["items"] if c["latest_job"] is None]
        if page_no * 200 >= batch["total"]:
            return ids
        page_no += 1


if api_client.is_reviewer() and data["total"]:
    st.divider()
    st.subheader("Research")
    if st.button("Start research for all not-scanned companies", icon=":material/play_arrow:", key="start_all",
                 help="Every company matching the search / test-data filters that has never been researched"):
        ids = ui.load("companies", never_researched_ids)  # on an API error: shows it and stops the page
        if not ids:
            st.info("Every matching company has already been researched (or is in progress).")
        else:
            # A fresh key for this click's batch; the backend still skips companies already in progress
            run = ui.start_research(ids, f"batch-{uuid.uuid4()}")
            if run:
                st.session_state["batch_run"] = run
    if st.session_state.get("batch_run"):
        ui.run_started(st.session_state["batch_run"], "batch")

st.divider()
st.subheader("Export")
st.caption("Exports use the filters above and contain the FINAL answers (a reviewer's correction wins).")
e1, e2, e3 = st.columns(3)
exports = {"csv": ("Companies CSV", "/api/exports", "csv"), "json": ("Companies JSON", "/api/exports", "json"),
           "corrections": ("Corrections CSV", "/api/exports/overrides", "csv")}
for column, (key, (label, path, fmt)) in zip((e1, e2, e3), exports.items(), strict=True):
    if column.button(f"Prepare {label}", key=f"prep_{key}"):
        try:
            params = {"format": fmt, **(filters if key != "corrections" else {})}
            with st.spinner("Preparing..."):
                st.session_state[f"export_{key}"] = api_client.download(path, **params)
        except ApiError as exc:
            ui.show_error(exc)
    if st.session_state.get(f"export_{key}"):
        column.download_button(f"Download {label}", st.session_state[f"export_{key}"],
                               file_name=f"{'corrections' if key == 'corrections' else 'companies'}.{fmt}",
                               mime="text/csv" if fmt == "csv" else "application/json", key=f"dl_{key}")
