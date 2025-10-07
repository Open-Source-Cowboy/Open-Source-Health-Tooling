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

# Node Section 2 scoring CLI (this repo)
GITHUB_TOKEN="$GITHUB_TOKEN" npm run oss-health -- --repos owner1/repo1 owner2/repo2 --format json --details
GITHUB_TOKEN="$GITHUB_TOKEN" npm run oss-health -- --org some-org --limit 10 --format table
```

## Notes

- `@figify/gh-metrics` reports PR and issue engagement metrics for a single repository at a time.
- The new Node CLI (`npm run oss-health`) enforces the Section 2 requirements defined below, mirroring the Python implementation.
- The original Python CLI for OSS Health scoring remains in `oss_health/` if you prefer that workflow.

## Output

`@figify/gh-metrics` prints metrics (e.g., average time to close, comments per issue/PR, reviews per PR) to stdout.

## Scoring overview (Policy Section 2)

- Documentation (0–7): README, LICENSE, CONTRIBUTING, SECURITY, Code of Conduct, Issue/PR templates, Setup instructions.
- Technical Infrastructure (0–18): tests, CI/CD, security scanning, dependency updates, linting/formatting, release management, build/packaging, IaC, platform integration.
- Health & Sustainability (0–12): community engagement, governance & leadership, succession planning, ecosystem importance, activity trend, sustainability & risks.

Totals map to tiers: <10 Incubation, 10–24 Growth, ≥24 Mature. Health: 10–12 Healthy, 6–9 Moderate, 0–5 Unhealthy.

### Section 2: Detailed Scoring Requirements

- **Documentation (0–7 points)**
  - 1 point each if present: `README`, `LICENSE`, `CONTRIBUTING`, `SECURITY` policy, `CODE_OF_CONDUCT`, Issue template, PR template.
  - Setup/installation instructions present in `README` also count toward the total.
  - Note: Documentation points are capped at 7 even if all eight signals are present.

- **Technical Infrastructure (0–18 points)**
  - Automated Tests (max 3)
    - +2: Test files detected (e.g., tests directory or *_test/*.test/*.spec* patterns)
    - +1: Tests referenced in CI workflows
  - CI/CD Pipelines (max 3)
    - +1: `.github/workflows/` exists
    - +1: Build steps referenced in CI (e.g., npm/pnpm/yarn build, make, docker build, mvn, gradle, cmake, cargo, go build)
    - +1: Release steps referenced in CI (e.g., gh release, common release actions)
  - Security Scanning (max 2)
    - +2: Code scanning referenced in CI (e.g., codeql, trivy, snyk, semgrep, bandit, gosec)
  - Dependency Updates (max 2)
    - +2: Dependabot or Renovate configuration present
  - Linting/Formatting (max 2)
    - +2: Lint/format config present and linting referenced in CI
    - +1: Either lint/format config present or linting referenced in CI
  - Release Management (max 2)
    - +1: Git tags exist
    - +1: Releases or a `CHANGELOG` present
  - Build & Packaging Tools (max 2)
    - +2: Build/packaging files present (e.g., `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`, `pom.xml`, `Dockerfile`, `Makefile`, etc.)
  - Infrastructure as Code (max 1)
    - +1: IaC files present (e.g., Terraform, Helm charts, Ansible) or IaC directories (`k8s/`, `deploy/`, `infra/`)
  - Platform Integration (max 1)
    - +1: CI config for a platform present (e.g., `.github/workflows`, CircleCI, Travis, Azure Pipelines, GitLab CI)

- **Health & Sustainability (0–12 points)**
  - Community Engagement (max 2)
    - 2: stars ≥ 25 or forks ≥ 10 or open issues ≥ 25
    - 1: stars ≥ 5 or forks ≥ 2 or open issues ≥ 5
  - Governance & Leadership (max 2)
    - 2: both `CODEOWNERS` and governance docs (`GOVERNANCE.md`, `MAINTAINERS`, `OWNERS`)
    - 1: either of the above present
  - Succession Planning (max 2)
    - 2: ≥ 4 unique committers in last 90 days
    - 1: ≥ 2 unique committers in last 90 days
  - Ecosystem Importance (max 2)
    - 2: forks ≥ 20 or watchers ≥ 50
    - 1: forks ≥ 5 or watchers ≥ 15
  - Activity Trend (max 2)
    - 2: latest commit within 30 days
    - 1: latest commit within 90 days
  - Sustainability & Risks (max 2)
    - 0 points if archived
    - Otherwise: +1 for `SECURITY` policy, +1 for ≥ 3 active committers in last 90 days

## Tips and troubleshooting

- Ensure `GITHUB_TOKEN` has `repo` scope and is exported.
- For GitHub Enterprise, set `GITHUB_URL` (e.g., `https://<ghe-host>/api`).
- If you hit API rate limits, try again later.
