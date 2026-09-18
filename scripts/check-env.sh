#!/usr/bin/env bash
# ============================================================================
# ABYSS — environment verification script
# Prints the tool status table for the ABYSS stack. Read-only: installs nothing.
#
#   bash scripts/check-env.sh
# ============================================================================
set -uo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; BOLD='\033[1m'; NC='\033[0m'

pass=0; fail=0; warn=0
ok()   { printf "  ${GREEN}[ OK ]${NC}    %-12s %s\n" "$1" "$2"; pass=$((pass+1)); }
bad()  { printf "  ${RED}[MISSING]${NC} %-12s %s\n" "$1" "$2"; fail=$((fail+1)); }
note() { printf "  ${YELLOW}[ NOTE ]${NC} %-12s %s\n" "$1" "$2"; warn=$((warn+1)); }

first_line() { "$@" 2>&1 | head -n1; }

echo ""
printf "${BOLD}ABYSS environment check${NC}   $(date '+%Y-%m-%d %H:%M:%S')\n"
printf -- "------------------------------------------------------------------------\n"
printf "  host: %s / %s\n" "$(uname -s)" "$(uname -m)"
printf -- "------------------------------------------------------------------------\n"

# --- Java ------------------------------------------------------------------
if command -v java >/dev/null 2>&1; then
  java_version="$(java -version 2>&1 | head -n1)"
  major="$(printf '%s' "$java_version" | sed -n 's/.*version "\([0-9][0-9]*\).*/\1/p')"
  if [ -n "$major" ] && [ "$major" -ge 21 ]; then ok "java" "$java_version"; else note "java" "$java_version (ABYSS targets 21+)"; fi
else bad "java" "not found — install OpenJDK 21"; fi

# --- Maven -----------------------------------------------------------------
if command -v mvn >/dev/null 2>&1; then ok "mvn" "$(mvn -v 2>/dev/null | head -n1)"; else bad "mvn" "not found — needed for backend/"; fi

# --- Python ----------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
  py="$(python3 --version 2>&1)"
  minor="$(python3 -c 'import sys;print("%d%d" % sys.version_info[:2])' 2>/dev/null)"
  if [ -n "$minor" ] && [ "$minor" -ge 311 ]; then ok "python3" "$py"; else note "python3" "$py (ABYSS targets 3.11+)"; fi
else bad "python3" "not found — install Python 3.11+"; fi

if command -v pip3 >/dev/null 2>&1; then ok "pip3" "$(pip3 --version 2>&1 | cut -d' ' -f1-2)"
elif python3 -m pip --version >/dev/null 2>&1; then ok "pip (module)" "$(python3 -m pip --version 2>&1 | cut -d' ' -f1-2)"
else bad "pip" "absent — bootstrap: curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && python3 /tmp/get-pip.py --user"; fi

if python3 -c 'import ensurepip' >/dev/null 2>&1; then ok "venv/ensurepip" "available"
else note "venv" "ensurepip absent (python3-venv pkg not installed) — virtualenv or get-pip workaround required"; fi

# --- Node / npm ------------------------------------------------------------
if command -v node >/dev/null 2>&1; then
  nv="$(node --version 2>&1)"; major="${nv#v}"; major="${major%%.*}"
  if [ "$major" -ge 18 ]; then ok "node" "$nv"; else note "node" "$nv (Vite needs 18+)"; fi
else bad "node" "not found — needed for frontend/ (see README setup)"; fi

if command -v npm >/dev/null 2>&1; then ok "npm" "$(npm --version 2>&1)"; else bad "npm" "not found — ships with Node.js"; fi

# --- PostgreSQL / PostGIS --------------------------------------------------
if command -v psql >/dev/null 2>&1; then ok "psql" "$(psql --version 2>&1)"; else bad "psql" "not found — needed for database/ (Phase 14)"; fi
if command -v pg_isready >/dev/null 2>&1; then
  if pg_isready -q -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" >/dev/null 2>&1; then
    ok "postgres" "server reachable at ${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}"
  else note "postgres" "server not reachable at ${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}"; fi
else note "postgres" "pg_isready not found — cannot verify server"; fi

# --- Docker (optional) -----------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then ok "docker compose" "$(docker compose version 2>&1 | head -n1)"
  elif command -v docker-compose >/dev/null 2>&1; then ok "docker-compose" "$(docker-compose --version 2>&1)"
  else note "docker compose" "docker present, compose plugin missing"; fi
else note "docker" "not installed (OPTIONAL — docker-compose.yml is a convenience only)"; fi

# --- Git -------------------------------------------------------------------
if command -v git >/dev/null 2>&1; then
  ok "git" "$(git --version 2>&1)"
  gn="$(git config --global user.name 2>/dev/null)"; ge="$(git config --global user.email 2>/dev/null)"
  if [ -n "$gn" ] && [ -n "$ge" ]; then note "git identity" "$gn <$ge>"; else note "git identity" "unset — commits will fail until configured"; fi
else bad "git" "not found"; fi

printf -- "------------------------------------------------------------------------\n"
printf "  result: ${GREEN}%d ok${NC}, ${RED}%d missing${NC}, ${YELLOW}%d note${NC}\n" "$pass" "$fail" "$warn"
printf -- "------------------------------------------------------------------------\n"
echo "  DEMO MODE needs only: Java 21 + Maven + Python 3.11+ (pip optional for demo data)"
echo "  FULL STACK additionally needs: Node 18+/npm (frontend) and PostgreSQL 16 + PostGIS (database)"
echo ""
exit 0
