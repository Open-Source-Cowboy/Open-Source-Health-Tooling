from __future__ import annotations

import base64
import datetime as dt
import json
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

ISO_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
)


def _parse_iso8601(value: str) -> dt.datetime:
    for fmt in ISO_FORMATS:
        try:
            return dt.datetime.strptime(value, fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    # Fallback best-effort
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)


class GitHubClient:
    def __init__(self, token: str, base_url: str = "https://api.github.com") -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "oss-health-checker/1.0",
            }
        )

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        # Reasonable per_page default for list endpoints
        params = kwargs.pop("params", {})
        if "per_page" not in params:
            params["per_page"] = 100
        kwargs["params"] = params

        response = self.session.request(method, url, timeout=30, **kwargs)

        # Handle abuse detection/rate limiting gracefully
        if response.status_code == 403 and "Retry-After" in response.headers:
            try:
                delay = int(response.headers["Retry-After"]) + 1
                time.sleep(delay)
                response = self.session.request(method, url, timeout=30, **kwargs)
            except Exception:
                pass

        return response

    def _paginate(self, method: str, path: str, **kwargs) -> Iterable[Dict[str, Any]]:
        page = 1
        while True:
            params = kwargs.get("params", {}).copy()
            params["page"] = page
            kwargs["params"] = params
            resp = self._request(method, path, **kwargs)
            if resp.status_code == 404:
                return
            resp.raise_for_status()
            items = resp.json()
            if not isinstance(items, list) or not items:
                if isinstance(items, list):
                    return
                # Non-list response, stop paginating
                yield items
                return
            for item in items:
                yield item
            # If less than per_page returned, end
            if len(items) < kwargs["params"].get("per_page", 100):
                return
            page += 1

    def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        resp = self._request("GET", f"/repos/{owner}/{repo}")
        resp.raise_for_status()
        return resp.json()

    def list_org_repos(self, org: str) -> List[Dict[str, Any]]:
        repos = list(self._paginate("GET", f"/orgs/{org}/repos", params={"type": "public"}))
        # Filter only public explicitly
        return [r for r in repos if not r.get("private", False)]

    def get_community_profile(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        resp = self._request("GET", f"/repos/{owner}/{repo}/community/profile")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_default_branch_sha(self, owner: str, repo: str) -> Optional[str]:
        repo_data = self.get_repo(owner, repo)
        default_branch = repo_data.get("default_branch")
        if not default_branch:
            return None
        resp = self._request("GET", f"/repos/{owner}/{repo}/git/refs/heads/{default_branch}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        # data can be a list in some cases, handle object shape
        object_data = data[0]["object"] if isinstance(data, list) else data.get("object", {})
        return object_data.get("sha")

    def list_repo_tree(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        sha = self.get_default_branch_sha(owner, repo)
        if not sha:
            return []
        resp = self._request("GET", f"/repos/{owner}/{repo}/git/trees/{sha}", params={"recursive": 1})
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("tree", [])

    def list_workflows(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        resp = self._request("GET", f"/repos/{owner}/{repo}/actions/workflows")
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json() or {}
        return data.get("workflows", [])

    def get_file_content(self, owner: str, repo: str, path: str) -> Optional[str]:
        resp = self._request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            headers={"Accept": "application/vnd.github.v3.raw"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        # If we asked for raw, text content is returned
        if resp.headers.get("Content-Type", "").startswith("text/"):
            return resp.text
        try:
            data = resp.json()
            if isinstance(data, dict) and data.get("encoding") == "base64":
                return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        except Exception:
            pass
        return None

    def file_exists(self, owner: str, repo: str, path: str) -> bool:
        resp = self._request("GET", f"/repos/{owner}/{repo}/contents/{path}")
        return resp.status_code == 200

    def list_tags(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        return list(self._paginate("GET", f"/repos/{owner}/{repo}/tags"))

    def list_releases(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        return list(self._paginate("GET", f"/repos/{owner}/{repo}/releases"))

    def list_commits_since(self, owner: str, repo: str, since: dt.datetime) -> List[Dict[str, Any]]:
        params = {"since": since.replace(tzinfo=dt.timezone.utc).isoformat()}
        return list(self._paginate("GET", f"/repos/{owner}/{repo}/commits", params=params))

    def get_latest_commit_datetime(self, owner: str, repo: str) -> Optional[dt.datetime]:
        repo_data = self.get_repo(owner, repo)
        pushed_at = repo_data.get("pushed_at")
        if pushed_at:
            return _parse_iso8601(pushed_at)
        # Fallback to last commit
        commits = list(self._paginate("GET", f"/repos/{owner}/{repo}/commits", params={"per_page": 1}))
        if commits:
            commit = commits[0]
            date = commit.get("commit", {}).get("committer", {}).get("date")
            if date:
                return _parse_iso8601(date)
        return None
