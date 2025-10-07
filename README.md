# OSS Health Checker

A friendly command‑line tool that evaluates the open‑source health of GitHub repositories using your GitHub token. It follows the 2025 Project Maturity Tiers (Section 2) guidance and can export a nicely formatted PDF report.

## Quick start (run locally)

1) Install Python 3.10+ and Git.

2) Clone this repo and open a terminal in the project directory.

3) (Recommended) Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

4) Install dependencies:

```bash
pip install -r requirements.txt
```

5) Provide a GitHub token with repo read access. Pick one:

- Export once per shell session:

```bash
export GITHUB_TOKEN=ghp_yourTokenHere
```

- Or pass `--token` on the command line (examples below).

## How to run

You can run the tool either via the package entry point or directly via the CLI module. Both accept the same flags.

- Package entry point:

```bash
python3 -m oss_health --repos owner1/repo1 owner2/repo2 --format table
```

- CLI module explicitly:

```bash
python3 -m oss_health.cli --org some-org --limit 10 --format json --details
```

## Generate a PDF report

Add the `--pdf PATH` flag to save a formatted PDF summary. Include `--details` to append per‑repository breakdown pages.

```bash
# Example: assess two repos, show table in terminal, and write a PDF
python3 -m oss_health --repos owner1/repo1 owner2/repo2 \
  --format table \
  --pdf reports/oss-health.pdf \
  --title "Acme OSS Health Report" \
  --token "$GITHUB_TOKEN"

# Example: scan an org, detailed JSON to terminal, and detailed PDF
python3 -m oss_health --org some-org --limit 20 \
  --format json --details \
  --pdf oss-health-detailed.pdf \
  --token "$GITHUB_TOKEN"
```

What the PDF includes:

- A summary table of all repositories with Documentation, Infrastructure, Health, Total, Health Label, and Maturity columns.
- Optional detail pages per repository (when `--details` is used) with the breakdowns and key signals.

## Output formats

- `table`: fixed‑width table printed to your terminal.
- `json`: machine‑readable results; `--details` adds breakdown arrays and hints.

## Scoring overview (Policy Section 2)

- Documentation (0–7): README, LICENSE, CONTRIBUTING, SECURITY, Code of Conduct, Issue/PR templates, Setup instructions.
- Technical Infrastructure (0–18): tests, CI/CD, security scanning, dependency updates, linting/formatting, release management, build/packaging, IaC, platform integration.
- Health & Sustainability (0–12): community engagement, governance & leadership, succession planning, ecosystem importance, activity trend, sustainability & risks.

Totals map to tiers: <10 Incubation, 10–24 Growth, ≥24 Mature. Health: 10–12 Healthy, 6–9 Moderate, 0–5 Unhealthy.

## Tips and troubleshooting

- If you see `ModuleNotFoundError: requests`, make sure you ran `pip install -r requirements.txt` in your active virtual environment.
- If you hit API rate limits, try again later or reduce the number of repositories with `--limit`.
- Private repositories are not scanned when using `--org`.
