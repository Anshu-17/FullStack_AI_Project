"""The exact shape the AI must answer in (checked by Pydantic).

Kept deliberately plain (strings, enums as Literal, lists, numbers) so both
Gemini and Groq accept it as a JSON schema. Accounting is NOT in the allowed
categories - it is decided by a business rule, never by the model.

Hard rules here (wrong category / status / shape -> the whole answer is rejected and retried).
Size limits (quote 10-300 chars, max 3 quotes, explanation max 400 chars) are given to
the model in the descriptions but enforced per item in validate.py: one over-long quote
should cost that quote, not the whole answer. (Observed on a real run: a single
370-character quote made Gemini's otherwise good answer fail three times.)
"""
from typing import Literal

from pydantic import BaseModel, Field

SiteCategoryName = Literal["agronomy", "grain", "energy", "feed", "gas_station", "retail_store"]
StatusName = Literal["yes", "possible", "not_found"]


class EvidenceItem(BaseModel):
    passage_id: str = Field(description="ID of the passage the quote comes from, e.g. 'P3'")
    quote: str = Field(description="10 to 300 characters copied VERBATIM from that passage")


class CategoryDecision(BaseModel):
    category: SiteCategoryName
    status: StatusName
    explanation: str = Field(description="One or two sentences (max 400 characters): why this status")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="At most 3 quotes")
    confidence: float | None = Field(default=None, ge=0, le=1, description="Self-reported, 0 to 1")


class ClassificationOutput(BaseModel):
    decisions: list[CategoryDecision]
