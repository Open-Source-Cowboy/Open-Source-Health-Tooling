#!/usr/bin/env bash
set -euo pipefail

# OSS Health setup and run helper
# - Checks/installs prerequisites (Node 18+, npm, git, curl)
# - Optionally sets up Python virtualenv for PDF export
# - Installs npm dependencies
# - Runs the Node CLI (or Python CLI if --pdf is requested)

SCRIPT_NAME=$(basename "$0")

# Defaults from environment if present
TOKEN="${GITHUB_TOKEN:-}"
GHE_URL="${GITHUB_URL:-}"
FORMAT="table"
DETAILS=0
ORG=""
LIMIT=""
PDF_PATH=""
PDF_TITLE="OSS Health Report"
RUN_METRICS=0
METRICS_OWNER=""
METRICS_REPO=""
ONLY_CHECK=0
SKIP_INSTALL=0
# REPOS is an array of owner/repo specs
REPOS=()

is_root() { [ "$(id -u)" -eq 0 ]; }

has_cmd() { command -v "$1" >/dev/null 2>&1; }

# Determine sudo capability
SUDO=""
if ! is_root && has_cmd sudo; then
  SUDO="sudo"
fi

log()  { printf "\033[1;32m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*" 1>&2; }

usage() {
  cat <<'EOF'
Usage:
  ./oss-health-setup.sh [options] (--repos owner/repo ... | --org ORG [--limit N])

Options:
  --token TOKEN             GitHub token (or export GITHUB_TOKEN)
  --ghe-url URL             GitHub Enterprise API base, e.g. https://ghe.example.com/api
  --repos owner/repo ...    One or more repositories to assess
  --org ORG                 Organization to scan (public repos)
  --limit N                 Limit number of repos for --org
  --format table|json       Output format (default: table)
  --details                 Include detailed breakdowns (JSON only)
  --pdf PATH                Use Python CLI to write PDF report to PATH
  --title TEXT              Title for the PDF (default: OSS Health Report)
  --metrics OWNER REPO      Also run @figify/gh-metrics for OWNER/REPO
  --only-check              Only check/print dependency versions; do not install or run
  --skip-install            Skip attempting to install missing prerequisites
  -h, --help                Show this help and exit

Examples:
  # Assess specific repos (table):
  ./oss-health-setup.sh --repos openai/gym vercel/next.js

  # JSON with details:
  ./oss-health-setup.sh --repos nodejs/node --format json --details

  # Org scan first 10 repos:
  ./oss-health-setup.sh --org kubernetes --limit 10

  # Generate PDF (Python CLI):
  ./oss-health-setup.sh --repos numpy/numpy pytorch/pytorch --pdf report.pdf --title "Data Science OSS"

  # GitHub Enterprise usage:
  ./oss-health-setup.sh --repos owner/repo --ghe-url https://ghe.example.com/api
EOF
}

# Detect system package manager
_detect_pkg_manager() {
  if has_cmd apt-get; then echo apt; return; fi
  if has_cmd dnf; then echo dnf; return; fi
  if has_cmd yum; then echo yum; return; fi
  if has_cmd pacman; then echo pacman; return; fi
  if has_cmd zypper; then echo zypper; return; fi
  if has_cmd apk; then echo apk; return; fi
  echo none
}

_install_pkgs() {
  # $@: packages
  local pm; pm=$(_detect_pkg_manager)
  if [ "$pm" = "none" ]; then
    warn "No supported package manager detected; cannot auto-install: $*"
    return 1
  fi
  if [ -z "$SUDO" ] && ! is_root; then
    warn "No sudo/root; cannot auto-install: $*"
    return 1
  fi
  case "$pm" in
    apt)
      $SUDO apt-get update -y || true
      $SUDO apt-get install -y "$@"
      ;;
    dnf)
      $SUDO dnf install -y "$@"
      ;;
    yum)
      $SUDO yum install -y "$@"
      ;;
    pacman)
      $SUDO pacman -Sy --noconfirm "$@"
      ;;
    zypper)
      $SUDO zypper install -y "$@"
      ;;
    apk)
      $SUDO apk add --no-cache "$@"
      ;;
  esac
}

_node_major() {
  local v
  v=$(node -v 2>/dev/null || true)
  if [ -z "$v" ]; then echo 0; return; fi
  echo "$v" | sed -E 's/^v([0-9]+).*/\1/'
}

_use_nvm() {
  export NVM_DIR="$HOME/.nvm"
  if [ -s "$NVM_DIR/nvm.sh" ]; then
    # shellcheck source=/dev/null
    . "$NVM_DIR/nvm.sh"
    return 0
  fi
  return 1
}

_install_nvm_and_node() {
  log "Installing Node via nvm (user-local)"
  export NVM_DIR="$HOME/.nvm"
  mkdir -p "$NVM_DIR"
  if ! has_cmd curl; then
    if [ "$SKIP_INSTALL" -eq 1 ]; then
      err "curl not found and --skip-install set; cannot install nvm"; return 1
    fi
    _install_pkgs curl || true
  fi
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
  if ! _use_nvm; then
    err "Failed to initialize nvm"; return 1
  fi
  nvm install --lts
  nvm alias default 'lts/*' || true
  nvm use --lts
}

_install_node_via_pkgmgr() {
  local pm; pm=$(_detect_pkg_manager)
  if [ "$pm" = apt ]; then
    if [ -z "$SUDO" ] && ! is_root; then return 1; fi
    log "Attempting Node 18.x via NodeSource (apt)"
    curl -fsSL https://deb.nodesource.com/setup_18.x | $SUDO -E bash -
    $SUDO apt-get install -y nodejs
    return $?
  fi
  if [ "$pm" = dnf ] || [ "$pm" = yum ]; then
    if [ -z "$SUDO" ] && ! is_root; then return 1; fi
    log "Attempting Node 18.x via NodeSource (dnf/yum)"
    curl -fsSL https://rpm.nodesource.com/setup_18.x | $SUDO -E bash -
    $SUDO ${pm} install -y nodejs
    return $?
  fi
  return 1
}

ensure_git() {
  if has_cmd git; then return 0; fi
  if [ "$SKIP_INSTALL" -eq 1 ]; then
    err "git not found (use your package manager to install)"; return 1
  fi
  log "Installing git"
  _install_pkgs git || { err "Failed to install git"; return 1; }
}

ensure_curl() {
  if has_cmd curl; then return 0; fi
  if [ "$SKIP_INSTALL" -eq 1 ]; then
    err "curl not found (use your package manager to install)"; return 1
  fi
  log "Installing curl"
  _install_pkgs curl || { err "Failed to install curl"; return 1; }
}

ensure_node() {
  local major; major=$(_node_major)
  if [ "$major" -ge 18 ]; then
    return 0
  fi
  if [ "$SKIP_INSTALL" -eq 1 ]; then
    err "Node 18+ required; found ${major}. Install Node >= 18 and re-run."; return 1
  fi
  # Try nvm first (user-local, no root)
  if ! _use_nvm; then
    _install_nvm_and_node || true
  else
    log "Using existing nvm"
    nvm install --lts
    nvm alias default 'lts/*' || true
    nvm use --lts
  fi
  major=$(_node_major)
  if [ "$major" -ge 18 ]; then return 0; fi
  # Fallback to package manager via NodeSource (needs sudo/root)
  _install_node_via_pkgmgr || true
  major=$(_node_major)
  if [ "$major" -ge 18 ]; then return 0; fi
  err "Unable to install Node 18+. Please install manually and re-run."
  return 1
}

ensure_python_for_pdf() {
  if [ -z "$PDF_PATH" ]; then return 0; fi
  # Python is only required if generating PDF
  if ! has_cmd python3; then
    if [ "$SKIP_INSTALL" -eq 1 ]; then
      err "python3 not found and --skip-install set; cannot generate PDF"; return 1
    fi
    log "Installing python3"
    _install_pkgs python3 || warn "Failed to auto-install python3; proceeding may fail"
  fi
  # Try to create venv
  if ! python3 -m venv .venv 2>/dev/null; then
    warn "python venv module missing; attempting to install venv support"
    _install_pkgs python3-venv || true
    if ! python3 -m venv .venv 2>/dev/null; then
      warn "Falling back to virtualenv"
      if ! has_cmd pip3; then _install_pkgs python3-pip || true; fi
      python3 -m pip install --user virtualenv || true
      python3 -m virtualenv .venv || { err "Failed to create virtual environment"; return 1; }
    fi
  fi
  # shellcheck source=/dev/null
  . ./.venv/bin/activate
  pip install --upgrade pip >/dev/null 2>&1 || true
  pip install --quiet fpdf2 requests || { err "Failed to install Python deps (fpdf2, requests)"; return 1; }
}

print_versions() {
  echo "Dependency versions:"
  if has_cmd node; then echo "- node: $(node -v)"; else echo "- node: not found"; fi
  if has_cmd npm; then echo "- npm: $(npm -v)"; else echo "- npm: not found"; fi
  if has_cmd git; then echo "- git: $(git --version | awk '{print $3}')"; else echo "- git: not found"; fi
  if has_cmd curl; then echo "- curl: $(curl --version | head -n1 | awk '{print $2}')"; else echo "- curl: not found"; fi
  if has_cmd python3; then echo "- python3: $(python3 --version | awk '{print $2}')"; else echo "- python3: not found"; fi
  if has_cmd pip3; then echo "- pip3: $(pip3 --version | awk '{print $2}')"; else echo "- pip3: not found"; fi
}

# Parse args
if [ $# -eq 0 ]; then usage; exit 2; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --token)        TOKEN="${2:-}"; shift ;;
    --ghe-url)      GHE_URL="${2:-}"; shift ;;
    --repos)
      shift
      while [ $# -gt 0 ] && [[ ! "$1" =~ ^-- ]]; do
        REPOS+=("$1")
        shift
      done
      continue ;;
    --org)          ORG="${2:-}"; shift ;;
    --limit)        LIMIT="${2:-}"; shift ;;
    --format)       FORMAT="${2:-}"; shift ;;
    --details)      DETAILS=1 ;;
    --pdf)          PDF_PATH="${2:-}"; shift ;;
    --title)        PDF_TITLE="${2:-}"; shift ;;
    --metrics)      RUN_METRICS=1; METRICS_OWNER="${2:-}"; METRICS_REPO="${3:-}"; shift 2 ;;
    --only-check)   ONLY_CHECK=1 ;;
    --skip-install) SKIP_INSTALL=1 ;;
    -h|--help)      usage; exit 0 ;;
    *) err "Unknown argument: $1"; usage; exit 2 ;;
  esac
  shift
done

# Validate inputs
if [ ${#REPOS[@]} -eq 0 ] && [ -z "$ORG" ]; then
  err "Either --repos or --org must be provided"; usage; exit 2
fi
if [ -n "$PDF_PATH" ] && [ "$FORMAT" = "json" ] && [ "$DETAILS" -eq 1 ]; then
  : # ok; Python CLI will honor details in PDF sections
fi
if [ "$RUN_METRICS" -eq 1 ]; then
  if [ -z "$METRICS_OWNER" ] || [ -z "$METRICS_REPO" ]; then
    err "--metrics requires OWNER and REPO"; exit 2
  fi
fi

log "Checking dependencies"
print_versions

if [ "$ONLY_CHECK" -eq 1 ]; then
  log "Only dependency check requested; exiting."
  exit 0
fi

# Ensure prerequisites
ensure_git
ensure_curl
ensure_node

# Install Node deps
log "Installing npm dependencies"
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi

# Export env for GitHub API
if [ -n "$TOKEN" ]; then export GITHUB_TOKEN="$TOKEN"; fi
if [ -n "$GHE_URL" ]; then export GITHUB_URL="$GHE_URL"; fi

# Build common arg list
OSS_ARGS=()
if [ ${#REPOS[@]} -gt 0 ]; then
  OSS_ARGS+=("--repos" "${REPOS[@]}")
else
  OSS_ARGS+=("--org" "$ORG")
  if [ -n "$LIMIT" ]; then OSS_ARGS+=("--limit" "$LIMIT"); fi
fi
if [ -n "$FORMAT" ]; then OSS_ARGS+=("--format" "$FORMAT"); fi
if [ "$DETAILS" -eq 1 ]; then OSS_ARGS+=("--details"); fi

# Run PDF via Python CLI if requested; otherwise run Node CLI
if [ -n "$PDF_PATH" ]; then
  log "Preparing Python environment for PDF export"
  ensure_python_for_pdf
  log "Running Python CLI to generate PDF: $PDF_PATH"
  # shellcheck disable=SC2086
  python3 -m oss_health ${OSS_ARGS[@]} --pdf "$PDF_PATH" --title "$PDF_TITLE"
  log "PDF saved to $PDF_PATH"
else
  log "Running Node CLI (oss-health)"
  # npm passes args after -- to script
  # shellcheck disable=SC2086
  npm run oss-health -- ${OSS_ARGS[@]}
fi

# Optionally run metrics
if [ "$RUN_METRICS" -eq 1 ]; then
  log "Running @figify/gh-metrics for $METRICS_OWNER/$METRICS_REPO"
  npm run gh-metrics -- --a "$METRICS_OWNER" --r "$METRICS_REPO"
fi

log "Done."
