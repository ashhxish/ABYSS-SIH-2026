# ABYSS — API keys and credentials

Status: **Phase 1**. Credentials are read **only** from environment variables, `.env` is git-ignored,
and `.env.example` contains placeholders. **No registration URL or token format is invented here.**

## 1. Services used by ABYSS

| SERVICE | PURPOSE | API KEY REQUIRED? | HOW TO REGISTER | ENVIRONMENT VARIABLE | FALLBACK |
|---|---|---|---|---|---|
| PostgreSQL + PostGIS (local) | Case/vessel/evidence persistence | **No** — ABYSS-owned local account, not a third-party key | Not applicable; created locally (`CREATE ROLE`) | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Demo mode needs no database. Backend startup validation reports a clear error if the DB is required but unreachable. |
| Python intelligence service (local) | Analysis pipeline | **No** — internal service on localhost | Not applicable | `ABYSS_INTELLIGENCE_BASE_URL`, `INTELLIGENCE_PORT` | If unreachable, the backend returns `502` with a meaningful message instead of failing silently. |
| Maven Central | Java dependency resolution | No | Not applicable | none | Build fails with Maven's own error; dependencies can be pre-cached in `~/.m2`. |
| npm registry | Frontend dependency resolution | No | Not applicable | none | Install fails with npm's own error; `node_modules` can be pre-installed. |
| Copernicus Marine Service (CMEMS) | Ocean surface current U/V for hindcasting | **Yes** (live mode only) | Register through the official Copernicus Marine Data Store portal. **Registration and authentication method need verification from the official provider documentation.** | `COPERNICUS_USERNAME`, `COPERNICUS_PASSWORD` (names are provisional placeholders) | Demo environmental field + `warnings[]` entry: `Environmental data unavailable — using demonstration dataset.` |
| Copernicus Climate Data Store (ERA5 / CDS) | Historical wind fields (10 m wind U/V) | **Yes** (live mode only) | Register through the official Copernicus CDS portal. **Authentication method needs verification from the official provider documentation** (personal access tokens have replaced earlier API-key flows; do not assume). | `CDS_API_URL`, `CDS_API_KEY` (provisional placeholders) | Demo environmental field + visible warning |
| Copernicus Data Space / Sentinel-1 | SAR imagery for detection | **Likely yes** for programmatic access | Register through the official Copernicus Data Space portal. **Authentication method needs verification from the official provider documentation** (OAuth2 vs legacy credentials). | `COPERNICUS_USERNAME`, `COPERNICUS_PASSWORD` (shared placeholder; split if the provider requires it) | Bundled demo scene + pre-computed slick polygon |
| Licensed historical AIS provider | Real AIS positions | **Yes** — historical AIS is typically commercial | Choose and license a provider; **do not implement endpoints or scrapers before verifying terms of use and authentication.** | **No variable defined yet** — none is created until a provider is actually selected (no fake variables) | Synthetic demo AIS CSV, labelled `AIS: Synthetic Demonstration Dataset` |
| OpenStreetMap / Natural Earth (optional) | Basemap and land context in the map | No (attribution required) | Not applicable | none | Demo-safe: no basemap key needed for the tiled basemaps used by default |

## 2. Policy

1. **Never hard-code** credentials, tokens or passwords — in source, tests, sample requests or docs.
2. **Never commit `.env`** (git-ignored). Commit only `.env.example`.
3. Configuration is **validated at startup**: unconfigured providers select their demo implementation
   and log an INFO/WARNING line; a *required* value that is missing produces a clear error naming the
   variable.
4. **An external service failure must never crash ABYSS.** The request degrades to demo data, and the
   response carries a warning the UI displays.
5. Where the authentication method is unknown, this repository says so explicitly instead of
   guessing: *"Authentication method needs verification from the official provider documentation."*
6. Demo mode must remain fully functional with `.env.example` copied to `.env` **and nothing filled
   in**.

## 3. Local setup

```bash
cd ABYSS
cp .env.example .env       # demo defaults; leave all credentials blank
bash scripts/check-env.sh  # confirms which tools/services are available
```

The `POSTGRES_*` values are local development credentials for a database ABYSS creates itself. They
are placeholders (`change_me_local_dev_only`) and must be replaced before any shared deployment.
ABYSS does not currently target any deployment environment, so no separate production secret
management is documented.
