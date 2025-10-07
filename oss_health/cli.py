from __future__ import annotations

import argparse
import json
import os
import sys
import datetime as dt
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
    parser.add_argument(
        "--pdf",
        metavar="PATH",
        help="Optional: write a nicely formatted PDF report to this path",
    )
    parser.add_argument(
        "--title",
        default="OSS Health Report",
        help="Optional: title for the PDF report (default: OSS Health Report)",
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


def _export_pdf(
    results: List[RepositoryAssessment],
    output_path: str,
    title: str,
    include_details: bool,
) -> None:
    """Render results to a simple, readable PDF file."""
    try:
        from fpdf import FPDF  # Lazy import to avoid hard dependency unless used
    except Exception as e:
        raise RuntimeError(
            "PDF export requires fpdf2. Install with: pip install fpdf2"
        ) from e

    class PDFReport(FPDF):
        def __init__(self, report_title: str) -> None:
            super().__init__(orientation="L", unit="mm", format="A4")
            self.report_title = report_title

        def header(self) -> None:
            self.set_font("Helvetica", "B", 14)
            self.cell(0, 8, self.report_title, ln=True)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(90, 90, 90)
            now_text = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            self.cell(0, 6, f"Generated: {now_text}", ln=True)
            self.ln(2)
            self.set_text_color(0, 0, 0)

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(120, 120, 120)
            self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="R")
            self.set_text_color(0, 0, 0)

    pdf = PDFReport(title)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Summary table
    headers = [
        "Repository",
        "Docs (0-7)",
        "Infra (0-18)",
        "Health (0-12)",
        "Total (0-37)",
        "Health Label",
        "Maturity",
    ]

    # Column widths tuned for A4 landscape and 10pt font
    col_widths = [
        90.0,  # Repository
        26.0,  # Docs
        30.0,  # Infra
        26.0,  # Health
        26.0,  # Total
        34.0,  # Health Label
        34.0,  # Maturity
    ]

    pdf.set_font("Helvetica", "B", 10)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    for r in results:
        row = [
            f"{r.owner}/{r.repo}",
            f"{r.documentation_score.points}/{r.documentation_score.max_points}",
            f"{r.total_infrastructure_points}/{r.max_infrastructure_points}",
            f"{r.total_health_points}/{r.max_health_points}",
            f"{r.total_points:.1f}",
            r.health_label,
            r.maturity_tier,
        ]
        for i, val in enumerate(row):
            align = "L" if i == 0 else "C"
            pdf.cell(col_widths[i], 8, str(val), border=1, align=align)
        pdf.ln()

    if include_details and results:
        for idx, r in enumerate(results, start=1):
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, f"Details: {r.owner}/{r.repo}", ln=True)
            pdf.ln(2)

            def section(title_text: str) -> None:
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 7, title_text, ln=True)
                pdf.set_font("Helvetica", "", 10)

            def keyvals(items: Dict[str, Any]) -> None:
                # Render key: value pairs as wrapped text lines
                for k, v in items.items():
                    pdf.multi_cell(0, 6, f"- {k}: {v}")

            # Documentation
            section("Documentation")
            doc = r.documentation_score
            pdf.multi_cell(0, 6, f"Score: {doc.points}/{doc.max_points}")
            details = doc.details or {}
            present = details.get("present") or []
            missing = details.get("missing") or []
            if present:
                pdf.multi_cell(0, 6, "Present: " + ", ".join(present))
            if missing:
                pdf.multi_cell(0, 6, "Missing: " + ", ".join(missing))
            pdf.ln(2)

            # Infrastructure breakdown
            section("Technical Infrastructure")
            for s in r.infrastructure_score:
                pdf.set_font("Helvetica", "B", 10)
                pdf.multi_cell(0, 6, f"{s.name}: {s.points}/{s.max_points}")
                pdf.set_font("Helvetica", "", 10)
                if s.details:
                    keyvals(s.details)
            pdf.ln(1)

            # Health breakdown
            section("Health & Sustainability")
            for s in r.health_score:
                pdf.set_font("Helvetica", "B", 10)
                pdf.multi_cell(0, 6, f"{s.name}: {s.points}/{s.max_points}")
                pdf.set_font("Helvetica", "", 10)
                if s.details:
                    keyvals(s.details)
            pdf.ln(1)

    # Write file
    try:
        # Ensure directory exists if a directory component is present
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        pdf.output(output_path)
    except Exception as e:
        raise RuntimeError(f"Failed to write PDF to {output_path}: {e}") from e


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

    if args.pdf:
        try:
            _export_pdf(results, args.pdf, args.title, include_details=args.details)
            print(f"Saved PDF report to {args.pdf}")
        except Exception as e:
            print(f"Error generating PDF: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
