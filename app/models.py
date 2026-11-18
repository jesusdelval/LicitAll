"""Normalized data models for tenders, criteria, and sync status."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class TenderRecord(BaseModel):
    """Normalized representation of a public tender from any source."""

    source: str
    external_id: str
    expediente: str
    title: str
    summary: str = ""
    contracting_authority: str = ""
    contract_type: str = ""
    procedure: str = ""
    status: str = ""
    budget_amount: Optional[float] = None
    estimated_value: Optional[float] = None
    currency: str = "EUR"
    published_at: Optional[str] = None
    updated_at: Optional[str] = None
    deadline_at: Optional[str] = None
    url: str = ""
    cpvs: list[str] = Field(default_factory=list)
    region: str = ""
    raw_hash: str = ""


class CriterionCreate(BaseModel):
    """Payload to create a CPV or keyword tracking criterion."""

    kind: str = Field(..., pattern="^(cpv|keyword)$")
    value: str = Field(..., min_length=1, max_length=120)
    label: str = Field(default="", max_length=160)
    active: bool = True


class CriterionToggle(BaseModel):
    """Payload to toggle a criterion active state."""

    active: bool


class SyncRequest(BaseModel):
    """Optional filter for triggering source synchronization."""

    sources: Optional[list[str]] = None
    max_pages: int = Field(default=200, ge=1, le=500)
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SavedFilterCreate(BaseModel):
    """Payload to save a named filter preset."""

    name: str = Field(..., min_length=1, max_length=100)
    filters: dict = Field(default_factory=dict)
