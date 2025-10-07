from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

from .github_client import GitHubClient
from .scoring import RepositoryAssessment, assess_repository


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate open source health of GitHub repositories per Section 2 (Project Maturity Tiers 2025)."
        )
    )
    parser.add_argument(
        "--token",
        help="GitHub API token. Defaults to $GITHUB_TOKEN",
        default=os.environ.get("GITHUB_TOKEN"),
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        help="One or more repositories in owner/repo format",
    )
    parser.add_argument(
        "--org",
        help="GitHub organization to scan public repositories",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of repositories when scanning an org",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Include detailed breakdowns in JSON output",
    )

    args = parser.parse_args(argv)
    if not args.token:
        parser.error("GitHub token is required (pass --token or set GITHUB_TOKEN)")
    if not args.repos and not args.org:
        parser.error("Either --repos or --org must be provided")
    return args


def _format_table(results: List[RepositoryAssessment]) -> str:
    # Build a simple fixed-width table
    headers = [
        "Repository",
        "Docs (0-7)",
        "Infra (0-18)",
        "Health (0-12)",
        "Total (0-37)",
        "Health Label",
        "Maturity",
    ]
    rows: List[List[str]] = []
    for r in results:
        rows.append(
            [
                f"{r.owner}/{r.repo}",
                f"{r.documentation_score.points}/{r.documentation_score.max_points}",
                f"{r.total_infrastructure_points}/{r.max_infrastructure_points}",
                f"{r.total_health_points}/{r.max_health_points}",
                f"{r.total_points:.1f}",
                r.health_label,
                r.maturity_tier,
            ]
        )

    # Compute column widths
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * widths[i] for i in range(len(headers)))
    out_lines = [line, sep]
    for row in rows:
        out_lines.append(" | ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(out_lines)


def _serialize(result: RepositoryAssessment, details: bool) -> Dict[str, Any]:
    return {
        "repository": f"{result.owner}/{result.repo}",
        "documentation": {
            "score": result.documentation_score.points,
            "max": result.documentation_score.max_points,
            "details": result.documentation_score.details if details else None,
        },
        "infrastructure": {
            "score": result.total_infrastructure_points,
            "max": result.max_infrastructure_points,
            "breakdown": [
                {"name": s.name, "points": s.points, "max": s.max_points, "details": s.details if details else None}
                for s in result.infrastructure_score
            ] if details else None,
        },
        "health": {
            "score": result.total_health_points,
            "max": result.max_health_points,
            "breakdown": [
                {"name": s.name, "points": s.points, "max": s.max_points, "details": s.details if details else None}
                for s in result.health_score
            ] if details else None,
            "label": result.health_label,
        },
        "total": result.total_points,
        "maturity": result.maturity_tier,
    }


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    client = GitHubClient(args.token)

    targets: List[Tuple[str, str]] = []
    if args.repos:
        for spec in args.repos:
            if "/" not in spec:
                print(f"Invalid repo spec: {spec}. Expected owner/repo", file=sys.stderr)
                return 2
            owner, repo = spec.split("/", 1)
            targets.append((owner, repo))
    else:
        repos = client.list_org_repos(args.org)
        if args.limit is not None:
            repos = repos[: args.limit]
        for r in repos:
            targets.append((r["owner"]["login"], r["name"]))

    results: List[RepositoryAssessment] = []
    for owner, repo in targets:
        try:
            results.append(assess_repository(client, owner, repo))
        except Exception as e:
            print(f"Error assessing {owner}/{repo}: {e}", file=sys.stderr)

    if args.format == "json":
        payload = [_serialize(r, args.details) for r in results]
        print(json.dumps(payload, indent=2))
    else:
        print(_format_table(results))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
