"""Small display helpers shared by all pages, so every page looks and words things the same way."""
from datetime import UTC, datetime

import streamlit as st

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


def legend() -> None:
    st.caption("Sources: " + " ".join(source_badge(p) for p in ("site", "rule", "human", "test")))
    st.caption("Website = crawled pages · Rule = business rule · Human = reviewer correction · "
               "Test = local fixture data")
