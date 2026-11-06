# ==============================================================================
# CareerCrew - Member 4 Safe Git Verification & Push Pre-flight Script (PowerShell)
# Enforces Branch Isolation, Member Boundaries, Quality Gates & Secret Hygiene
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  CareerCrew Member 4: Resume Writer Pre-Push Guard   " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# 1. Feature Branch Isolation Check
$currentBranch = (git branch --show-current).Trim()
Write-Host "`n[1/5] Checking Git Branch Isolation..." -ForegroundColor Yellow
if ($currentBranch -eq "main" -or $currentBranch -eq "master") {
    Write-Host "[ERROR] Direct commits to '$currentBranch' are strictly forbidden." -ForegroundColor Red
    Write-Host "Please switch to your designated feature branch: 'feat/member4-resume-writer'" -ForegroundColor Red
    exit 1
} elseif ($currentBranch -ne "feat/member4-resume-writer") {
    Write-Host "[WARNING] Current branch is '$currentBranch' (expected 'feat/member4-resume-writer')." -ForegroundColor Yellow
} else {
    Write-Host "[PASS] Working on isolated feature branch: $currentBranch" -ForegroundColor Green
}

# 2. Code Quality & Formatting Gate (Ruff)
Write-Host "`n[2/5] Running Ruff Linter & Formatter Validation..." -ForegroundColor Yellow
python -m ruff check .
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Ruff validation failed." -ForegroundColor Red
    exit 1
}
Write-Host "[PASS] All Ruff checks passed." -ForegroundColor Green

# 3. Deterministic Test Suite Gate (Pytest)
Write-Host "`n[3/5] Running Writer Unit Tests..." -ForegroundColor Yellow
python -m pytest tests/unit/test_writer.py -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Pytest execution failed." -ForegroundColor Red
    exit 1
}
Write-Host "[PASS] All unit tests passed." -ForegroundColor Green

# 4. Directory Ownership & Teammate Boundary Check
Write-Host "`n[4/5] Enforcing Member 4 Directory Ownership Boundaries..." -ForegroundColor Yellow
$stagedFiles = git diff --cached --name-only
if (-not $stagedFiles) {
    Write-Host "[INFO] No files currently staged. Checking working tree..." -ForegroundColor DarkGray
    $stagedFiles = git status --porcelain | ForEach-Object { ($_ -split '\s+')[-1] }
}

$forbiddenTeams = @("supervisor", "profile", "job_intel", "critic", "interview")
$violations = @()

foreach ($file in $stagedFiles) {
    foreach ($team in $forbiddenTeams) {
        if ($file -match $team) {
            $violations += $file
        }
    }
}

if ($violations.Count -gt 0) {
    Write-Host "[ABORT] Member 4 ownership is restricted to: writer agent, docx export tools, resume schemas, docker, and writer tests." -ForegroundColor Red
    $violations | ForEach-Object { Write-Host "  - Violation: $_" -ForegroundColor Red }
    exit 1
}
Write-Host "[PASS] No teammate files violated." -ForegroundColor Green

# 5. Secrets & Hygiene Safeguard Check
Write-Host "`n[5/5] Checking for Secrets & Hygiene Safeguards..." -ForegroundColor Yellow
$forbiddenPatterns = @("gsk_[A-Za-z0-9]{20,}", "ghp_[A-Za-z0-9]{20,}", "sk-[A-Za-z0-9]{20,}", "AIzaSy[A-Za-z0-9]{20,}", "BEGIN (RSA|OPENSSH) PRIVATE KEY")
$cachedDiff = git diff --cached -- ':!scripts/*'
$secretDetected = $false

foreach ($pattern in $forbiddenPatterns) {
    if ($cachedDiff -match $pattern) {
        Write-Host "[ERROR] Potential secret detected matching pattern: '$pattern'" -ForegroundColor Red
        $secretDetected = $true
    }
}

if ($secretDetected) {
    Write-Host "[ABORT] Staged diff contains sensitive credentials or API keys." -ForegroundColor Red
    exit 1
}
Write-Host "[PASS] Clean working directory. Zero secrets detected." -ForegroundColor Green

Write-Host "`n======================================================" -ForegroundColor Cyan
Write-Host "  Pre-flight verification PASSED successfully.        " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Cyan

Write-Host "`nRecommended Conventional Commit commands:" -ForegroundColor White
Write-Host "  git add ." -ForegroundColor Cyan
Write-Host "  git commit -m `"refactor(writer): remove emojis and standardize professional logging and docstrings`"" -ForegroundColor Cyan
Write-Host "  git push -u origin $currentBranch`n" -ForegroundColor Cyan
