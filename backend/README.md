# backend/ — ABYSS Spring Boot API

Java 21 · Spring Boot · Spring Web · Spring Data JPA · PostgreSQL/PostGIS. **Phase 13** builds the
project; **Phase 1** only fixes the layout and package structure.

```
backend/
├── pom.xml                                   (Phase 13)
└── src/
    ├── main/
    │   ├── java/com/abyss/
    │   │   ├── AbyssApplication.java          (Phase 13)
    │   │   ├── controller/                    REST endpoints (the public contract)
    │   │   ├── service/                       case orchestration + intelligence client
    │   │   ├── repository/                    Spring Data JPA repositories
    │   │   ├── entity/                        JPA entities / PostGIS geometry mapping
    │   │   ├── dto/                           request/response models
    │   │   ├── config/                        CORS, Jackson, WebClient/RestClient, startup validation
    │   │   └── exception/                     typed exceptions + @RestControllerAdvice
    │   └── resources/                         application.yml (+ application-demo.yml)
    └── test/java/com/abyss/                   Phase 19 tests
```

## Public API (specification contract — implemented in Phase 13)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/cases` | create a case (for example `CASE-001`) |
| GET | `/api/cases/{caseId}` | case state and current workflow step |
| POST | `/api/cases/{caseId}/satellite` | load satellite observation, detect/confirm slick |
| POST | `/api/cases/{caseId}/hindcast` | run backward drift, store origin + release window |
| POST | `/api/cases/{caseId}/ais/analyze` | clean AIS, build trajectories, filter, behave, gaps, score |
| GET | `/api/cases/{caseId}/vessels` | vessels in scope (with filters) |
| GET | `/api/cases/{caseId}/candidates` | ranked candidates with factor breakdown + reasons |
| GET | `/api/cases/{caseId}/vessels/{vesselId}` | vessel detail: track, events, evidence, confidence |
| GET | `/api/cases/{caseId}/timeline` | forensic timeline |
| GET | `/api/cases/{caseId}/evidence` | evidence chain/graph |
| GET | `/api/cases/{caseId}/report` | investigation report |

The backend is the **only** service exposed to the browser; it forwards analysis calls to the Python
intelligence service at `ABYSS_INTELLIGENCE_BASE_URL`.

## Rules for this module

* Credentials come from the environment only (`POSTGRES_*`) and are validated at startup.
* An unreachable intelligence service returns `502` with a meaningful message — never a stack trace
  and never a hang.
* Timestamps are stored and returned in UTC (`TIMESTAMPTZ` + `hibernate.jdbc.time_zone=UTC`).
* Entity/DTO separation: no JPA entity is returned directly from a controller.
* Every persisted conclusion keeps its provenance (observed vs model-derived vs inferred).

## Commands (once Phase 13 adds `pom.xml`)

```bash
mvn -q clean package        # compile + test + jar
mvn spring-boot:run         # http://localhost:8080
curl http://localhost:8080/api/health
```