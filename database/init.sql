-- ============================================================================
-- ABYSS — database bootstrap
-- ============================================================================
-- Scope of PHASE 1: extensions + schema metadata only.
-- The domain tables (cases, oil_spills, hindcast_results, vessels, ais_positions,
-- vessel_trajectories, behaviour_events, ais_gaps, candidate_scores,
-- evidence_events) are defined in PHASE 14, together with their spatial/temporal
-- indexes, once the Python pipeline output shapes are frozen by Phases 3–12.
--
-- Idempotent: safe to run repeatedly.
--   psql -U abyss -h localhost -d abyss -f database/init.sql
-- ============================================================================

-- PostGIS gives geometry columns, spatial indexes and distance operators used by
-- spatial compatibility filtering (candidate vessel positions vs origin region).
CREATE EXTENSION IF NOT EXISTS postgis;

-- Filesystem-independent UUID generation, used for case identifiers in Phase 14.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- Schema metadata
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS abyss_schema_info (
    component       TEXT        PRIMARY KEY,
    version         TEXT        NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO abyss_schema_info (component, version, description)
VALUES
    ('database', '1.0.0', 'ABYSS bootstrap schema: extensions + metadata (Phase 1)'),
    ('tables',   '0.0.0', 'Domain tables are introduced in Phase 14')
ON CONFLICT (component) DO UPDATE
    SET version = EXCLUDED.version,
        description = EXCLUDED.description,
        updated_at = now();

-- ---------------------------------------------------------------------------
-- Time and timezone discipline
-- ---------------------------------------------------------------------------
-- All application timestamps are stored as TIMESTAMPTZ. Browsing sessions default
-- to UTC; the JDBC/Hibernate connection also pins UTC in Phase 13
-- (spring.jpa.properties.hibernate.jdbc.time_zone=UTC), which is what actually
-- guarantees consistency. A database-wide ALTER DATABASE ... SET timezone is
-- deliberately NOT executed here because it requires a literal database name and
-- the bootstrap script must stay name-agnostic (it is also mounted as a Docker
-- entrypoint script, where a hard-coded name would be wrong).
SET timezone TO 'UTC';
