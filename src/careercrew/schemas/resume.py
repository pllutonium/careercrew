"""Resume data models and strict output schemas for CareerCrew Resume Writer."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    """Base schema enforcing strict JSON schema compatibility for Groq open-weight models.

    Invariants:
    - extra = "forbid"
    - No dynamic dicts
    - No field-level constraints (e.g., min_length, max_length) that violate strict mode.
    """

    model_config = ConfigDict(extra="forbid")


class TailoredBullet(StrictBaseModel):
    """A single tailored resume bullet point with deterministic provenance tracking."""

    text: str = Field(
        description="The bullet point text formulated with Google X-Y-Z active framing."
    )
    source_ids: List[str] = Field(
        description="List of raw bullet IDs from candidate profile serving as factual basis."
    )


class TailoredSection(StrictBaseModel):
    """A section of the tailored resume (e.g. Work Experience, Education, Projects)."""

    section_name: str = Field(
        description="Name of the section, e.g., 'Work Experience' or 'Education'."
    )
    organization: Optional[str] = Field(
        default=None,
        description="Company, university, or client organization name.",
    )
    role_title: Optional[str] = Field(
        default=None,
        description="Job title, degree, or role designation.",
    )
    date_range: Optional[str] = Field(
        default=None,
        description="Employment or degree timeframe (e.g., '2021 - 2024').",
    )
    bullets: List[TailoredBullet] = Field(
        default_factory=list,
        description="Tailored bullet points belonging to this section.",
    )


class TailoredResume(StrictBaseModel):
    """Complete tailored resume draft produced by the Resume Writer Agent."""

    version: int = Field(
        default=1,
        description="Schema or iteration version number.",
    )
    summary: TailoredBullet = Field(
        description="Tailored executive summary with explicit source_ids grounding."
    )
    sections: List[TailoredSection] = Field(
        default_factory=list,
        description="List of tailored sections (Experience, Projects, Education, etc.).",
    )


class RepairedBullet(StrictBaseModel):
    """Repaired bullet returned by the LLM during critic delta-repair loops."""

    bullet_id: str = Field(
        description="Target bullet identifier being repaired (e.g. 'summary' or 'sec_0_b_1')."
    )
    text: str = Field(
        description="Repaired bullet text adhering strictly to source facts and critique."
    )
    source_ids: List[str] = Field(
        description="List of verified profile bullet IDs supporting this repaired bullet."
    )


class DeltaRepairOutput(StrictBaseModel):
    """Structured LLM output for surgical repair of critic-rejected bullets."""

    repaired_bullets: List[RepairedBullet] = Field(
        default_factory=list,
        description="List of surgically repaired bullets mapped to their identifiers.",
    )
