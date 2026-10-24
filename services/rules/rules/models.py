"""Wire shapes of the rules service (interfaces-v1 §17; `Citation` matches `AskCitation` in `ctl.schema.json`)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RuleDoc(BaseModel):
    """One dataset item from the Apify actor (one numbered clause, or one chunk of a long clause)."""

    sport: str
    rule_id: str
    number: str = ""
    title: str = ""
    text: str
    url: str = ""
    source: str = ""
    section_path: list[str] = []
    license_note: str = ""


class RuleHit(BaseModel):
    """A retrieved clause."""

    rule_id: str
    sport: str
    number: str
    title: str
    url: str
    source: str
    text: str
    score: float


class Citation(BaseModel):
    rule_id: str
    title: str
    url: str
    quote: str = Field(description="verbatim, <= 25 words")


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    sport: str = Field(min_length=1, max_length=40)


class AskOut(BaseModel):
    answer: str
    speech: str
    citations: list[Citation]
    found: bool
    moss_ms: float
    llm_ms: float
    latency_ms: float
    model: str
    top_score: float | None = None
    retrieved: list[str] = []  # rule ids Moss returned, for the dashboard and the eval


class RuleRefIn(BaseModel):
    sport: str = Field(min_length=1, max_length=40)
    rule_ref: str | None = Field(default=None, max_length=80, description='e.g. "ITTF 2.6.2"')
    rule_id: str | None = Field(default=None, max_length=80, description='e.g. "ittf:2.6.2"')
    text: str | None = Field(default=None, max_length=2000, description="rule name + text, for a search")


class RuleRefOut(BaseModel):
    rule_id: str
    title: str
    url: str
    quote: str
    score: float
    how: str  # "exact" | "search"
