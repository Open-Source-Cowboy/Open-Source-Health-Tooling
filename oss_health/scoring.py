from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .github_client import GitHubClient


DOC_ITEMS = [
    ("readme", "README present"),
    ("license", "LICENSE present"),
    ("contributing", "CONTRIBUTING present"),
    ("security_policy", "SECURITY policy present"),
    ("code_of_conduct", "CODE_OF_CONDUCT present"),
    ("issue_template", "Issue template present"),
    ("pull_request_template", "PR template present"),
]

LINTER_CONFIG_NAMES = [
    # JavaScript/TypeScript
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yml",
    ".eslintrc.yaml",
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.yml",
    ".prettierrc.yaml",
    "prettier.config.js",
    "prettier.config.cjs",
    # Python
    ".flake8",
    "pyproject.toml",
    "setup.cfg",
    ".pylintrc",
    "ruff.toml",
    # Go
    ".golangci.yml",
    ".golangci.yaml",
    # Rust
    "rustfmt.toml",
    # General
    ".editorconfig",
]

BUILD_PACKAGING_FILES = [
    # General
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    # Node
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    # Python
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    # Rust
    "Cargo.toml",
    # Go
    "go.mod",
    # Java
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    # C/C++
    "CMakeLists.txt",
    # Nix
    "flake.nix",
]

IAC_FILES = [
    "main.tf",
    "terraform.tfvars",
    "chart.yaml",
    "Chart.yaml",
    "values.yaml",
    "kustomization.yaml",
    "playbook.yml",
    "playbook.yaml",
]

CI_CONFIG_FILES = [
    ".github/workflows",
    ".circleci/config.yml",
    ".travis.yml",
    "azure-pipelines.yml",
    ".gitlab-ci.yml",
]

TEST_FILE_PATTERNS = [
    re.compile(r"(^|/)tests?(/|$)", re.I),
    re.compile(r"(^|/).*(_test|\.test\.|\.spec\.)", re.I),
]

CODE_SCANNING_HINTS = [
    "codeql",
    "trivy",
    "snyk",
    "semgrep",
    "bandit",
    "gosec",
]

LINT_HINTS = [
    "eslint",
    "flake8",
    "ruff",
    "pylint",
    "prettier",
    "golangci-lint",
    "clang-tidy",
]

BUILD_HINTS = [
    "make ",
    "docker build",
    "npm run build",
    "pnpm build",
    "yarn build",
    "mvn package",
    "gradle build",
    "cmake ",
    "cargo build",
    "go build",
]

TEST_HINTS = [
    "pytest",
    "python -m pytest",
    "npm test",
    "pnpm test",
    "yarn test",
    "go test",
    "cargo test",
    "mvn test",
]

RELEASE_HINTS = [
    "gh release",
    "actions/create-release",
    "softprops/action-gh-release",
    "semantic-release",
]

DEPENDENCY_UPDATE_FILES = [
    ".github/dependabot.yml",
    ".github/dependabot.yaml",
    "renovate.json",
    ".renovaterc.json",
]


@dataclass
class SubScore:
    name: str
    max_points: int
    points: int
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepositoryAssessment:
    owner: str
    repo: str
    documentation_score: SubScore
    infrastructure_score: List[SubScore]
    health_score: List[SubScore]

    @property
    def total_infrastructure_points(self) -> int:
        return sum(s.points for s in self.infrastructure_score)

    @property
    def max_infrastructure_points(self) -> int:
        return sum(s.max_points for s in self.infrastructure_score)

    @property
    def total_health_points(self) -> int:
        return sum(s.points for s in self.health_score)

    @property
    def max_health_points(self) -> int:
        return sum(s.max_points for s in self.health_score)

    @property
    def total_points(self) -> float:
        return (
            self.documentation_score.points
            + self.total_infrastructure_points
            + self.total_health_points
        )

    @property
    def maturity_tier(self) -> str:
        total = self.total_points
        if total < 10:
            return "Incubation"
        if total < 24:
            return "Growth"
        return "Mature"

    @property
    def health_label(self) -> str:
        score = self.total_health_points
        if score >= 10:
            return "Healthy"
        if score >= 6:
            return "Moderate"
        return "Unhealthy"


def _path_exists(paths: List[str], tree_paths: List[str]) -> bool:
    for p in paths:
        if p.endswith("/"):
            # directory
            prefix = p.rstrip("/") + "/"
            if any(tp.startswith(prefix) for tp in tree_paths):
                return True
        else:
            if p in tree_paths:
                return True
    return False


def _collect_tree_paths(tree: List[Dict[str, Any]]) -> List[str]:
    return [t.get("path", "") for t in tree]


def _get_workflow_texts(client: GitHubClient, owner: str, repo: str) -> List[str]:
    workflows = client.list_workflows(owner, repo)
    texts: List[str] = []
    for wf in workflows:
        path = wf.get("path")
        if not path:
            continue
        content = client.get_file_content(owner, repo, path)
        if content:
            texts.append(content.lower())
    return texts


def _score_documentation(client: GitHubClient, owner: str, repo: str) -> SubScore:
    profile = client.get_community_profile(owner, repo) or {}
    files = (profile.get("files") or {}) if isinstance(profile, dict) else {}

    present_map = {
        "readme": bool(files.get("readme")),
        "license": bool(files.get("license")),
        "contributing": bool(files.get("contributing")),
        "security_policy": bool(files.get("security_policy")),
        "code_of_conduct": bool(files.get("code_of_conduct")) or bool(files.get("code_of_conduct_file")),
        "issue_template": bool(files.get("issue_template")),
        "pull_request_template": bool(files.get("pull_request_template")),
    }

    # Setup instructions: heuristics in README content
    readme_text: Optional[str] = None
    if not present_map["readme"]:
        # try raw readme path
        readme_text = client.get_file_content(owner, repo, "README.md") or client.get_file_content(owner, repo, "README.rst")
    else:
        # Community profile confirms presence; still fetch to analyze setup instructions
        readme_text = client.get_file_content(owner, repo, "README.md") or client.get_file_content(owner, repo, "README.rst")

    setup_present = False
    if readme_text:
        lower = readme_text.lower()
        setup_present = any(
            h in lower
            for h in ["getting started", "installation", "install", "setup", "usage", "quickstart"]
        )

    # Apply points: 1 point per item, setup included to align with 7 total per policy section
    points = sum(1 for k in present_map if present_map[k])
    points += 1 if setup_present else 0

    max_points = 7  # As described in Section 2 bullets

    missing = [desc for key, desc in DOC_ITEMS if not present_map.get(key)]
    if not setup_present:
        missing.append("Setup & configuration instructions in README")

    return SubScore(
        name="Documentation Maturity",
        max_points=max_points,
        points=min(points, max_points),
        details={
            "present": [desc for key, desc in DOC_ITEMS if present_map.get(key)],
            "missing": missing,
        },
    )


def _score_infrastructure(client: GitHubClient, owner: str, repo: str) -> List[SubScore]:
    tree = client.list_repo_tree(owner, repo)
    tree_paths = _collect_tree_paths(tree)
    workflow_texts = _get_workflow_texts(client, owner, repo)

    def contains_any(hints: List[str]) -> bool:
        for text in workflow_texts:
            if any(h in text for h in hints):
                return True
        return False

    # Automated Tests (3)
    has_test_files = any(pat.search(p) for p in tree_paths for pat in TEST_FILE_PATTERNS)
    tests_in_ci = contains_any(TEST_HINTS)
    test_points = 0
    if has_test_files:
        test_points += 2
    if tests_in_ci:
        test_points += 1
    tests_score = SubScore(
        name="Automated Tests",
        max_points=3,
        points=min(test_points, 3),
        details={"has_test_files": has_test_files, "tests_in_ci": tests_in_ci},
    )

    # CI/CD Pipelines (3)
    has_ci_dir = _path_exists([".github/workflows/"], tree_paths)
    has_release_steps = contains_any(RELEASE_HINTS)
    has_build_steps = contains_any(BUILD_HINTS)
    ci_points = 0
    if has_ci_dir:
        ci_points += 1
    if has_build_steps:
        ci_points += 1
    if has_release_steps:
        ci_points += 1
    cicd_score = SubScore(
        name="CI/CD Pipelines",
        max_points=3,
        points=min(ci_points, 3),
        details={"has_ci": has_ci_dir, "build_in_ci": has_build_steps, "release_in_ci": has_release_steps},
    )

    # Security Scanning (2)
    has_scanning = contains_any(CODE_SCANNING_HINTS)
    security_points = 2 if has_scanning else 0
    security_score = SubScore(
        name="Security Scanning",
        max_points=2,
        points=security_points,
        details={"scanning_in_ci": has_scanning},
    )

    # Dependency Updates (2)
    has_dep_updates = _path_exists(DEPENDENCY_UPDATE_FILES, tree_paths)
    dep_points = 2 if has_dep_updates else 0
    dep_score = SubScore(
        name="Dependency Updates",
        max_points=2,
        points=dep_points,
        details={"dependabot_or_renovate": has_dep_updates},
    )

    # Linting/Formatting (2)
    has_lint_config = _path_exists(LINTER_CONFIG_NAMES, tree_paths)
    lint_in_ci = contains_any(LINT_HINTS)
    lint_points = 2 if (has_lint_config and lint_in_ci) else (1 if (has_lint_config or lint_in_ci) else 0)
    lint_score = SubScore(
        name="Linting/Formatting",
        max_points=2,
        points=lint_points,
        details={"lint_config": has_lint_config, "lint_in_ci": lint_in_ci},
    )

    # Release Management (2)
    tags = client.list_tags(owner, repo)
    releases = client.list_releases(owner, repo)
    has_changelog = any(
        _path_exists([p], tree_paths)
        for p in ["CHANGELOG.md", "changelog.md", "CHANGELOG", "docs/CHANGELOG.md"]
    )
    rel_points = 0
    if tags:
        rel_points += 1
    if releases or has_changelog:
        rel_points += 1
    release_score = SubScore(
        name="Release Management",
        max_points=2,
        points=min(rel_points, 2),
        details={"tags": len(tags), "releases": len(releases), "has_changelog": has_changelog},
    )

    # Build & Packaging Tools (2)
    has_build_packaging = _path_exists(BUILD_PACKAGING_FILES, tree_paths)
    build_points = 2 if has_build_packaging else 0
    build_score = SubScore(
        name="Build & Packaging Tools",
        max_points=2,
        points=build_points,
        details={"has_build_or_packaging_files": has_build_packaging},
    )

    # Infrastructure as Code (1)
    has_iac = _path_exists(IAC_FILES, tree_paths) or any(
        p.startswith("k8s/") or p.startswith("deploy/") or p.startswith("infra/") for p in tree_paths
    )
    iac_score = SubScore(
        name="Infrastructure as Code",
        max_points=1,
        points=1 if has_iac else 0,
        details={"has_iac": has_iac},
    )

    # Platform Integration (1)
    has_platform = _path_exists(CI_CONFIG_FILES, tree_paths)
    platform_score = SubScore(
        name="Platform Integration",
        max_points=1,
        points=1 if has_platform else 0,
        details={"has_ci_config": has_platform},
    )

    return [
        tests_score,
        cicd_score,
        security_score,
        dep_score,
        lint_score,
        release_score,
        build_score,
        iac_score,
        platform_score,
    ]


def _score_health(client: GitHubClient, owner: str, repo: str) -> List[SubScore]:
    repo_data = client.get_repo(owner, repo)
    stars = repo_data.get("stargazers_count", 0)
    forks = repo_data.get("forks_count", 0)
    watchers = repo_data.get("subscribers_count", 0) or repo_data.get("watchers_count", 0)
    open_issues = repo_data.get("open_issues_count", 0)
    archived = bool(repo_data.get("archived", False))

    # Community Engagement (0-2)
    ce_points = 0
    if stars >= 25 or forks >= 10 or open_issues >= 25:
        ce_points = 2
    elif stars >= 5 or forks >= 2 or open_issues >= 5:
        ce_points = 1
    community_score = SubScore(
        name="Community Engagement",
        max_points=2,
        points=ce_points,
        details={"stars": stars, "forks": forks, "open_issues": open_issues},
    )

    # Governance & Leadership (0-2)
    tree = client.list_repo_tree(owner, repo)
    tree_paths = _collect_tree_paths(tree)
    has_codeowners = _path_exists(["CODEOWNERS", ".github/CODEOWNERS"], tree_paths)
    has_governance = _path_exists(["GOVERNANCE.md", "MAINTAINERS", "OWNERS"], tree_paths)
    gl_points = 2 if (has_codeowners and has_governance) else (1 if (has_codeowners or has_governance) else 0)
    governance_score = SubScore(
        name="Governance & Leadership",
        max_points=2,
        points=gl_points,
        details={"codeowners": has_codeowners, "governance_docs": has_governance},
    )

    # Succession Planning (0-2): unique committers in last 90 days
    since = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(days=90)
    commits = client.list_commits_since(owner, repo, since)
    authors = set()
    for c in commits:
        # Prefer GitHub usernames when available
        login = (c.get("author") or {}).get("login")
        if login:
            authors.add(login)
        else:
            name = (c.get("commit") or {}).get("author", {}).get("name")
            if name:
                authors.add(name)
    num_authors = len(authors)
    sp_points = 2 if num_authors >= 4 else (1 if num_authors >= 2 else 0)
    succession_score = SubScore(
        name="Succession Planning",
        max_points=2,
        points=sp_points,
        details={"active_maintainers_90d": num_authors},
    )

    # Ecosystem Importance (0-2) proxy via forks/watchers
    ei_points = 2 if (forks >= 20 or watchers >= 50) else (1 if (forks >= 5 or watchers >= 15) else 0)
    ecosystem_score = SubScore(
        name="Ecosystem Importance",
        max_points=2,
        points=ei_points,
        details={"forks": forks, "watchers": watchers},
    )

    # Activity Trend (0-2)
    latest = client.get_latest_commit_datetime(owner, repo)
    days_since = 9999
    if latest:
        days_since = (dt.datetime.now(tz=dt.timezone.utc) - latest).days
    at_points = 2 if days_since <= 30 else (1 if days_since <= 90 else 0)
    activity_score = SubScore(
        name="Activity Trend",
        max_points=2,
        points=at_points,
        details={"days_since_last_commit": days_since},
    )

    # Sustainability & Risks (0-2)
    has_security = _path_exists(["SECURITY.md", ".github/SECURITY.md"], tree_paths)
    sr_points = 0
    if archived:
        sr_points = 0
    else:
        # One point for security policy, one for >=3 active committers in last 90d
        sr_points = (1 if has_security else 0) + (1 if num_authors >= 3 else 0)
    sustainability_score = SubScore(
        name="Sustainability & Risks",
        max_points=2,
        points=min(sr_points, 2),
        details={"security_policy": has_security, "archived": archived},
    )

    return [
        community_score,
        governance_score,
        succession_score,
        ecosystem_score,
        activity_score,
        sustainability_score,
    ]


def assess_repository(client: GitHubClient, owner: str, repo: str) -> RepositoryAssessment:
    doc = _score_documentation(client, owner, repo)
    infra = _score_infrastructure(client, owner, repo)
    health = _score_health(client, owner, repo)
    return RepositoryAssessment(
        owner=owner,
        repo=repo,
        documentation_score=doc,
        infrastructure_score=infra,
        health_score=health,
    )
