/*
  Section 2 scoring logic (Node port) matching the Python implementation in oss_health/scoring.py
*/

const DOC_ITEMS = [
  ['readme', 'README present'],
  ['license', 'LICENSE present'],
  ['contributing', 'CONTRIBUTING present'],
  ['security_policy', 'SECURITY policy present'],
  ['code_of_conduct', 'CODE_OF_CONDUCT present'],
  ['issue_template', 'Issue template present'],
  ['pull_request_template', 'PR template present'],
];

const LINTER_CONFIG_NAMES = [
  // JS/TS
  '.eslintrc.js',
  '.eslintrc.cjs',
  '.eslintrc.json',
  '.eslintrc.yml',
  '.eslintrc.yaml',
  '.prettierrc',
  '.prettierrc.json',
  '.prettierrc.yml',
  '.prettierrc.yaml',
  'prettier.config.js',
  'prettier.config.cjs',
  // Python
  '.flake8',
  'pyproject.toml',
  'setup.cfg',
  '.pylintrc',
  'ruff.toml',
  // Go
  '.golangci.yml',
  '.golangci.yaml',
  // Rust
  'rustfmt.toml',
  // General
  '.editorconfig',
];

const BUILD_PACKAGING_FILES = [
  // General
  'Makefile',
  'Dockerfile',
  'docker-compose.yml',
  // Node
  'package.json',
  'pnpm-lock.yaml',
  'yarn.lock',
  // Python
  'pyproject.toml',
  'setup.py',
  'requirements.txt',
  // Rust
  'Cargo.toml',
  // Go
  'go.mod',
  // Java
  'pom.xml',
  'build.gradle',
  'build.gradle.kts',
  // C/C++
  'CMakeLists.txt',
  // Nix
  'flake.nix',
];

const IAC_FILES = [
  'main.tf',
  'terraform.tfvars',
  'chart.yaml',
  'Chart.yaml',
  'values.yaml',
  'kustomization.yaml',
  'playbook.yml',
  'playbook.yaml',
];

const CI_CONFIG_FILES = [
  '.github/workflows',
  '.circleci/config.yml',
  '.travis.yml',
  'azure-pipelines.yml',
  '.gitlab-ci.yml',
];

const TEST_FILE_PATTERNS = [
  // regex strings for quick check
  /(^|\/)tests?(\/|$)/i,
  /(^|\/).*((_|\.)test|\.spec\.)/i,
];

const CODE_SCANNING_HINTS = ['codeql', 'trivy', 'snyk', 'semgrep', 'bandit', 'gosec'];
const LINT_HINTS = ['eslint', 'flake8', 'ruff', 'pylint', 'prettier', 'golangci-lint', 'clang-tidy'];
const BUILD_HINTS = [
  'make ',
  'docker build',
  'npm run build',
  'pnpm build',
  'yarn build',
  'mvn package',
  'gradle build',
  'cmake ',
  'cargo build',
  'go build',
];
const TEST_HINTS = [
  'pytest',
  'python -m pytest',
  'npm test',
  'pnpm test',
  'yarn test',
  'go test',
  'cargo test',
  'mvn test',
];
const RELEASE_HINTS = ['gh release', 'actions/create-release', 'softprops/action-gh-release', 'semantic-release'];

function pathExists(paths, treePaths) {
  for (const p of paths) {
    if (p.endsWith('/')) {
      const prefix = p.replace(/\/$/, '') + '/';
      if (treePaths.some((tp) => tp.startsWith(prefix))) return true;
    } else {
      if (treePaths.includes(p)) return true;
    }
  }
  return false;
}

function collectTreePaths(tree) {
  return tree.map((t) => t.path || '');
}

async function getWorkflowTexts(client, owner, repo) {
  const workflows = await client.listWorkflows(owner, repo);
  const texts = [];
  for (const wf of workflows) {
    const p = wf && wf.path;
    if (!p) continue;
    const content = await client.getFileContent(owner, repo, p);
    if (content) texts.push(String(content).toLowerCase());
  }
  return texts;
}

async function scoreDocumentation(client, owner, repo) {
  const profile = (await client.getCommunityProfile(owner, repo)) || {};
  const files = (profile.files || {});
  const presentMap = {
    readme: Boolean(files.readme),
    license: Boolean(files.license),
    contributing: Boolean(files.contributing),
    security_policy: Boolean(files.security_policy),
    code_of_conduct: Boolean(files.code_of_conduct || files.code_of_conduct_file),
    issue_template: Boolean(files.issue_template),
    pull_request_template: Boolean(files.pull_request_template),
  };

  let readmeText = null;
  // Try to fetch README content to detect setup/installation hints
  const candidates = ['README.md', 'README.rst'];
  for (const c of candidates) {
    const txt = await client.getFileContent(owner, repo, c);
    if (txt) {
      readmeText = txt;
      break;
    }
  }

  let setupPresent = false;
  if (readmeText) {
    const lower = String(readmeText).toLowerCase();
    setupPresent = ['getting started', 'installation', 'install', 'setup', 'usage', 'quickstart'].some((h) => lower.includes(h));
  }

  let points = Object.values(presentMap).filter(Boolean).length;
  if (setupPresent) points += 1;
  const maxPoints = 7;

  const missing = DOC_ITEMS.filter(([k]) => !presentMap[k]).map(([, desc]) => desc);
  if (!setupPresent) missing.push('Setup & configuration instructions in README');

  return {
    name: 'Documentation Maturity',
    maxPoints,
    points: Math.min(points, maxPoints),
    details: {
      present: DOC_ITEMS.filter(([k]) => presentMap[k]).map(([, d]) => d),
      missing,
    },
  };
}

async function scoreInfrastructure(client, owner, repo) {
  const tree = await client.listRepoTree(owner, repo);
  const treePaths = collectTreePaths(tree);
  const workflowTexts = await getWorkflowTexts(client, owner, repo);

  function containsAny(hints) {
    for (const text of workflowTexts) {
      if (hints.some((h) => text.includes(h))) return true;
    }
    return false;
  }

  // Automated Tests (3)
  const hasTestFiles = treePaths.some((p) => TEST_FILE_PATTERNS.some((re) => re.test(p)));
  const testsInCi = containsAny(TEST_HINTS);
  let testPoints = 0;
  if (hasTestFiles) testPoints += 2;
  if (testsInCi) testPoints += 1;
  const testsScore = {
    name: 'Automated Tests',
    maxPoints: 3,
    points: Math.min(testPoints, 3),
    details: { has_test_files: hasTestFiles, tests_in_ci: testsInCi },
  };

  // CI/CD Pipelines (3)
  const hasCiDir = pathExists(['.github/workflows/'], treePaths);
  const hasReleaseSteps = containsAny(RELEASE_HINTS);
  const hasBuildSteps = containsAny(BUILD_HINTS);
  let ciPoints = 0;
  if (hasCiDir) ciPoints += 1;
  if (hasBuildSteps) ciPoints += 1;
  if (hasReleaseSteps) ciPoints += 1;
  const cicdScore = {
    name: 'CI/CD Pipelines',
    maxPoints: 3,
    points: Math.min(ciPoints, 3),
    details: { has_ci: hasCiDir, build_in_ci: hasBuildSteps, release_in_ci: hasReleaseSteps },
  };

  // Security Scanning (2)
  const hasScanning = containsAny(CODE_SCANNING_HINTS);
  const securityScore = {
    name: 'Security Scanning',
    maxPoints: 2,
    points: hasScanning ? 2 : 0,
    details: { scanning_in_ci: hasScanning },
  };

  // Dependency Updates (2)
  const hasDepUpdates = pathExists(['.github/dependabot.yml', '.github/dependabot.yaml', 'renovate.json', '.renovaterc.json'], treePaths);
  const depScore = {
    name: 'Dependency Updates',
    maxPoints: 2,
    points: hasDepUpdates ? 2 : 0,
    details: { dependabot_or_renovate: hasDepUpdates },
  };

  // Linting/Formatting (2)
  const hasLintConfig = pathExists(LINTER_CONFIG_NAMES, treePaths);
  const lintInCi = containsAny(LINT_HINTS);
  const lintPoints = (hasLintConfig && lintInCi) ? 2 : ((hasLintConfig || lintInCi) ? 1 : 0);
  const lintScore = {
    name: 'Linting/Formatting',
    maxPoints: 2,
    points: lintPoints,
    details: { lint_config: hasLintConfig, lint_in_ci: lintInCi },
  };

  // Release Management (2)
  const tags = await client.listTags(owner, repo);
  const releases = await client.listReleases(owner, repo);
  const hasChangelog = ['CHANGELOG.md', 'changelog.md', 'CHANGELOG', 'docs/CHANGELOG.md'].some((p) => pathExists([p], treePaths));
  let relPoints = 0;
  if (tags && tags.length > 0) relPoints += 1;
  if ((releases && releases.length > 0) || hasChangelog) relPoints += 1;
  const releaseScore = {
    name: 'Release Management',
    maxPoints: 2,
    points: Math.min(relPoints, 2),
    details: { tags: (tags || []).length, releases: (releases || []).length, has_changelog: hasChangelog },
  };

  // Build & Packaging Tools (2)
  const hasBuildPackaging = pathExists(BUILD_PACKAGING_FILES, treePaths);
  const buildScore = {
    name: 'Build & Packaging Tools',
    maxPoints: 2,
    points: hasBuildPackaging ? 2 : 0,
    details: { has_build_or_packaging_files: hasBuildPackaging },
  };

  // Infrastructure as Code (1)
  const hasIac = pathExists(IAC_FILES, treePaths) || treePaths.some((p) => p.startsWith('k8s/') || p.startsWith('deploy/') || p.startsWith('infra/'));
  const iacScore = {
    name: 'Infrastructure as Code',
    maxPoints: 1,
    points: hasIac ? 1 : 0,
    details: { has_iac: hasIac },
  };

  // Platform Integration (1)
  const hasPlatform = pathExists(CI_CONFIG_FILES, treePaths);
  const platformScore = {
    name: 'Platform Integration',
    maxPoints: 1,
    points: hasPlatform ? 1 : 0,
    details: { has_ci_config: hasPlatform },
  };

  return [
    testsScore,
    cicdScore,
    securityScore,
    depScore,
    lintScore,
    releaseScore,
    buildScore,
    iacScore,
    platformScore,
  ];
}

async function scoreHealth(client, owner, repo) {
  const repoData = await client.getRepo(owner, repo);
  const stars = (repoData && repoData.stargazers_count) || 0;
  const forks = (repoData && repoData.forks_count) || 0;
  const watchers = (repoData && (repoData.subscribers_count || repoData.watchers_count)) || 0;
  const openIssues = (repoData && repoData.open_issues_count) || 0;
  const archived = Boolean(repoData && repoData.archived);

  // Community Engagement (0-2)
  let cePoints = 0;
  if (stars >= 25 || forks >= 10 || openIssues >= 25) cePoints = 2;
  else if (stars >= 5 || forks >= 2 || openIssues >= 5) cePoints = 1;
  const communityScore = { name: 'Community Engagement', maxPoints: 2, points: cePoints, details: { stars, forks, open_issues: openIssues } };

  // Governance & Leadership (0-2)
  const tree = await client.listRepoTree(owner, repo);
  const treePaths = collectTreePaths(tree);
  const hasCodeowners = pathExists(['CODEOWNERS', '.github/CODEOWNERS'], treePaths);
  const hasGovernance = pathExists(['GOVERNANCE.md', 'MAINTAINERS', 'OWNERS'], treePaths);
  const glPoints = (hasCodeowners && hasGovernance) ? 2 : ((hasCodeowners || hasGovernance) ? 1 : 0);
  const governanceScore = { name: 'Governance & Leadership', maxPoints: 2, points: glPoints, details: { codeowners: hasCodeowners, governance_docs: hasGovernance } };

  // Succession Planning (0-2)
  const since = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000);
  const commits = await client.listCommitsSince(owner, repo, since);
  const authors = new Set();
  for (const c of commits || []) {
    const login = c && c.author && c.author.login;
    if (login) {
      authors.add(login);
    } else {
      const name = c && c.commit && c.commit.author && c.commit.author.name;
      if (name) authors.add(name);
    }
  }
  const numAuthors = authors.size;
  const spPoints = numAuthors >= 4 ? 2 : numAuthors >= 2 ? 1 : 0;
  const successionScore = { name: 'Succession Planning', maxPoints: 2, points: spPoints, details: { active_maintainers_90d: numAuthors } };

  // Ecosystem Importance (0-2)
  const eiPoints = (forks >= 20 || watchers >= 50) ? 2 : ((forks >= 5 || watchers >= 15) ? 1 : 0);
  const ecosystemScore = { name: 'Ecosystem Importance', maxPoints: 2, points: eiPoints, details: { forks, watchers } };

  // Activity Trend (0-2)
  const latest = await client.getLatestCommitDatetime(owner, repo);
  let daysSince = 9999;
  if (latest instanceof Date && !Number.isNaN(latest.getTime())) {
    daysSince = Math.floor((Date.now() - latest.getTime()) / (24 * 60 * 60 * 1000));
  }
  const atPoints = daysSince <= 30 ? 2 : daysSince <= 90 ? 1 : 0;
  const activityScore = { name: 'Activity Trend', maxPoints: 2, points: atPoints, details: { days_since_last_commit: daysSince } };

  // Sustainability & Risks (0-2)
  const hasSecurity = pathExists(['SECURITY.md', '.github/SECURITY.md'], treePaths);
  let srPoints = 0;
  if (archived) srPoints = 0;
  else srPoints = (hasSecurity ? 1 : 0) + (numAuthors >= 3 ? 1 : 0);
  const sustainabilityScore = { name: 'Sustainability & Risks', maxPoints: 2, points: Math.min(srPoints, 2), details: { security_policy: hasSecurity, archived } };

  return [
    communityScore,
    governanceScore,
    successionScore,
    ecosystemScore,
    activityScore,
    sustainabilityScore,
  ];
}

async function assessRepository(client, owner, repo) {
  const documentationScore = await scoreDocumentation(client, owner, repo);
  const infrastructureScore = await scoreInfrastructure(client, owner, repo);
  const healthScore = await scoreHealth(client, owner, repo);

  const totalInfrastructurePoints = infrastructureScore.reduce((s, x) => s + x.points, 0);
  const maxInfrastructurePoints = infrastructureScore.reduce((s, x) => s + x.maxPoints, 0);
  const totalHealthPoints = healthScore.reduce((s, x) => s + x.points, 0);
  const maxHealthPoints = healthScore.reduce((s, x) => s + x.maxPoints, 0);
  const totalPoints = documentationScore.points + totalInfrastructurePoints + totalHealthPoints;

  let maturityTier = 'Mature';
  if (totalPoints < 10) maturityTier = 'Incubation';
  else if (totalPoints < 24) maturityTier = 'Growth';

  let healthLabel = 'Unhealthy';
  if (totalHealthPoints >= 10) healthLabel = 'Healthy';
  else if (totalHealthPoints >= 6) healthLabel = 'Moderate';

  return {
    owner,
    repo,
    documentationScore,
    infrastructureScore,
    healthScore,
    totalInfrastructurePoints,
    maxInfrastructurePoints,
    totalHealthPoints,
    maxHealthPoints,
    totalPoints,
    maturityTier,
    healthLabel,
  };
}

module.exports = {
  assessRepository,
};
