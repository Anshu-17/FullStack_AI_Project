"""Trust nothing from the model: check its answer against what we actually crawled.

Rules (in this order, per category):
1. Every site category must appear exactly once        -> else InvalidModelOutput (retry)
   Size limits: explanation trimmed to 400 chars; only the first 3 quotes are used;
   quotes shorter than 10 or longer than 300 chars are dropped (issue)
2. Each quote must exist in the cited passage AND in the stored page text
   (whitespace-collapsed, case-insensitive)             -> else the quote is dropped (issue)
3. "yes"/"possible" with no verified quote left         -> "not_found"
4. "yes" whose verified quotes contain none of the category's keywords -> "possible"
   (a simple relevance heuristic: quoting "We love our community" is not grain evidence)
5. Evidence attached to "not_found" is ignored.
"""
from dataclasses import dataclass, field

from app.classifier.schema import ClassificationOutput
from app.classifier.select import Passage
from app.classifier.taxonomy import SITE_CATEGORY_NAMES, keyword_hits
from app.db.enums import ClassStatus, Provenance

MIN_QUOTE_CHARS, MAX_QUOTE_CHARS = 10, 300
MAX_QUOTES = 3
MAX_EXPLANATION_CHARS = 400


class InvalidModelOutput(Exception):
    """The answer is structurally wrong (missing / duplicated categories). Retryable."""


@dataclass
class CheckedEvidence:
    page_id: int
    source_url: str
    quote: str
    quote_verified: bool = True  # unverified quotes are dropped, so every kept quote is verified


@dataclass
class CheckedDecision:
    category: str
    status: str
    explanation: str
    confidence: float | None
    provenance: str = Provenance.SITE
    evidence: list[CheckedEvidence] = field(default_factory=list)


def _squash(text: str) -> str:
    """Whitespace-collapsed, lower-case: tolerate line breaks and capitalisation differences."""
    return " ".join(text.split()).lower()


def check_complete(output: ClassificationOutput) -> None:
    """Each of the 6 site categories exactly once."""
    names = [d.category for d in output.decisions]
    missing = [c for c in SITE_CATEGORY_NAMES if c not in names]
    duplicated = sorted({c for c in names if names.count(c) > 1})
    if missing or duplicated:
        raise InvalidModelOutput(f"missing categories {missing}, duplicated {duplicated}")


def validate(output: ClassificationOutput, passages: list[Passage], pages) -> tuple[list[CheckedDecision], list[str]]:
    """Return (decisions in fixed category order, list of human-readable issues)."""
    check_complete(output)
    passages_by_id = {p.passage_id: p for p in passages}
    page_text_by_id = {p.id: _squash(p.text_content or "") for p in pages}
    by_category = {d.category: d for d in output.decisions}

    decisions: list[CheckedDecision] = []
    issues: list[str] = []
    for category in SITE_CATEGORY_NAMES:
        d = by_category[category]
        checked = CheckedDecision(category, d.status, d.explanation.strip()[:MAX_EXPLANATION_CHARS], d.confidence)

        if d.status != ClassStatus.NOT_FOUND:
            if len(d.evidence) > MAX_QUOTES:
                issues.append(f"{category}: {len(d.evidence)} quotes given, only the first {MAX_QUOTES} used")
            for item in d.evidence[:MAX_QUOTES]:
                if not MIN_QUOTE_CHARS <= len(item.quote.strip()) <= MAX_QUOTE_CHARS:
                    issues.append(f"{category}: dropped a quote of {len(item.quote.strip())} characters "
                                  f"(allowed {MIN_QUOTE_CHARS}-{MAX_QUOTE_CHARS})")
                    continue
                passage = passages_by_id.get(item.passage_id)
                quote = _squash(item.quote)
                if (passage is None or quote not in _squash(passage.text)
                        or quote not in page_text_by_id.get(passage.page_id, "")):
                    issues.append(f"{category}: dropped a quote not found in passage {item.passage_id}: "
                                  f"\"{item.quote}\"")
                    continue
                checked.evidence.append(CheckedEvidence(passage.page_id, passage.url, item.quote.strip()))

            if not checked.evidence:
                issues.append(f"{category}: model said '{d.status}' but no quote could be verified -> not_found")
                checked.status = ClassStatus.NOT_FOUND
                checked.explanation = (f"Model claimed {d.status} but its evidence could not be verified "
                                       "in the crawled pages.")
            elif d.status == ClassStatus.YES and not any(keyword_hits(category, e.quote) for e in checked.evidence):
                issues.append(f"{category}: 'yes' quotes mention no {category} keyword -> possible")
                checked.status = ClassStatus.POSSIBLE

        decisions.append(checked)
    return decisions, issues
