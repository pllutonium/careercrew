# CareerCrew: Resume Writer Agent (Member 4)

Production-grade Resume Writer Agent for the CareerCrew multi-agent intelligence platform. Implemented with Python 3.11, LangGraph, Groq open-weight inference (`openai/gpt-oss-120b`), and Microsoft Word ATS document generation.

---

## Architectural Invariants and Rules

### 1. Zero-Fabrication Mandate
The Resume Writer Agent sharpens, aligns, and frames candidate facts using the Google X-Y-Z active framework ("Accomplished [X], as measured by [Y], by doing [Z]"). 

- All generated bullet points carry a non-empty `source_ids: list[str]` array referencing factual bullet identifiers in the candidate's profile.
- Hard deterministic validation (`validate_writer_output`) runs prior to state return, preventing hallucinated tools, metrics, titles, or dates.

### 2. Groq Open-Weight Structured Output Compliance
- **Engine**: `openai/gpt-oss-120b` via `ChatGroq` (`temperature=0.4`, `reasoning_effort="medium"`).
- **Structured Output**: Method `json_schema` with `strict=True`.
- **Schema Constraints**: All schemas inherit from `StrictBaseModel` with `model_config = {"extra": "forbid"}`. Dynamic dictionaries, default assignments, and schema-level size restrictions (`min_length`, `max_length`, `minItems`) are excluded to prevent Groq API parsing rejections.
- **Token Budget**: Prompt arrays serialize candidate profiles into compact JSON to maintain total turn volume below 6,000 tokens.

### 3. State Contract and Delta-Repair
- **Function Signature**: `def run(state: GraphState) -> dict` returning:
  ```python
  {"draft": TailoredResume, "round": current_round + 1}
  ```
- **Round 0**: Generates the complete tailored resume draft.
- **Round > 0 with Critique**:
  - If `critique.passed` is `True`, regeneration is bypassed and the draft is returned unchanged.
  - If `critique.passed` is `False`, the agent inspects `critique.claim_checks` and isolates only bullets marked `"unsupported"` or `"partial"`.
  - All `"supported"` bullets remain locked. Only flagged bullets are sent for surgical repair and re-integrated into their exact section indices.

---

## Component Layout

```text
careercrew/
├── docker/
│   ├── api.Dockerfile               # Multi-stage production build with LibreOffice headless
│   └── ui.Dockerfile                # Multi-stage Streamlit interface build
├── docker-compose.yml               # Local development stack
├── docker-compose.prod.yml          # Production stack with resource limits
├── pyproject.toml                   # Project dependencies, Ruff, and Pytest configuration
├── scripts/
│   ├── git_verify_push.sh           # Bash pre-flight verification gate
│   └── git_verify_push.ps1          # PowerShell pre-flight verification gate
├── src/careercrew/
│   ├── agents/writer/
│   │   ├── agent.py                 # LangGraph node, Delta-Repair, and validation logic
│   │   └── prompts/
│   │       ├── system.md            # System prompt with Zero-Fabrication instructions
│   │       └── task.md              # Jinja2 task template optimized for prompt caching
│   ├── schemas/
│   │   └── resume.py                # Strict Pydantic models for Groq structured output
│   └── tools/
│       └── docx_export.py           # ATS document generation and headless PDF conversion
└── tests/
    ├── fixtures/
    │   └── tailored_resume.json     # Valid ground-truth resume fixture
    └── unit/
        └── test_writer.py           # 15 offline unit tests covering schemas and agent execution
```

---

## Document Export Specifications

- **Page Margins**: Exactly 0.65 inches (46.8 pt) on top, bottom, left, and right.
- **Typography Hierarchy**:
  - Candidate Name: 16pt Bold, centered.
  - Contact Line: 9pt Regular with pipe delimiters (` | `).
  - Section Titles: 11pt Bold Uppercase with bottom border rule.
  - Role, Organization, Date: 10pt Bold / Italic with right-aligned tab stop at 7.2 inches.
  - Bullets: 9.5pt body text with 1.15 line spacing and 2pt paragraph spacing.
  - Source Provenance: Optional 7.5pt muted superscript tags (`[src: exp1_b1]`).
- **PDF Conversion**: Headless LibreOffice invocation (`soffice` / `libreoffice`) with error capture and diagnostic logging.

---

## Verification and Quality Gates

### Running Linter and Formatter
```bash
python -m ruff check .
```

### Running Offline Unit Tests
```bash
python -m pytest tests/unit/test_writer.py -v
```

### Automated Pre-Flight Script
Verify repository state, branch isolation, teammate file boundaries, and secret hygiene:

```bash
# Bash (Linux / macOS / Git Bash)
bash scripts/git_verify_push.sh

# PowerShell (Windows)
powershell -ExecutionPolicy Bypass -File scripts/git_verify_push.ps1
```
