"""Small display helpers shared by all pages, so every page looks and words things the same way."""
from datetime import UTC, datetime

import streamlit as st

import api_client
from api_client import ApiError

# Order used everywhere in the UI
CATEGORIES = ["accounting", "agronomy", "grain", "energy", "feed", "gas_station", "retail_store"]
CATEGORY_LABEL = {"accounting": "Accounting", "agronomy": "Agronomy", "grain": "Grain", "energy": "Energy",
                  "feed": "Feed", "gas_station": "Gas Station", "retail_store": "Retail Store"}
SHORT_LABEL = {"accounting": "Acct", "agronomy": "Agro", "grain": "Grain", "energy": "Energy", "feed": "Feed",
               "gas_station": "Gas", "retail_store": "Retail"}

# status -> (label, colour)   None = never scanned (NOT the same as "not found")
STATUS = {"yes": ("Yes", "green"), "possible": ("Possible", "orange"), "not_found": ("Not found", "gray"),
          None: ("Not scanned", "gray")}
# provenance -> (label, colour)
SOURCE = {"site": ("Website", "blue"), "rule": ("Rule", "violet"), "human": ("Human", "orange"),
          "test": ("Test", "gray"), None: ("-", "gray")}

ACTIVE_RUN = {"queued", "running", "cancelling"}


def status_label(status: str | None) -> str:
    return STATUS.get(status, (str(status), "gray"))[0]


def status_badge(status: str | None) -> str:
    """Markdown badge, e.g. ':green-badge[Yes]'."""
    label, colour = STATUS.get(status, (str(status), "gray"))
    return f":{colour}-badge[{label}]"


def source_badge(provenance: str | None) -> str:
    label, colour = SOURCE.get(provenance, (str(provenance), "gray"))
    return f":{colour}-badge[{label}]"


def test_data_badge(company: dict) -> str:
    """Grey 'Test data' badge for fixture / synthetic companies (empty for real ones)."""
    return ":gray-badge[Test data]" if company.get("is_test_data") else ""


def when(value: str | None) -> str:
    """ISO timestamp from the API -> '2026-11-18 07:55 UTC' (or '-')."""
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def show_error(exc: ApiError) -> None:
    """The API's own message, so the user sees exactly what went wrong."""
    st.error(exc.message, icon=":material/error:")


def load(what: str, fn, *args, **kwargs):
    """Call the API with a spinner; on error show the message and stop this page."""
    try:
        with st.spinner(f"Loading {what}..."):
            return fn(*args, **kwargs)
    except ApiError as exc:
        show_error(exc)
        st.stop()


def start_research(company_ids: list[int], idempotency_key: str) -> dict | None:
    """POST /api/runs for these companies. Returns the new (or earlier, same-key) run, or None after
    showing why nothing started. The SAME key must be reused for repeated clicks, so a double click
    can never create two runs."""
    try:
        with st.spinner("Starting research..."):
            return api_client.post("/api/runs", json={"company_ids": company_ids},
                                   headers={"Idempotency-Key": idempotency_key})
    except ApiError as exc:
        busy = [s for s in exc.details.get("skipped") or [] if s.get("reason") == "already_in_progress"]
        if busy:  # 409 NOTHING_TO_RUN because a job is already queued / running for them
            st.warning(f"{exc.message} Research is already in progress "
                       f"({len(busy)} {'company' if len(busy) == 1 else 'companies'}) - see the Runs page.",
                       icon=":material/hourglass_top:")
        else:
            show_error(exc)
        return None


def run_started(run: dict, key: str) -> None:
    """Confirmation for a started run + a button that opens it on the Runs page."""
    again = "" if run.get("created", True) else " (started earlier - same run)"
    st.success(f"Run **#{run['run_id']}** started for {run['total_items']} "
               f"{'company' if run['total_items'] == 1 else 'companies'}{again}.")
    busy = [s for s in run.get("skipped") or [] if s["reason"] == "already_in_progress"]
    if busy:
        st.warning(f"{len(busy)} skipped: already in progress in another run.")
    if st.button(f"Open run #{run['run_id']}", icon=":material/open_in_new:", key=f"open_run_{key}"):
        st.session_state["run_id"] = run["run_id"]
        st.switch_page("views/runs.py")


def legend() -> None:
    st.caption("Sources: " + " ".join(source_badge(p) for p in ("site", "rule", "human", "test")))
    st.caption("Website = crawled pages · Rule = business rule · Human = reviewer correction · "
               "Test = local fixture data")
