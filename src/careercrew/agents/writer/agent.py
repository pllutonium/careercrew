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

    profile: Dict[str, Any]
    job: Dict[str, Any]
    gap: Dict[str, Any]
    round: int
    critique: Optional[Dict[str, Any]]
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
    """Recursively harvest all raw factual bullet IDs and their text from the profile.

    Supports arbitrary nested structures produced by upstream agents (Profile Agent, etc.).
    """
    facts: Dict[str, str] = {}

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

    _walk(profile)
    return facts


def validate_draft(draft: TailoredResume, profile: Dict[str, Any]) -> None:
    """Deterministic Guardrail: Asserts every bullet has non-empty valid source IDs from profile."""
    profile_facts = extract_profile_facts(profile)
    valid_ids: Set[str] = set(profile_facts.keys())

    # Check executive summary bullet
    if not draft.summary:
        raise ValueError("Resume draft is missing an executive summary.")
    if not draft.summary.source_ids:
        msg = f"Zero-Fabrication Violation: Summary has empty source_ids: '{draft.summary.text}'"
        raise ValueError(msg)
    for src_id in draft.summary.source_ids:
        if valid_ids and src_id not in valid_ids:
            msg = (
                f"Zero-Fabrication Violation: Summary references invalid source_id '{src_id}' "
                f"not found in candidate profile."
            )
            raise ValueError(msg)

    # Check all sections and bullets
    for _sec_idx, section in enumerate(draft.sections):
        if not section.bullets:
            continue
        for b_idx, bullet in enumerate(section.bullets):
            if not bullet.source_ids:
                msg = (
                    f"Zero-Fabrication Violation: Section '{section.section_name}' bullet {b_idx} "
                    f"has empty source_ids: '{bullet.text}'"
                )
                raise ValueError(msg)
            for src_id in bullet.source_ids:
                if valid_ids and src_id not in valid_ids:
                    msg = (
                        f"Zero-Fabrication Violation: Section '{section.section_name}' "
                        f"bullet {b_idx} references invalid source_id '{src_id}'."
                    )
                    raise ValueError(msg)


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
        profile: Dict[str, Any],
        job: Dict[str, Any],
        gap: Dict[str, Any],
    ) -> TailoredResume:
        """Generates the initial tailored resume draft (Round 0)."""
        system_content = self.system_template.render()

        # Enforce compact JSON to stay strictly within 6,000 token budget
        compact_profile = json.dumps(profile, separators=(",", ":"), ensure_ascii=False)
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
        profile: Dict[str, Any],
        critique: Dict[str, Any],
    ) -> TailoredResume:
        """Delta-Repair Algorithm: Preserves supported bullets, isolates unsupported/partial ones,
        and surgically merges repairs back into the draft.
        """
        profile_facts = extract_profile_facts(profile)
        bullet_map, _ = self._index_draft_bullets(draft)

        # Parse critique bullets
        critique_bullets = critique.get("bullets", [])
        if not critique_bullets and isinstance(critique.get("critiques"), list):
            critique_bullets = critique["critiques"]

        flagged_items: List[Dict[str, Any]] = []

        for crit in critique_bullets:
            status = crit.get("status", "").lower()
            if status in ("unsupported", "partial"):
                b_id = crit.get("bullet_id")
                target_bullet: Optional[TailoredBullet] = None

                if b_id and b_id in bullet_map:
                    target_bullet = bullet_map[b_id]
                else:
                    # Fallback matching by exact or partial text
                    crit_text = crit.get("text", "")
                    for candidate_id, bullet in bullet_map.items():
                        if bullet.text == crit_text or (crit_text and crit_text in bullet.text):
                            b_id = candidate_id
                            target_bullet = bullet
                            break

                if not b_id or not target_bullet:
                    continue

                fb = crit.get("critique") or crit.get("feedback") or "Fact-check failed."
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

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=task_content),
        ]
        repair_output: DeltaRepairOutput = structured_llm.invoke(messages)

        # Surgically merge repaired bullets back into draft
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

    # Deterministic Guardrail Check
    validate_draft(draft, profile)

    return {
        "draft": draft,
        "round": current_round + 1,
    }
