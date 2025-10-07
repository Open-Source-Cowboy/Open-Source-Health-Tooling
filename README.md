# OSS Health Checker

A friendly command‑line tool that evaluates the open‑source health of GitHub repositories using your GitHub token. It follows the 2025 Project Maturity Tiers (Section 2) guidance and can export a nicely formatted PDF report.

## Quick start (Node/npm)

1) Install Node.js 18+ and Git.

2) Clone this repo and open a terminal in the project directory.

3) Install dependencies:

```bash
npm install
```

4) Provide a GitHub token with repo read access. Either:

- Export once per shell session:

```bash
export GITHUB_TOKEN=ghp_yourTokenHere
```

- Or set it inline per command.

## How to run

This repo includes an npm-powered CLI using `@figify/gh-metrics` for GitHub repository metrics.

- Using npx:

```bash
npx @figify/gh-metrics --a <owner-or-org> --r <repo>
```

- Using the npm script in this repo:

```bash
npm run gh-metrics -- --a <owner-or-org> --r <repo>
```

### Examples

```bash
# npx example
GITHUB_TOKEN="$GITHUB_TOKEN" npx @figify/gh-metrics --a sindresorhus --r ora

# npm script example
GITHUB_TOKEN="$GITHUB_TOKEN" npm run gh-metrics -- --a sindresorhus --r ora
```

## Notes

- `@figify/gh-metrics` reports PR and issue engagement metrics for a single repository at a time.
- The original Python CLI for OSS Health scoring remains in `oss_health/` if you prefer that workflow.

## Output

`@figify/gh-metrics` prints metrics (e.g., average time to close, comments per issue/PR, reviews per PR) to stdout.

## Scoring overview (Policy Section 2)

- Documentation (0–7): README, LICENSE, CONTRIBUTING, SECURITY, Code of Conduct, Issue/PR templates, Setup instructions.
- Technical Infrastructure (0–18): tests, CI/CD, security scanning, dependency updates, linting/formatting, release management, build/packaging, IaC, platform integration.
- Health & Sustainability (0–12): community engagement, governance & leadership, succession planning, ecosystem importance, activity trend, sustainability & risks.

Totals map to tiers: <10 Incubation, 10–24 Growth, ≥24 Mature. Health: 10–12 Healthy, 6–9 Moderate, 0–5 Unhealthy.

## Tips and troubleshooting

- Ensure `GITHUB_TOKEN` has `repo` scope and is exported.
- For GitHub Enterprise, set `GITHUB_URL` (e.g., `https://<ghe-host>/api`).
- If you hit API rate limits, try again later.
