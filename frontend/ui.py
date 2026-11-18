"""Display helpers shared by all pages, so every page looks and words things the same way.

Look: the theme (colours, font, corners) is in .streamlit/config.toml; the small CSS block below adds
cards, badges, pills and blockquotes. Colour pairs were chosen for WCAG-AA contrast (>= 4.5:1 for text).

SAFETY: website text (quotes, explanations, company names) is untrusted. Anything we put inside our own
HTML goes through esc() first, so a page can never inject HTML or scripts into the UI.
"""
import html
from datetime import UTC, datetime

import streamlit as st

import api_client
from api_client import ApiError

APP_NAME = "Business Evidence Platform"
SUBTITLE = "Evidence-backed business-line research"

# Order used everywhere in the UI
CATEGORIES = ["accounting", "agronomy", "grain", "energy", "feed", "gas_station", "retail_store"]
CATEGORY_LABEL = {"accounting": "Accounting", "agronomy": "Agronomy", "grain": "Grain", "energy": "Energy",
                  "feed": "Feed", "gas_station": "Gas Station", "retail_store": "Retail Store"}
CATEGORY_ICON = {"accounting": "🧾", "agronomy": "🌱", "grain": "🌾", "energy": "🛢️", "feed": "🐄",
                 "gas_station": "⛽", "retail_store": "🏬"}
SHORT_LABEL = {"accounting": "Acct", "agronomy": "Agro", "grain": "Grain", "energy": "Energy", "feed": "Feed",
               "gas_station": "Gas", "retail_store": "Retail"}

# status -> (label, css class)   None = never scanned (NOT the same as "not found")
STATUS = {"yes": ("Yes", "yes"), "possible": ("Possible", "possible"), "not_found": ("Not found", "notfound"),
          None: ("Not scanned", "notscanned")}
# provenance -> (label, css class)
SOURCE = {"site": ("Website", "site"), "rule": ("Rule", "rule"), "human": ("Human", "human"),
          "test": ("Test data", "test"), None: ("-", "test")}
# Table cell colours (background, text) for the Companies table - same pairs as the badges
CELL_COLOURS = {"Yes": ("#DCEFE0", "#1B5E2B"), "Possible": ("#FCEBC7", "#6E4400"),
                "Not found": ("#E4E1D9", "#38342D"), "Not scanned": ("#F3F1EC", "#5A554C")}

ACTIVE_RUN = {"queued", "running", "cancelling"}
JOB_PILL = {"queued": "queued", "running": "running", "completed": "yes", "review_required": "possible",
            "failed": "failed", "cancelled": "notfound", "cancelling": "notfound"}

CSS = """
<style>
/* spacing */
.block-container {padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1200px;}  /* below Streamlit's top bar */
/* header */
.bep-brand {display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .5rem;
            border-bottom: 1px solid #D9D3C4; padding-bottom: .5rem; margin-bottom: .25rem;}
.bep-brand .name {font-weight: 700; color: #1F4D2B; font-size: 1.05rem;}
.bep-brand .sub {color: #5A554C; font-size: .85rem; margin-left: .4rem;}
.bep-chip {background: #E7EFE6; color: #1F4D2B; border-radius: 999px; padding: .15rem .7rem; font-size: .8rem;
           white-space: nowrap;}
/* badges + pills (text / background pairs >= 4.5:1) */
.bep-badge {display: inline-block; border-radius: 999px; padding: .1rem .6rem; font-size: .78rem; font-weight: 600;
            margin-right: .3rem; line-height: 1.5; white-space: nowrap;}
.bep-yes {background: #DCEFE0; color: #1B5E2B;}
.bep-possible {background: #FCEBC7; color: #6E4400;}
.bep-notfound {background: #E4E1D9; color: #38342D;}
.bep-notscanned {background: #F3F1EC; color: #5A554C; border: 1px dashed #B8B1A2;}
.bep-site {background: #DDE8F5; color: #1D4F80;}
.bep-rule {background: #ECE3F5; color: #5B3A86;}
.bep-human {background: #FDE6D6; color: #8A3B0A;}
.bep-test {background: #E4E1D9; color: #38342D;}
.bep-queued {background: #E4E1D9; color: #38342D;}
.bep-running {background: #DDE8F5; color: #1D4F80;}
.bep-failed {background: #F8DAD7; color: #8C1D13;}
/* quotes */
.bep-quote {border-left: 4px solid #2E6B3F; background: #F4F1EA; padding: .5rem .8rem; margin: .4rem 0 .1rem 0;
            border-radius: 0 8px 8px 0; color: #1F2A22; font-size: .92rem;}
.bep-source {color: #5A554C; font-size: .78rem; margin-bottom: .5rem; word-break: break-all;}
.bep-source a {color: #245C36;}
.bep-muted {color: #5A554C; font-size: .85rem;}
/* tables: header row */
[data-testid="stDataFrame"] {border-radius: 8px;}
</style>
"""


def esc(value) -> str:
    """HTML-escape any value before it goes into our own HTML (website text is untrusted)."""
    return html.escape("" if value is None else str(value), quote=True)


def inject_css() -> None:
    """The shared CSS (once per run, from app.py - Streamlit clears the page every run)."""
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, description: str) -> None:
    """App name + subtitle, the user / role chip, then the page title and a one-line description."""
    user = api_client.current_user()
    chip = f'<span class="bep-chip">👤 {esc(user.get("email"))} · {esc(user.get("role"))}</span>' if user else ""
    st.markdown(f'<div class="bep-brand"><div><span class="name">🌾 {APP_NAME}</span>'
                f'<span class="sub">{SUBTITLE}</span></div>{chip}</div>', unsafe_allow_html=True)
    st.title(title)
    st.caption(description)


def badge(label: str, css: str) -> str:
    return f'<span class="bep-badge bep-{css}">{esc(label)}</span>'


def status_label(status: str | None) -> str:
    return STATUS.get(status, (str(status), "notfound"))[0]


def status_badge(status: str | None) -> str:
    """HTML badge, e.g. <span class="bep-badge bep-yes">Yes</span>."""
    label, css = STATUS.get(status, (str(status), "notfound"))
    return badge(label, css)


def source_badge(provenance: str | None) -> str:
    label, css = SOURCE.get(provenance, (str(provenance), "test"))
    return badge(label, css)


def test_data_badge(company: dict) -> str:
    """'Test data' badge for fixture / synthetic companies (empty for real ones)."""
    return badge("Test data", "test") if company.get("is_test_data") else ""


def pills(counts: dict[str, int]) -> str:
    """Job-status counts as small coloured pills (only the non-zero ones)."""
    return " ".join(badge(f"{status.replace('_', ' ')}: {n}", JOB_PILL.get(status, "notfound"))
                    for status, n in counts.items() if n)


def quote_html(evidence: dict) -> str:
    """A verified quote as a blockquote + its source link and fetch time (all escaped)."""
    url = esc(evidence["source_url"])
    return (f'<div class="bep-quote">“{esc(evidence["quote"])}”</div>'
            f'<div class="bep-source">Source: <a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
            f' · fetched {esc(when(evidence.get("fetched_at")))}</div>')


def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


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
    html_block(" ".join(source_badge(p) for p in ("site", "rule", "human", "test")))
    st.caption("Website = crawled pages · Rule = business rule · Human = reviewer correction · "
               "Test data = local fixture / synthetic data")
