"""Unit tests for CareerCrew Resume Writer Agent and Document Export Tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from careercrew.agents.writer.agent import (
    extract_profile_facts,
    run,
    validate_draft,
)
from careercrew.schemas.resume import (
    DeltaRepairOutput,
    RepairedBullet,
    TailoredBullet,
    TailoredResume,
)
from careercrew.tools.docx_export import convert_docx_to_pdf, export_to_docx

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "tailored_resume.json"


@pytest.fixture
def sample_profile() -> dict:
    return {
        "candidate": {
            "name": "Alex Mercer",
            "email": "alex.mercer@example.com",
            "phone": "+1-555-0199",
            "location": "San Francisco, CA",
        },
        "summary_facts": [
            {
                "id": "sum_1",
                "text": "Senior ML Infrastructure Engineer with 6+ years in distributed training.",
            }
        ],
        "experiences": [
            {
                "organization": "HyperScale AI",
                "role_title": "Senior AI Systems Engineer",
                "date_range": "2021 - Present",
                "bullets": [
                    {
                        "id": "exp1_b1",
                        "text": (
                            "Engineered distributed LLM inference pipeline serving 2M daily "
                            "requests, slashing p99 latency by 35% with vLLM."
                        ),
                    },
                    {
                        "id": "exp1_b2",
                        "text": (
                            "Architected automated model evaluation framework across "
                            "50 GPU cluster nodes."
                        ),
                    },
                ],
            }
        ],
        "education": [
            {
                "organization": "Carnegie Mellon University",
                "role_title": "B.S. in Computer Science",
                "date_range": "2015 - 2019",
                "bullets": [
                    {
                        "id": "edu_1",
                        "text": (
                            "Graduated with University Honors; undergraduate research "
                            "in distributed consensus."
                        ),
                    }
                ],
            }
        ],
    }


@pytest.fixture
def sample_draft() -> TailoredResume:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return TailoredResume.model_validate(data)


# ==============================================================================
# 1. Schema & Invariant Tests
# ==============================================================================


def test_schema_extra_forbid():
    """Verify strict JSON schema compliance: extra fields are forbidden."""
    with pytest.raises(ValidationError):
        TailoredBullet(
            text="Valid text",
            source_ids=["exp1_b1"],
            unauthorized_field="illegal",  # type: ignore
        )


def test_extract_profile_facts_recursive(sample_profile):
    """Ensure recursive fact extraction gathers all valid IDs and text."""
    facts = extract_profile_facts(sample_profile)
    assert "sum_1" in facts
    assert "exp1_b1" in facts
    assert "exp1_b2" in facts
    assert "edu_1" in facts
    assert "2M daily requests" in facts["exp1_b1"]


# ==============================================================================
# 2. Deterministic Guardrail Tests
# ==============================================================================


def test_validate_draft_success(sample_draft, sample_profile):
    """Valid draft passes without error."""
    validate_draft(sample_draft, sample_profile)


def test_validate_draft_empty_source_ids(sample_draft, sample_profile):
    """Fails deterministically when any bullet has empty source_ids."""
    sample_draft.sections[0].bullets[0].source_ids = []
    with pytest.raises(ValueError, match="empty source_ids"):
        validate_draft(sample_draft, sample_profile)


def test_validate_draft_empty_summary_source_ids(sample_draft, sample_profile):
    """Fails deterministically when summary has empty source_ids."""
    sample_draft.summary.source_ids = []
    with pytest.raises(ValueError, match="empty source_ids"):
        validate_draft(sample_draft, sample_profile)


def test_validate_draft_unknown_source_id(sample_draft, sample_profile):
    """Fails deterministically when referencing an ungrounded hallucinated ID."""
    sample_draft.sections[0].bullets[0].source_ids = ["hallucinated_id_999"]
    with pytest.raises(ValueError, match="invalid source_id 'hallucinated_id_999'"):
        validate_draft(sample_draft, sample_profile)


# ==============================================================================
# 3. Initial Draft Generation (Round 0)
# ==============================================================================


def test_run_initial_draft_round_0(sample_profile, sample_draft):
    """Round 0 generates initial draft and increments round to 1."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = sample_draft
    mock_llm.with_structured_output.return_value = mock_structured

    state = {
        "profile": sample_profile,
        "job": {"title": "Staff AI Engineer", "company": "Anthropic"},
        "gap": {"matched_strengths": ["distributed training"]},
        "round": 0,
        "llm": mock_llm,
    }

    result = run(state)

    assert result["round"] == 1
    assert isinstance(result["draft"], TailoredResume)
    assert result["draft"].summary.source_ids == ["sum_1", "exp1_b1"]
    mock_llm.with_structured_output.assert_called_once_with(
        TailoredResume, method="json_schema", strict=True
    )


# ==============================================================================
# 4. Delta-Repair Algorithm (Round > 0 with Critic Feedback)
# ==============================================================================


def test_run_delta_repair_preserves_supported_bullets(sample_profile, sample_draft):
    """Critic rejection isolates only flagged bullets and preserves supported bullets untouched."""
    # sec_0_b_0 is supported; sec_0_b_1 is unsupported
    original_supported_text = sample_draft.sections[0].bullets[0].text
    original_supported_ids = sample_draft.sections[0].bullets[0].source_ids.copy()

    critique = {
        "bullets": [
            {
                "bullet_id": "sec_0_b_0",
                "status": "supported",
                "critique": "Factually verified.",
            },
            {
                "bullet_id": "sec_0_b_1",
                "status": "unsupported",
                "critique": "Candidate did not build a benchmark framework across 50 nodes.",
            },
        ]
    }

    repaired_output = DeltaRepairOutput(
        repaired_bullets=[
            RepairedBullet(
                bullet_id="sec_0_b_1",
                text="Engineered regression evaluation scripts executed across GPU clusters.",
                source_ids=["exp1_b2"],
            )
        ]
    )

    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = repaired_output
    mock_llm.with_structured_output.return_value = mock_structured

    state = {
        "profile": sample_profile,
        "job": {"title": "Staff AI Engineer", "company": "Anthropic"},
        "gap": {},
        "round": 1,
        "critique": critique,
        "draft": sample_draft,
        "llm": mock_llm,
    }

    result = run(state)

    assert result["round"] == 2
    updated_draft = result["draft"]

    # 1. Supported bullet was NOT modified
    assert updated_draft.sections[0].bullets[0].text == original_supported_text
    assert updated_draft.sections[0].bullets[0].source_ids == original_supported_ids

    # 2. Flagged bullet was surgically repaired
    assert (
        updated_draft.sections[0].bullets[1].text
        == "Engineered regression evaluation scripts executed across GPU clusters."
    )
    assert updated_draft.sections[0].bullets[1].source_ids == ["exp1_b2"]


# ==============================================================================
# 5. Document Export & PDF Conversion Tests
# ==============================================================================


def test_docx_export(tmp_path, sample_draft, sample_profile):
    """Generates valid .docx file matching ATS specifications."""
    out_docx = tmp_path / "tailored_resume.docx"
    result_path = export_to_docx(
        resume=sample_draft,
        output_path=out_docx,
        profile_meta=sample_profile["candidate"],
        include_source_tags=True,
    )

    assert result_path.exists()
    assert result_path.stat().st_size > 0

    # Read back through python-docx to verify document structure
    import docx

    doc = docx.Document(str(result_path))
    headings = [p.text for p in doc.paragraphs if p.runs and p.runs[0].bold]
    assert "Alex Mercer" in headings[0]
    full_text = " ".join(p.text for p in doc.paragraphs)
    assert "HyperScale AI" in full_text
    assert "[src: exp1_b1]" in full_text


def test_convert_docx_to_pdf_missing_binary(tmp_path):
    """Raises FileNotFoundError when LibreOffice is not installed/found."""
    dummy_docx = tmp_path / "test.docx"
    dummy_docx.write_bytes(b"PK0304")

    with patch("careercrew.tools.docx_export.find_libreoffice_binary", return_value=None):
        with pytest.raises(FileNotFoundError, match="LibreOffice headless binary"):
            convert_docx_to_pdf(dummy_docx, output_dir=tmp_path)


def test_convert_docx_to_pdf_successful_invocation(tmp_path):
    """Verifies headless CLI command execution and return path."""
    dummy_docx = tmp_path / "test.docx"
    dummy_docx.write_bytes(b"PK0304")
    expected_pdf = tmp_path / "test.pdf"

    def mock_subprocess_run(cmd, **kwargs):
        expected_pdf.write_bytes(b"%PDF-1.4 mock")
        res = MagicMock()
        res.returncode = 0
        res.stdout = "Converted test.docx -> test.pdf"
        res.stderr = ""
        return res

    with patch(
        "careercrew.tools.docx_export.find_libreoffice_binary",
        return_value="/usr/bin/libreoffice",
    ):
        with patch("subprocess.run", side_effect=mock_subprocess_run) as mock_run:
            pdf_path = convert_docx_to_pdf(dummy_docx, output_dir=tmp_path)
            assert pdf_path == expected_pdf
            assert pdf_path.exists()
            mock_run.assert_called_once()
            cmd_args = mock_run.call_args[0][0]
            assert cmd_args[0] == "/usr/bin/libreoffice"
            assert "--headless" in cmd_args
            assert "--convert-to" in cmd_args
            assert "pdf" in cmd_args
