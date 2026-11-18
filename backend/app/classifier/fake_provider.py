"""TEST-ONLY "fake" AI provider: deterministic, keyword-based, no network, no cost.

Used for controlled load tests (many jobs without spending real AI quota). It reads the same
prompt a real model gets, and for each category picks the passage line with the most keyword
hits and quotes it VERBATIM, so its answers go through exactly the same validation as a real
model's. It never uses judgement (no "possible", no special rules) - it is NOT a classifier
to trust, only a stand-in for load and plumbing tests.

Refused when ENVIRONMENT=production (see providers.py).
"""
import re

from langchain_core.messages import AIMessage

from app.classifier.prompts import UNTRUSTED_TAG
from app.classifier.schema import ClassificationOutput
from app.classifier.taxonomy import SITE_CATEGORY_NAMES, keyword_hits

MODEL_NAME = "fake-keyword-v1"
PASSAGE_RE = re.compile(r"\[(P\d+)\] \([^)]*\)\n(.*?)(?=\n\n\[P\d+\] \(|\n</" + UNTRUSTED_TAG + ">)", re.S)


def _passages(messages) -> list[tuple[str, str]]:
    """[(passage_id, text)] parsed from the user message built by prompts.build_messages."""
    user = next(content for role, content in messages if role == "human")
    return PASSAGE_RE.findall(user)


def _best_quote(category: str, passages: list[tuple[str, str]]) -> tuple[str, str] | None:
    best = None  # (hits, passage_id, line)
    for pid, text in passages:
        for line in text.splitlines():
            hits = keyword_hits(category, line)
            if hits and (best is None or hits > best[0]):
                best = (hits, pid, line.strip()[:300])
    return (best[1], best[2]) if best else None


class FakeKeywordModel:
    """Same interface as a LangChain structured model with include_raw=True."""

    def invoke(self, messages) -> dict:
        passages = _passages(messages)
        decisions = []
        for category in SITE_CATEGORY_NAMES:
            found = _best_quote(category, passages)
            if found:
                pid, quote = found
                decisions.append({"category": category, "status": "yes", "confidence": 0.5,
                                  "explanation": "Keyword match (fake test provider).",
                                  "evidence": [{"passage_id": pid, "quote": quote}]})
            else:
                decisions.append({"category": category, "status": "not_found", "evidence": [],
                                  "explanation": "No keyword found (fake test provider)."})
        parsed = ClassificationOutput.model_validate({"decisions": decisions})
        # No tokens are reported: the fake provider uses none (never invent usage numbers).
        return {"raw": AIMessage(content=""), "parsed": parsed, "parsing_error": None}
