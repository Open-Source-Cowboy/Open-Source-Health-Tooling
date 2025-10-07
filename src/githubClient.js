/*
  Minimal GitHub REST API client for Node.js
  Mirrors the Python client's methods used by the Section 2 scoring logic.
*/

const DEFAULT_BASE_URL = process.env.GITHUB_URL
  ? String(process.env.GITHUB_URL).replace(/\/$/, '')
  : 'https://api.github.com';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseIso8601(value) {
  // Try common formats, otherwise rely on Date parsing
  const dt = new Date(value);
  if (!Number.isNaN(dt.getTime())) return dt;
  return new Date(0);
}

class GitHubClient {
  constructor(token, baseUrl = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    if (!token) {
      throw new Error('GitHub token is required (env GITHUB_TOKEN or --token).');
    }
    this.token = token;
    this.defaultHeaders = {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'oss-health-checker-node/1.0',
    };
  }

  async _request(method, path, { params, headers } = {}) {
    const url = new URL(`${this.baseUrl}${path}`);
    const qp = new URLSearchParams();
    const mergedParams = { per_page: 100, ...(params || {}) };
    for (const [k, v] of Object.entries(mergedParams)) {
      if (v === undefined || v === null) continue;
      qp.set(k, String(v));
    }
    url.search = qp.toString();

    const res = await fetch(url, {
      method,
      headers: { ...this.defaultHeaders, ...(headers || {}) },
      // 30s timeout via AbortController if needed; Node 22 default fetch has no timeout
    });

    if (res.status === 403 && res.headers.has('retry-after')) {
      const delay = Number(res.headers.get('retry-after'));
      if (!Number.isNaN(delay)) {
        await sleep((delay + 1) * 1000);
        return this._request(method, path, { params, headers });
      }
    }

    return res;
  }

  async _jsonOrNull(res) {
    if (res.status === 404) return null;
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`GitHub API error ${res.status}: ${text}`);
    }
    try {
      return await res.json();
    } catch (_) {
      return null;
    }
  }

  async _paginate(method, path, { params, headers } = {}) {
    const items = [];
    let page = 1;
    while (true) {
      const res = await this._request(method, path, { params: { ...(params || {}), page }, headers });
      if (res.status === 404) return items;
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`GitHub API error ${res.status}: ${text}`);
      }
      let data;
      try {
        data = await res.json();
      } catch {
        data = null;
      }
      if (!Array.isArray(data) || data.length === 0) {
        if (Array.isArray(data)) return items;
        if (data && typeof data === 'object') {
          items.push(data);
        }
        return items;
      }
      items.push(...data);
      const perPage = Number((params && params.per_page) || 100);
      if (data.length < perPage) return items;
      page += 1;
    }
  }

  async getRepo(owner, repo) {
    const res = await this._request('GET', `/repos/${owner}/${repo}`);
    return this._jsonOrNull(res);
  }

  async listOrgRepos(org) {
    const repos = await this._paginate('GET', `/orgs/${org}/repos`, { params: { type: 'public' } });
    return (repos || []).filter((r) => !(r && r.private));
  }

  async getCommunityProfile(owner, repo) {
    const res = await this._request('GET', `/repos/${owner}/${repo}/community/profile`);
    return this._jsonOrNull(res);
  }

  async getDefaultBranchSha(owner, repo) {
    const repoData = await this.getRepo(owner, repo);
    if (!repoData) return null;
    const def = repoData.default_branch;
    if (!def) return null;
    const res = await this._request('GET', `/repos/${owner}/${repo}/git/refs/heads/${def}`);
    if (res.status === 404) return null;
    let data;
    try {
      data = await res.json();
    } catch {
      return null;
    }
    if (Array.isArray(data)) {
      const obj = data[0] && data[0].object;
      return obj ? obj.sha : null;
    }
    const obj = data && data.object;
    return obj ? obj.sha : null;
  }

  async listRepoTree(owner, repo) {
    const sha = await this.getDefaultBranchSha(owner, repo);
    if (!sha) return [];
    const res = await this._request('GET', `/repos/${owner}/${repo}/git/trees/${sha}`, { params: { recursive: 1 } });
    const data = await this._jsonOrNull(res);
    return data && Array.isArray(data.tree) ? data.tree : [];
  }

  async listWorkflows(owner, repo) {
    const res = await this._request('GET', `/repos/${owner}/${repo}/actions/workflows`);
    const data = await this._jsonOrNull(res);
    return data && Array.isArray(data.workflows) ? data.workflows : [];
  }

  async getFileContent(owner, repo, path) {
    const res = await this._request('GET', `/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}`, {
      headers: { Accept: 'application/vnd.github.v3.raw' },
    });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.startsWith('text/') || contentType.includes('json')) {
      return await res.text();
    }
    try {
      return await res.text();
    } catch {
      return null;
    }
  }

  async fileExists(owner, repo, path) {
    const res = await this._request('GET', `/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}`);
    return res.status === 200;
  }

  async listTags(owner, repo) {
    return await this._paginate('GET', `/repos/${owner}/${repo}/tags`);
  }

  async listReleases(owner, repo) {
    return await this._paginate('GET', `/repos/${owner}/${repo}/releases`);
  }

  async listCommitsSince(owner, repo, sinceDate) {
    const since = new Date(sinceDate);
    const iso = since.toISOString();
    return await this._paginate('GET', `/repos/${owner}/${repo}/commits`, { params: { since: iso } });
  }

  async getLatestCommitDatetime(owner, repo) {
    const repoData = await this.getRepo(owner, repo);
    if (!repoData) return null;
    const pushed = repoData.pushed_at;
    if (pushed) return parseIso8601(pushed);
    const res = await this._request('GET', `/repos/${owner}/${repo}/commits`, { params: { per_page: 1 } });
    if (res.status === 404 || !res.ok) return null;
    let data;
    try {
      data = await res.json();
    } catch {
      return null;
    }
    const commit = Array.isArray(data) && data[0];
    const date = commit && commit.commit && commit.commit.committer && commit.commit.committer.date;
    return date ? parseIso8601(date) : null;
  }
}

module.exports = { GitHubClient };
