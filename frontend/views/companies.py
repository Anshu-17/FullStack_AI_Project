"""Companies: search and filter on the FINAL answers, open a company, export."""
import streamlit as st

import api_client
import ui
from api_client import ApiError

st.title("Companies")

PAGE_SIZE = 25
STATUS_FILTER = {"Any": None, "Yes": "yes", "Possible": "possible", "Not found": "not_found"}

f1, f2, f3 = st.columns([2, 1, 1])
search = f1.text_input("Search name or website")
category = f2.selectbox("Category", ["Any", *ui.CATEGORIES],
                        format_func=lambda c: c if c == "Any" else ui.CATEGORY_LABEL[c])
status = f3.selectbox("Final answer", list(STATUS_FILTER))
filters = {"search": search, "category": None if category == "Any" else category, "status": STATUS_FILTER[status]}
page = st.session_state.get("companies_page", 1)

data = ui.load("companies", api_client.get, "/api/companies", page=page, page_size=PAGE_SIZE, **filters)

if data["total"] == 0:
    st.info("No companies match." if any(filters.values()) else "No companies yet. Add some on 'Add companies'.")
else:
    rows = []
    for c in data["items"]:
        job = c["latest_job"] or {}
        row = {"id": c["id"], "name": c["name"], "domain": c["canonical_domain"],
               "last scanned": ui.when(c["last_scanned_at"]), "latest job": job.get("status", "-")}
        for cat in ui.CATEGORIES:
            answer = c["answers"][cat]
            mark = " (H)" if answer["provenance"] == "human" else ""
            row[ui.SHORT_LABEL[cat]] = ui.status_label(answer["status"]) + mark + (" ⚠" if answer["conflict"] else "")
        rows.append(row)
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("(H) = corrected by a reviewer · ⚠ = the latest automated scan disagrees with the correction")

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
