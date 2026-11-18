"""Evidence selection: pick the passages worth sending to the AI.

Why: sending every crawled page would be slow, expensive and hit free-tier rate
limits. We send at most ~12,000 characters (roughly 3,000 tokens), chosen so
every category gets its best candidates:

1. Split each page's text into passages (~400 characters each).
2. Score every passage for each category = number of category keyword hits.
3. Take the homepage's first passage (what the company is), then the top
   passages of each category round-robin (best of each, then second best, ...)
   until the budget is used.

Deterministic: the same pages always give the same passages in the same order,
so a run can be reproduced.
"""
import textwrap
from dataclasses import dataclass

from app.classifier.taxonomy import SITE_CATEGORY_NAMES, keyword_hits
from app.crawler.crawl import is_duplicate
from app.db.enums import PageOutcome

MAX_PASSAGE_CHARS = 400
MIN_PASSAGE_CHARS = 30      # shorter fragments ("Home", "Contact us") carry no evidence
TOP_PER_CATEGORY = 5
TOTAL_BUDGET_CHARS = 12_000


@dataclass
class Passage:
    passage_id: str  # "P1", "P2", ... - the AI cites these
    page_id: int
    url: str
    text: str


def split_into_passages(text: str) -> list[str]:
    """Merge neighbouring short lines up to MAX_PASSAGE_CHARS; split over-long lines; drop tiny pieces."""
    pieces: list[str] = []
    current = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = textwrap.wrap(line, MAX_PASSAGE_CHARS) if len(line) > MAX_PASSAGE_CHARS else [line]
        for part in parts:
            if current and len(current) + 1 + len(part) > MAX_PASSAGE_CHARS:
                pieces.append(current)
                current = part
            else:
                current = f"{current}\n{part}" if current else part
    if current:
        pieces.append(current)
    return [p for p in pieces if len(p) >= MIN_PASSAGE_CHARS]


def select_passages(pages) -> list[Passage]:
    """`pages`: Page rows of one job. Returns the passages to send, numbered P1, P2, ..."""
    # Duplicate-text pages (same text as an earlier page) are skipped: the original is already included.
    usable = [p for p in pages if p.outcome == PageOutcome.OK and p.text_content and not is_duplicate(p)]
    usable.sort(key=lambda p: (p.depth, p.id))  # homepage first, then in crawl order (deterministic)

    # All candidate passages, in page order: (page, text)
    candidates = [(page, text) for page in usable for text in split_into_passages(page.text_content)]
    if not candidates:
        return []

    # Ranked candidate indexes per category (most keyword hits first; ties -> earlier passage first).
    ranked: dict[str, list[int]] = {}
    for category in SITE_CATEGORY_NAMES:
        scores = [(keyword_hits(category, text), i) for i, (_, text) in enumerate(candidates)]
        best = sorted((s for s in scores if s[0] > 0), key=lambda s: (-s[0], s[1]))[:TOP_PER_CATEGORY]
        ranked[category] = [i for _, i in best]

    # Order of picking: homepage context first, then round-robin over categories by rank.
    order = [0]
    for rank in range(TOP_PER_CATEGORY):
        for category in SITE_CATEGORY_NAMES:
            if rank < len(ranked[category]):
                order.append(ranked[category][rank])

    passages: list[Passage] = []
    used = 0
    taken: set[int] = set()
    for i in order:
        if i in taken:
            continue  # the same passage can be a top pick for several categories
        page, text = candidates[i]
        if used + len(text) > TOTAL_BUDGET_CHARS:
            break
        taken.add(i)
        used += len(text)
        passages.append(Passage(f"P{len(passages) + 1}", page.id, page.final_url or page.url, text))
    return passages
