#!/usr/bin/env node

const { GitHubClient } = require('./githubClient');
const { assessRepository } = require('./scoring');

function parseArgs(argv) {
  const args = {
    token: process.env.GITHUB_TOKEN || null,
    repos: [],
    org: null,
    limit: null,
    format: 'table',
    details: false,
  };

  // Simple arg parsing; keep compatible-ish with Python CLI where possible
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--token') args.token = argv[++i];
    else if (a === '--repos') {
      const list = [];
      for (let j = i + 1; j < argv.length && !argv[j].startsWith('--'); j++) list.push(argv[j]);
      args.repos.push(...list);
      i += list.length;
    } else if (a === '--org') args.org = argv[++i];
    else if (a === '--limit') args.limit = Number(argv[++i]);
    else if (a === '--format') args.format = argv[++i];
    else if (a === '--details') args.details = true;
  }

  if (!args.token) throw new Error('GitHub token is required (pass --token or set GITHUB_TOKEN)');
  if (args.repos.length === 0 && !args.org) {
    throw new Error('Either --repos or --org must be provided');
  }
  if (!['json', 'table'].includes(args.format)) args.format = 'table';
  return args;
}

function formatTable(results) {
  const headers = ['Repository', 'Docs (0-7)', 'Infra (0-18)', 'Health (0-12)', 'Total (0-37)', 'Health Label', 'Maturity'];
  const rows = results.map((r) => [
    `${r.owner}/${r.repo}`,
    `${r.documentationScore.points}/7`,
    `${r.totalInfrastructurePoints}/${r.maxInfrastructurePoints}`,
    `${r.totalHealthPoints}/${r.maxHealthPoints}`,
    `${r.totalPoints.toFixed(1)}`,
    r.healthLabel,
    r.maturityTier,
  ]);
  const widths = headers.map((h, idx) => Math.max(h.length, ...rows.map((row) => String(row[idx]).length)));
  const line = headers.map((h, i) => h.padEnd(widths[i])).join(' | ');
  const sep = widths.map((w) => '-'.repeat(w)).join('-+-');
  const out = [line, sep];
  for (const row of rows) out.push(row.map((v, i) => String(v).padEnd(widths[i])).join(' | '));
  return out.join('\n');
}

function serialize(result, details) {
  return {
    repository: `${result.owner}/${result.repo}`,
    documentation: {
      score: result.documentationScore.points,
      max: result.documentationScore.maxPoints || 7,
      details: details ? result.documentationScore.details : null,
    },
    infrastructure: {
      score: result.totalInfrastructurePoints,
      max: result.maxInfrastructurePoints,
      breakdown: details
        ? result.infrastructureScore.map((s) => ({ name: s.name, points: s.points, max: s.maxPoints, details: s.details }))
        : null,
    },
    health: {
      score: result.totalHealthPoints,
      max: result.maxHealthPoints,
      breakdown: details
        ? result.healthScore.map((s) => ({ name: s.name, points: s.points, max: s.maxPoints, details: s.details }))
        : null,
      label: result.healthLabel,
    },
    total: result.totalPoints,
    maturity: result.maturityTier,
  };
}

async function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    const client = new GitHubClient(args.token);

    const targets = [];
    if (args.repos && args.repos.length > 0) {
      for (const spec of args.repos) {
        if (!spec.includes('/')) throw new Error(`Invalid repo spec: ${spec}. Expected owner/repo`);
        const [owner, repo] = spec.split('/', 2);
        targets.push({ owner, repo });
      }
    } else {
      const repos = await client.listOrgRepos(args.org);
      const limited = (args.limit == null) ? repos : repos.slice(0, args.limit);
      for (const r of limited) {
        targets.push({ owner: r.owner.login, repo: r.name });
      }
    }

    const results = [];
    for (const t of targets) {
      try {
        results.push(await assessRepository(client, t.owner, t.repo));
      } catch (e) {
        console.error(`Error assessing ${t.owner}/${t.repo}: ${e.message || e}`);
      }
    }

    if (args.format === 'json') {
      const payload = results.map((r) => serialize(r, args.details));
      process.stdout.write(JSON.stringify(payload, null, 2) + '\n');
    } else {
      process.stdout.write(formatTable(results) + '\n');
    }

    return 0;
  } catch (e) {
    console.error(e.message || e);
    return 2;
  }
}

if (require.main === module) {
  main().then((code) => process.exit(code));
}
