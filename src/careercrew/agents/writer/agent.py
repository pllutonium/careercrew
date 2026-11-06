"""Resume Writer Agent implementation for CareerCrew multi-agent platform."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict, Union

from jinja2 import Environment, FileSystemLoader
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from careercrew.schemas.resume import (
    DeltaRepairOutput,
    TailoredBullet,
    TailoredResume,
)


class GraphState(TypedDict, total=False):
    """LangGraph shared state contract for CareerCrew workflow."""

    profile: Any
    job: Dict[str, Any]
    gap: Dict[str, Any]
    round: int
    critique: Optional[Any]
    draft: Optional[Union[TailoredResume, Dict[str, Any]]]
    llm: Optional[BaseChatModel]


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def extract_profile_facts(profile: Any) -> Dict[str, str]:
    """Recursively harvest all raw factual bullet IDs and their text from the profile."""
    facts: Dict[str, str] = {}

    # Handle Pydantic model
    if hasattr(profile, "model_dump"):
        data = profile.model_dump()
    elif isinstance(profile, dict):
        data = profile
    else:
        data = {}

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if "id" in node and isinstance(node["id"], str):
                text_val = (
                    node.get("text")
                    or node.get("content")
                    or node.get("bullet")
                    or node.get("summary")
                    or ""
                )
                facts[node["id"]] = str(text_val).strip()
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return facts


def validate_writer_output(draft: TailoredResume, profile: Any) -> None:
    """Hard Deterministic Verification:
    - Assert that len(bullet.source_ids) > 0 for every bullet in every section (and summary).
    - Collect all existing bullet IDs from profile.experiences, profile.projects, etc.
    - Assert that every string in bullet.source_ids exists in the collected set of valid IDs.
    - Raise a descriptive ValueError if any ID is hallucinated or missing.
    """
    profile_facts = extract_profile_facts(profile)
    valid_ids: Set[str] = set(profile_facts.keys())

    # 1. Validate Executive Summary
    if not draft.summary:
        msg = "Deterministic Verification Failed: Resume draft is missing an executive summary."
        raise ValueError(msg)
    if not draft.summary.source_ids or len(draft.summary.source_ids) == 0:
        msg = (
            f"Deterministic Verification Failed: Executive summary bullet has empty source_ids: "
            f"'{draft.summary.text}'"
        )
        raise ValueError(msg)
    for src_id in draft.summary.source_ids:
        if valid_ids and src_id not in valid_ids:
            msg = (
                f"Deterministic Verification Failed: Summary references hallucinated source_id "
                f"'{src_id}' not found in candidate profile."
            )
            raise ValueError(msg)

    # 2. Validate all Sections and Bullets
    for sec_idx, section in enumerate(draft.sections):
        if not section.bullets or len(section.bullets) == 0:
            continue
        for b_idx, bullet in enumerate(section.bullets):
            if not bullet.source_ids or len(bullet.source_ids) == 0:
                msg = (
                    f"Deterministic Verification Failed: Section '{section.section_name}' "
                    f"bullet {b_idx} has empty source_ids: '{bullet.text}'"
                )
                raise ValueError(msg)
            for src_id in bullet.source_ids:
                if valid_ids and src_id not in valid_ids:
                    msg = (
                        f"Deterministic Verification Failed: Section '{section.section_name}' "
                        f"bullet {b_idx} references hallucinated source_id '{src_id}' "
                        f"not found in candidate profile."
                    )
                    raise ValueError(msg)


# Backwards compatibility alias
validate_draft = validate_writer_output


def get_default_llm() -> BaseChatModel:
    """Instantiate the Groq LLM under architectural engine constraints."""
    return ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.4,
        model_kwargs={"reasoning_effort": "medium"},
    )


class ResumeWriterAgent:
    """Orchestrates initial draft generation and surgical delta-repair loops."""

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or get_default_llm()
        self.system_template = _jinja_env.get_template("system.md")
        self.task_template = _jinja_env.get_template("task.md")

    def _to_resume_model(
        self, draft_data: Union[TailoredResume, Dict[str, Any]]
    ) -> TailoredResume:
        if isinstance(draft_data, TailoredResume):
            return draft_data
        return TailoredResume.model_validate(draft_data)

    def generate_initial_draft(
        self,
        profile: Any,
        job: Dict[str, Any],
        gap: Dict[str, Any],
    ) -> TailoredResume:
        """Generates the initial tailored resume draft (Round 0)."""
        system_content = self.system_template.render()

        # Enforce compact JSON to stay strictly within 6,000 token budget
        if hasattr(profile, "model_dump"):
            profile_dict = profile.model_dump()
        else:
            profile_dict = profile

        compact_profile = json.dumps(profile_dict, separators=(",", ":"), ensure_ascii=False)
        task_content = self.task_template.render(
            mode="initial",
            job=job,
            gap=gap,
            profile_json=compact_profile,
        )

        structured_llm = self.llm.with_structured_output(
            TailoredResume,
            method="json_schema",
            strict=True,
        )

        # Prompt Caching: Static system instructions first, dynamic data last
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=task_content),
        ]
        result = structured_llm.invoke(messages)
        draft = self._to_resume_model(result)
        draft.version = 1
        return draft

    def _index_draft_bullets(
        self, draft: TailoredResume
    ) -> Tuple[Dict[str, TailoredBullet], Dict[str, Tuple[Optional[int], int]]]:
        """Maps bullet identifiers to draft bullet instances and their positional coordinates."""
        bullet_map: Dict[str, TailoredBullet] = {}
        pos_map: Dict[str, Tuple[Optional[int], int]] = {}

        # Summary bullet
        bullet_map["summary"] = draft.summary
        pos_map["summary"] = (None, 0)

        for s_idx, section in enumerate(draft.sections):
            for b_idx, bullet in enumerate(section.bullets):
                b_id = f"sec_{s_idx}_b_{b_idx}"
                bullet_map[b_id] = bullet
                pos_map[b_id] = (s_idx, b_idx)

        return bullet_map, pos_map

    def delta_repair(
        self,
        draft: TailoredResume,
        profile: Any,
        critique: Any,
    ) -> TailoredResume:
        """Delta-Repair Algorithm:
        1. Inspect critique. If passed, bypass regeneration and return unchanged.
        2. Inspect critique.claim_checks. Identify bullets flagged as unsupported or partial.
        3. Keep all supported bullets locked.
        4. Send prompt with ONLY flagged bullets, their source facts, and Critic feedback.
        5. Surgically re-integrate repaired bullets into exact section indices without
           disturbing supported bullets.
        """
        # 1. Bypass if critique passed
        is_passed = getattr(critique, "passed", None)
        if is_passed is None and isinstance(critique, dict):
            is_passed = critique.get("passed", False)

        if is_passed is True:
            return draft

        profile_facts = extract_profile_facts(profile)
        bullet_map, _ = self._index_draft_bullets(draft)

        # 2. Extract claim checks
        claim_checks = getattr(critique, "claim_checks", None)
        if claim_checks is None and isinstance(critique, dict):
            claim_checks = (
                critique.get("claim_checks")
                or critique.get("bullets")
                or critique.get("critiques")
                or []
            )
        elif claim_checks is None:
            claim_checks = []

        flagged_items: List[Dict[str, Any]] = []

        for chk in claim_checks:
            # Determine status
            status = ""
            if hasattr(chk, "status"):
                status = str(chk.status or "").lower()
            elif hasattr(chk, "verdict"):
                status = str(chk.verdict or "").lower()
            elif isinstance(chk, dict):
                status = str(chk.get("status") or chk.get("verdict") or "").lower()

            # Keep supported bullets locked; process only unsupported or partial
            if status in ("unsupported", "partial"):
                b_id = None
                if hasattr(chk, "bullet_id"):
                    b_id = chk.bullet_id
                elif hasattr(chk, "claim_id"):
                    b_id = chk.claim_id
                elif isinstance(chk, dict):
                    b_id = chk.get("bullet_id") or chk.get("claim_id")

                target_bullet: Optional[TailoredBullet] = None

                if b_id and b_id in bullet_map:
                    target_bullet = bullet_map[b_id]
                else:
                    # Match by section and bullet indices if provided
                    s_idx = getattr(chk, "section_idx", None) if hasattr(chk, "section_idx") else (
                        chk.get("section_idx") if isinstance(chk, dict) else None
                    )
                    b_idx = getattr(chk, "bullet_idx", None) if hasattr(chk, "bullet_idx") else (
                        chk.get("bullet_idx") if isinstance(chk, dict) else None
                    )
                    if s_idx is not None and b_idx is not None:
                        pos_id = f"sec_{s_idx}_b_{b_idx}"
                        if pos_id in bullet_map:
                            b_id = pos_id
                            target_bullet = bullet_map[pos_id]

                    if not target_bullet:
                        # Fallback match by exact or partial text
                        chk_text = ""
                        if hasattr(chk, "text"):
                            chk_text = str(chk.text or "")
                        elif hasattr(chk, "claim"):
                            chk_text = str(chk.claim or "")
                        elif isinstance(chk, dict):
                            chk_text = str(chk.get("text") or chk.get("claim") or "")

                        for candidate_id, candidate_bullet in bullet_map.items():
                            if candidate_bullet.text == chk_text or (
                                chk_text and chk_text in candidate_bullet.text
                            ):
                                b_id = candidate_id
                                target_bullet = candidate_bullet
                                break

                if not b_id or not target_bullet:
                    continue

                fb = ""
                if hasattr(chk, "feedback"):
                    fb = str(chk.feedback or "")
                elif hasattr(chk, "critique"):
                    fb = str(chk.critique or "")
                elif isinstance(chk, dict):
                    fb = str(chk.get("feedback") or chk.get("critique") or chk.get("reason") or "")

                if not fb:
                    fb = "Fact-check failed: statement unsupported by profile."

                flagged_items.append(
                    {
                        "bullet_id": b_id,
                        "text": target_bullet.text,
                        "status": status,
                        "critique": fb,
                        "source_ids": target_bullet.source_ids,
                    }
                )

        # If no bullets were rejected, draft is fully supported
        if not flagged_items:
            return draft

        # Render repair prompt with only the isolated rejected bullets
        system_content = self.system_template.render()
        task_content = self.task_template.render(
            mode="repair",
            flagged_bullets=flagged_items,
            source_facts=profile_facts,
        )

        structured_llm = self.llm.with_structured_output(
            DeltaRepairOutput,
            method="json_schema",
            strict=True,
        )

        # Prompt Caching: Static system instructions first, dynamic data last
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=task_content),
        ]
        repair_output: DeltaRepairOutput = structured_llm.invoke(messages)

        # Surgically merge repaired bullets back into draft in exact positions
        repaired_map = {rb.bullet_id: rb for rb in repair_output.repaired_bullets}

        if "summary" in repaired_map:
            rep = repaired_map["summary"]
            draft.summary = TailoredBullet(text=rep.text, source_ids=rep.source_ids)

        for s_idx, section in enumerate(draft.sections):
            for b_idx, _ in enumerate(section.bullets):
                b_id = f"sec_{s_idx}_b_{b_idx}"
                if b_id in repaired_map:
                    rep = repaired_map[b_id]
                    draft.sections[s_idx].bullets[b_idx] = TailoredBullet(
                        text=rep.text,
                        source_ids=rep.source_ids,
                    )

        draft.version += 1
        return draft


def run(state: GraphState) -> Dict[str, Any]:
    """LangGraph node execution function.

    Signature Contract: def run(state: GraphState) -> dict
    Reads: profile, job, gap, round, critique, draft
    Returns: {"draft": TailoredResume, "round": state.get("round", 0) + 1}
    """
    profile = state.get("profile", {})
    job = state.get("job", {})
    gap = state.get("gap", {})
    current_round = state.get("round", 0)
    critique = state.get("critique")
    existing_draft = state.get("draft")
    llm = state.get("llm")

    agent = ResumeWriterAgent(llm=llm)

    if current_round == 0 or not existing_draft:
        draft = agent.generate_initial_draft(profile=profile, job=job, gap=gap)
    else:
        resume_model = agent._to_resume_model(existing_draft)
        if critique:
            draft = agent.delta_repair(
                draft=resume_model,
                profile=profile,
                critique=critique,
            )
        else:
            draft = resume_model

    # Hard Deterministic Verification
    validate_writer_output(draft, profile)

    return {
        "draft": draft,
        "round": current_round + 1,
    }
