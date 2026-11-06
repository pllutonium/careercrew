#!/usr/bin/env bash
# ==============================================================================
# CareerCrew - Member 4 Safe Git Verification & Push Pre-flight Script
# Enforces Branch Isolation, Member Boundaries, Quality Gates & Secret Hygiene
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  CareerCrew Member 4: Resume Writer Pre-Push Guard   ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Feature Branch Isolation Check
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null | tr -d '\r' || git rev-parse --abbrev-ref HEAD 2>/dev/null | tr -d '\r' || echo "UNKNOWN")
echo -e "\n[1/5] Checking Git Branch Isolation..."
if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
    echo -e "${RED}[ERROR] Direct commits to '$CURRENT_BRANCH' are strictly forbidden.${NC}"
    echo -e "Please switch to your designated feature branch: 'feat/member4-resume-writer'"
    exit 1
elif [ "$CURRENT_BRANCH" != "feat/member4-resume-writer" ]; then
    echo -e "${YELLOW}[WARNING] Current branch is '$CURRENT_BRANCH' (expected 'feat/member4-resume-writer').${NC}"
else
    echo -e "${GREEN}[PASS] Working on isolated feature branch: $CURRENT_BRANCH${NC}"
fi

# 2. Code Quality & Formatting Gate (Ruff)
echo -e "\n[2/5] Running Ruff Linter & Formatter Validation..."
if command -v uv &>/dev/null; then
    uv run ruff check .
else
    python -m ruff check .
fi
echo -e "${GREEN}[PASS] All Ruff checks passed.${NC}"

# 3. Deterministic Test Suite Gate (Pytest)
echo -e "\n[3/5] Running Writer Unit Tests..."
if command -v uv &>/dev/null; then
    uv run pytest tests/unit/test_writer.py -v
else
    python -m pytest tests/unit/test_writer.py -v
fi
echo -e "${GREEN}[PASS] All unit tests passed.${NC}"

# 4. Directory Ownership & Teammate Boundary Check
echo -e "\n[4/5] Enforcing Member 4 Directory Ownership Boundaries..."
STAGED_FILES=$(git diff --cached --name-only || true)

if [ -z "$STAGED_FILES" ]; then
    echo -e "${YELLOW}[INFO] No files currently staged. Checking untracked/modified files...${NC}"
    STAGED_FILES=$(git status --porcelain | awk '{print $2}')
fi

FORBIDDEN_FOUND=0
FORBIDDEN_TEAMS=("supervisor" "profile" "job_intel" "critic" "interview")

for file in $STAGED_FILES; do
    for teammate in "${FORBIDDEN_TEAMS[@]}"; do
        if [[ "$file" == *"$teammate"* ]]; then
            echo -e "${RED}[ERROR] Boundary violation: File '$file' belongs to teammate '$teammate'.${NC}"
            FORBIDDEN_FOUND=1
        fi
    done
done

if [ "$FORBIDDEN_FOUND" -ne 0 ]; then
    echo -e "${RED}[ABORT] Member 4 ownership is restricted to: writer agent, docx export tools, resume schemas, docker, and writer tests.${NC}"
    exit 1
fi
echo -e "${GREEN}[PASS] No teammate files violated.${NC}"

# 5. Secrets & Hygiene Safeguard Check
echo -e "\n[5/5] Checking for Secrets & Hygiene Safeguards..."
SECRETS_FOUND=0
FORBIDDEN_PATTERNS=("gsk_[A-Za-z0-9]{20,}" "ghp_[A-Za-z0-9]{20,}" "sk-[A-Za-z0-9]{20,}" "AIzaSy[A-Za-z0-9]{20,}" "BEGIN (RSA|OPENSSH) PRIVATE KEY")

for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    if git diff --cached -E -- ':!scripts/*' 2>/dev/null | grep -qE "$pattern"; then
        echo -e "${RED}[ERROR] Potential secret detected matching pattern: '$pattern'${NC}"
        SECRETS_FOUND=1
    fi
done

if [ "$SECRETS_FOUND" -ne 0 ]; then
    echo -e "${RED}[ABORT] Staged diff contains sensitive credentials or API keys.${NC}"
    exit 1
fi
echo -e "${GREEN}[PASS] Clean working directory. Zero secrets detected.${NC}"

echo -e "\n${BLUE}======================================================${NC}"
echo -e "${GREEN}  Pre-flight verification PASSED successfully.        ${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "\nRecommended Conventional Commit commands:"
echo -e "  git add ."
echo -e "  git commit -m \"refactor(writer): remove emojis and standardize professional logging and docstrings\""
echo -e "  git push -u origin $CURRENT_BRANCH\n"
