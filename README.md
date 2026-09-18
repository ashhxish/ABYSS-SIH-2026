# ABYSS — AI-Powered Maritime Forensic Intelligence System

> **SIH 2026 — Problem Statement 26143**
> Oil-spill attribution support from satellite observation + ocean/wind hindcasting + historical AIS.

ABYSS turns an observed oil slick into an **explainable forensic investigation**. It reconstructs a
**probable origin region** and a **release time window** from the observed slick and environmental
conditions, then filters historical AIS traffic to produce a **ranked, explainable list of candidate
vessels** whose movement is *compatible* with that reconstruction.

```
Satellite observation → oil-spill detection → slick segmentation → environmental data
→ backward drift / hindcasting → probable origin region + release time window
→ historical AIS filtering → trajectory compatibility → behaviour analysis
→ AIS gap analysis → explainable evidence scoring → candidate vessel ranking
→ forensic timeline → interactive geospatial dashboard → investigation report
```

**ABYSS is an investigation support system. It does not prove which vessel caused a spill.**
Candidate ranking does not establish legal responsibility. Synthetic demonstration data is always
labelled as synthetic.

---

## 1. Architecture

```
                    React + Vite + React-Leaflet + Recharts
                                   |
                                   | REST /api/**
                                   v
                     Spring Boot (Java 21) — case lifecycle,
                     persistence, API contract, report assembly
                                   |
                                   | REST (internal)
                                   v
                   Python 3.11+ FastAPI — detection, hindcast,
                   AIS cleaning, trajectories, behaviour, gaps, scoring
                                   |
                                   v
                      PostgreSQL 16 + PostGIS (geometry, AIS positions)
```

No Kubernetes, Kafka, Redis, message queues or cloud services: the prototype is intentionally a
three-process local stack (frontend, backend, intelligence) plus one database.

| Component | Path | Runtime | Default port |
|---|---|---|---|
| Dashboard | `frontend/` | Node 18+ / Vite / React | 5173 |
| Backend API | `backend/` | Java 21 / Spring Boot / Maven | 8080 |
| Intelligence service | `intelligence/` | Python 3.11+ / FastAPI | 8000 |
| Database | `database/` | PostgreSQL + PostGIS | 5432 |

## 2. Two data modes

| Mode | `ABYSS_DATA_MODE` | Credentials | Dataset | UI label |
|---|---|---|---|---|
| **Demo** (default, hackathon-reliable) | `demo` | **none** | bundled deterministic dataset in `intelligence/data/demo/case_001/` (see its `README.md`) | **DEMO DATA** |
| **Live** | `live` | optional, from `.env` | external scientific providers | provider name + fallback notices |

Rules enforced in code and documentation:

* Demo mode must run **with no API keys at all**.
* If a live provider is unconfigured, unreachable, or errors, the service **logs the failure and
  falls back to demo data** with a visible warning — an external API must never crash the system.
* Synthetic AIS is **never** presented as real-world evidence; every screen that shows it carries the
  label `AIS: Synthetic Demonstration Dataset`.

## 3. Repository layout

```
ABYSS/
├── frontend/      React + Vite dashboard (map-centric)
├── backend/       Spring Boot API, JPA entities, case lifecycle
├── intelligence/  Python FastAPI scientific/AI service + datasets + tests
├── database/      init.sql (extensions, schema bootstrap)
├── docs/          architecture, data sources, api keys, methodology, demo scenario
├── scripts/       check-env.sh (read-only environment verification)
├── .env.example   configuration template (safe to commit)
├── docker-compose.yml  OPTIONAL PostGIS convenience
└── README.md
```

## 4. Prerequisites

| Tool | Version | Required for | Status on the reference machine |
|---|---|---|---|
| JDK | 21+ | backend | ✅ 21.0.12 |
| Maven | 3.8+ | backend | ✅ 3.8.7 |
| Python | 3.11+ | intelligence | ✅ 3.12.3 |
| pip / venv | — | intelligence dependencies | ⚠️ not yet bootstrapped |
| Node + npm | 18+ | frontend | ❌ not installed |
| PostgreSQL + PostGIS | 16 / 3.4 | database persistence | ❌ not installed |
| Docker | any | *optional* database convenience | ❌ not installed |

Read-only verification at any time:

```bash
cd ABYSS
bash scripts/check-env.sh
```

### Installing the missing pieces (the reference machine has no passwordless sudo)

**pip — needed by `intelligence/`**

```bash
curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
python3 /tmp/get-pip.py --user
python3 -m pip --version
```

The system Python here ships **without `ensurepip`**, so `python3 -m venv` fails. Use `virtualenv`
or a `--user` install instead:

```bash
python3 -m pip install --user virtualenv
python3 -m virtualenv .venv
source .venv/bin/activate
python3 -m pip install -r intelligence/requirements.txt   # added in Phase 2
```

**Node.js + npm** — download the Linux x64 LTS tarball from the official download page
(<https://nodejs.org/en/download>), then extract it into your home directory:

```bash
mkdir -p "$HOME/.local/node"
tar -xJf ~/Downloads/node-v*-linux-x64.tar.xz -C "$HOME/.local/node" --strip-components=1
export PATH="$HOME/.local/node/bin:$PATH"      # add to ~/.bashrc to persist
node --version && npm --version
```

**PostgreSQL + PostGIS** — with `sudo`:

```bash
sudo apt-get install -y postgresql postgresql-postgis
sudo -u postgres psql -c "CREATE ROLE abyss LOGIN PASSWORD 'change_me_local_dev_only';"
sudo -u postgres psql -c "CREATE DATABASE abyss OWNER abyss;"
psql -U abyss -h localhost -d abyss -f database/init.sql
```

Without `sudo` (and without Docker) the database is deferred to **Phase 14**, where the installation
route is validated *before* the schema is written. The official PostgreSQL binary distribution
requires accepting the provider's licence through their download flow — **verification needed**, and
it is not assumed here. **Demo mode does not require PostgreSQL**: the intelligence service runs
standalone, so Phases 2–13 are unaffected.

## 5. Running the stack (target state of Phase 20)

```bash
bash scripts/check-env.sh                                   # 1. verify toolchain
cp .env.example .env                                        # 2. demo mode, no keys needed
cd intelligence && uvicorn app.main:app --port 8000         # 3. intelligence service
cd backend && mvn spring-boot:run                           # 4. backend API   (Phase 13)
cd frontend && npm install && npm run dev                   # 5. dashboard     (Phase 15)
```

Health checks once those phases land:

| Check | Command / URL |
|---|---|
| Intelligence service | `curl http://localhost:8000/health` |
| Backend API | `curl http://localhost:8080/api/health` |
| Database + PostGIS | `psql -U abyss -h localhost -d abyss -c "SELECT postgis_full_version();"` |
| Dashboard | <http://localhost:5173> |

### Verify Phase 2 (the demo dataset) — works right now, no services needed

```bash
# regenerate the deterministic CASE-001 dataset in place
python3 intelligence/data/demo/generate_case_001.py

# run the Phase 2 validation suite (identity, fields, data quality, scenario design, determinism)
python3 -m unittest discover -s intelligence/tests -v
```

Expected: the generator prints a per-vessel table and `40 self-checks passed`; the suite reports
`Ran 35 tests ... OK`. The dataset itself is described in
`intelligence/data/demo/case_001/README.md`.

## 6. Build status (phase plan from the specification)

| Phase | Scope | Status |
|---|---|---|
| 1 | Repository + project structure | ✅ complete |
| 2 | Demo dataset (deterministic) | ✅ complete |
| 3–10 | AIS cleaning → trajectories → spatial/temporal/trajectory filtering → behaviour → gaps → scoring | ⏳ next |
| 11–12 | Hindcast engine, satellite / oil-spill module | ⏳ |
| 13–14 | Spring Boot API, PostgreSQL/PostGIS schema | ⏳ |
| 15–18 | React dashboard, forensic timeline, evidence graph, report generation | ⏳ |
| 19–20 | Automated tests, demo mode + fallback hardening | ⏳ |

The specification's forensic test cases (A: correct location+time, B: wrong time, C: wrong location,
D: gap with impossible travel, E: physically compatible gap, F: isolated speed anomaly,
G: nearest vessel is not automatically the top candidate) are implemented in Phase 19 against the
deterministic demo dataset.

## 7. Terminology and scientific honesty

Approved: *candidate vessel, evidence compatibility, candidate ranking, probable origin, uncertainty
region, investigation confidence, behavioural anomaly.*
Avoided: *guilty vessel, confirmed culprit, proven criminal, guaranteed source.*

* ABYSS identifies **candidate vessels whose historical movement is compatible** with the
  reconstructed spill origin and release window.
* The hindcast produces a **probable origin region with uncertainty**, never a single exact point.
* An AIS gap is **flagged for investigation** when it is physically compatible with the vessel's
  movement and overlaps the reconstructed event window — a gap alone never increases suspicion.
* Prototype scoring weights are **configurable prototypes, not scientifically validated constants.**
* Observed data, model-derived estimates, inferred compatibility and uncertainty are labelled
  separately in the UI and in generated reports.

## 8. Documentation

| Document | Contents |
|---|---|
| `docs/architecture.md` | components, data flow, module responsibilities, configuration, fallback policy |
| `docs/data-sources.md` | satellite / environmental / AIS sources and the provider abstraction |
| `docs/api-keys.md` | which services need credentials, registration, environment variable, fallback |
| `docs/methodology.md` | methods, assumptions, uncertainty handling, limitations |
| `docs/demo-scenario.md` | the deterministic CASE-001 demonstration design |

## 9. Configuration and security

* All configuration is read from environment variables; credentials are **never** hard-coded.
* `.env` is git-ignored; `.env.example` contains placeholders only.
* Configuration is validated at service startup, and any provider left unconfigured simply selects
  its demo implementation instead of failing.
* Every provider error, invalid AIS row, missing environmental value, model failure and fallback
  activation is logged.

## 10. Disclaimer

ABYSS provides analytical evidence for investigation support. Candidate ranking does not establish
legal responsibility, and the system does not determine which vessel caused an oil spill.
