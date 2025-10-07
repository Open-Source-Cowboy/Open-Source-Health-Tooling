# OSS Health Checker

A Python CLI to evaluate the open source health of GitHub repositories using a token, aligned with Section 2 of the Open Source Committee: Project Maturity Tiers (2025) methodology.

## Beginner-friendly install (Windows, macOS, Linux)

1) Install Python 3.10+:
- Windows: Download from the Microsoft Store or python.org. During install, check "Add python.exe to PATH".
- macOS: Use Homebrew (`brew install python`) or python.org installer.
- Linux: Use your package manager (e.g., `sudo apt install python3 python3-pip`).

2) Open a terminal/command prompt:
- Windows: Start Menu -> "Command Prompt" or "PowerShell".
- macOS: Launchpad -> "Terminal".
- Linux: Open your terminal app.

3) Clone or download this folder to your computer, then in the terminal, change into the project directory.

4) (Recommended) Create and activate a virtual environment:
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

5) Install the tool and dependencies:
```bash
pip install -e .
```
If you get a permissions warning, try:
```bash
pip install --user -e .
```

6) Set your GitHub token:
- Create a token at GitHub (Settings -> Developer settings -> Fine-grained or classic token). Read-only public repo scope is sufficient.
- In the terminal, set the environment variable:
```bash
# Windows PowerShell
$env:GITHUB_TOKEN = "ghp_your_token_here"
# Windows cmd.exe
set GITHUB_TOKEN=ghp_your_token_here
# macOS/Linux (bash/zsh)
export GITHUB_TOKEN=ghp_your_token_here
```

## Run from command prompt

- Check specific repositories and print a table:
```bash
oss-health --repos owner1/repo1 owner2/repo2 --format table
```

- Scan an organization (public repos) and save a PDF report:
```bash
oss-health --org IntersectMBO --limit 10 --format pdf --output report.pdf
```

- Output JSON with details:
```bash
oss-health --repos owner/repo --format json --details
```

## PDF output
- Use `--format pdf --output report.pdf` to generate a PDF summary table with repository scores, health label, and maturity tier.
- The PDF uses standard US Letter size; open the resulting `report.pdf` with any PDF viewer.

## Notes
- If `oss-health` isn't found on Windows, try `python -m oss_health.cli ...` from the project folder, or ensure your Python Scripts directory is on PATH.
- The tool uses conservative heuristics from the default branch and GitHub workflows. It may not capture private configurations or non-standard layouts.
