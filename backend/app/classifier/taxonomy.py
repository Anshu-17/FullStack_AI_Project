"""The business-line taxonomy (policy v1): what each category means and how we recognise it.

Six categories are decided from website evidence by the AI. Accounting is NOT
sent to the AI: the brief's default policy says Accounting = Yes for every
company, so it is a fixed business rule with provenance "rule".

The keywords are used twice:
- select.py:   to pick the passages most likely to contain evidence (cost control)
- validate.py: as a simple relevance check on the AI's quotes (a "yes" whose
               quotes mention none of the category's words is downgraded)
"""
import re
from dataclasses import dataclass

from app.config import settings
from app.db.enums import Category, ClassStatus, Provenance

POLICY_VERSION = settings.policy_version  # "v1"
PROMPT_VERSION = settings.prompt_version  # "p1"


@dataclass(frozen=True)
class SiteCategory:
    name: str
    label: str
    definition: str
    rule: str                  # the brief's special rule for this category
    keywords: tuple[str, ...]  # matched at the START of a word, case-insensitive ("fertiliz" matches "fertilizers")


SITE_CATEGORIES: dict[str, SiteCategory] = {
    str(c.name): c
    for c in (
        SiteCategory(
            Category.AGRONOMY, "Agronomy",
            "Sells crop inputs or agronomy services: seed, fertilizer, crop protection, custom application, "
            "soil sampling, precision agriculture.",
            "The company must SELL these goods or services; a passing mention of crops or farming is not enough.",
            ("agronom", "seed", "fertiliz", "fertilis", "crop protection", "crop input", "crop nutrient", "herbicide",
             "fungicide", "insecticide", "chemical", "custom appl", "applicat", "spraying", "soil sampl",
             "soil test", "precision ag", "nutrient"),
        ),
        SiteCategory(
            Category.GRAIN, "Grain",
            "Commercial grain services: buying, handling, storage, elevators, cash bids, merchandising, "
            "grain marketing, contracts.",
            "Grain farming alone is not commercial grain services.",
            ("grain", "elevator", "cash bid", "bids", "merchandis", "bushel", "futures", "basis", "corn", "soybean",
             "wheat", "harvest", "storage"),
        ),
        SiteCategory(
            Category.ENERGY, "Energy",
            "Sells energy products: propane, diesel, gasoline, heating fuels, oils, lubricants, bulk fuel delivery.",
            "Wholesale or bulk delivery does not by itself prove retail fuel pumps (that is Gas Station).",
            ("propane", "diesel", "gasoline", "fuel", "heating oil", "oil", "lubricant", "energy", "bulk deliver",
             "ethanol", "biodiesel"),
        ),
        SiteCategory(
            Category.FEED, "Feed",
            "Livestock feed and animal nutrition: feed mills, bulk or bagged feed, minerals, supplements.",
            "Pet supplies alone do not qualify.",
            ("feed", "livestock", "animal nutrition", "nutrition", "cattle", "swine", "hog", "poultry", "dairy",
             "mineral", "supplement", "ration", "mill"),
        ),
        SiteCategory(
            Category.GAS_STATION, "Gas Station",
            "Operates public or member fueling sites: unattended pumps, cardlock, convenience stores with pumps.",
            "Needs a fueling-SITE signal (a place where vehicles are fuelled), not just fuel delivery.",
            ("cardlock", "card lock", "fueling", "fuel station", "fuel site", "gas station", "pump", "c-store",
             "convenience store", "24/7", "24 hour", "unattended", "pay at the pump"),
        ),
        SiteCategory(
            Category.RETAIL_STORE, "Retail Store",
            "Physical locations selling general goods: farm supplies, hardware, lumber, convenience goods.",
            "An online catalog alone is not enough; there must be a physical store signal (address, hours, visit us).",
            ("store", "retail", "hardware", "lumber", "farm supply", "farm store", "shop", "convenience",
             "hours", "location", "visit us", "open monday", "mon-fri"),
        ),
    )
}

SITE_CATEGORY_NAMES: tuple[str, ...] = tuple(SITE_CATEGORIES)  # fixed order, used everywhere

# One regex per category: \b = start of a word, so "oil" matches "oils" but not "soil".
_KEYWORD_PATTERNS = {
    name: re.compile(r"\b(?:" + "|".join(re.escape(k) for k in cat.keywords) + ")", re.IGNORECASE)
    for name, cat in SITE_CATEGORIES.items()
}


def keyword_hits(category: str, text: str) -> int:
    """How many times the category's keywords appear in `text`."""
    return len(_KEYWORD_PATTERNS[category].findall(text))


def accounting_rule_decision() -> dict:
    """Accounting = Yes for every company, by explicit business rule (not by the AI, no evidence)."""
    return {
        "category": str(Category.ACCOUNTING),
        "status": str(ClassStatus.YES),
        "provenance": str(Provenance.RULE),
        "explanation": f"Default assessment policy {POLICY_VERSION}: Accounting = Yes by explicit business rule.",
    }
