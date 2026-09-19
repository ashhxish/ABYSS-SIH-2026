"""ABYSS - intelligence service configuration.

POLICY (see docs/api-keys.md)
    * every value comes from an environment variable, with a documented default;
    * no credential is ever hard-coded or read from a file inside the repository;
    * invalid configuration fails LOUDLY at startup instead of silently selecting a
      wrong data source, because a silently wrong data source is worse than a crash;
    * a provider that is simply unconfigured is not an error - it selects its demo
      implementation and the response records a fallback warning.

USAGE
    from app.config import get_settings
    settings = get_settings()
    settings.ais_cleaning_config()      # thresholds for the Phase 3 cleaning module
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = INTELLIGENCE_DIR.parent

DATA_MODES = ("demo", "live")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_DEMO_CASE_ID = "CASE-001"
_CASE_ID_PATTERN = re.compile(r"^CASE-\d{3}$")

__all__ = ["Settings", "ConfigurationError", "get_settings", "DATA_MODES", "INTELLIGENCE_DIR", "REPO_ROOT"]


class ConfigurationError(RuntimeError):
    """Raised when configuration is present but invalid."""


def _read_str(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def _read_float(
    env: Mapping[str, str], name: str, default: float,
    minimum: Optional[float] = None, maximum: Optional[float] = None,
) -> float:
    raw = env.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(str(raw).strip())
    except ValueError as exc:
        raise ConfigurationError(
            f"{name} must be a number, got {raw!r} (expected something like {default})"
        ) from exc
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ConfigurationError(f"{name} must be <= {maximum}, got {value}")
    return value


def _read_int(
    env: Mapping[str, str], name: str, default: int,
    minimum: Optional[int] = None, maximum: Optional[int] = None,
) -> int:
    value = _read_float(env, name, float(default), minimum, maximum)
    if float(value).is_integer():
        return int(value)
    raise ConfigurationError(f"{name} must be a whole number, got {value}")


@dataclass(frozen=True)
class Settings:
    """Validated runtime configuration. Instances are immutable."""

    data_mode: str = "demo"
    data_dir: Path = INTELLIGENCE_DIR / "data"
    demo_case_id: str = DEFAULT_DEMO_CASE_ID
    ais_max_plausible_speed_kn: float = 60.0
    ais_max_audit_records: int = 1000
    intelligence_port: int = 8000
    log_level: str = "INFO"

    # ---- derived paths -------------------------------------------------
    @property
    def demo_case_slug(self) -> str:
        """Filesystem name of the demo bundle. `CASE-001` -> `case_001`.

        The case id is an investigation identifier (upper case, hyphenated); the
        directory that holds a case's inputs and outputs is its lower-case,
        underscore-separated slug, so the two cannot drift apart.
        """
        return self.demo_case_id.lower().replace("-", "_")

    @property
    def demo_case_dir(self) -> Path:
        return self.data_dir / "demo" / self.demo_case_slug

    @property
    def demo_ais_csv(self) -> Path:
        return self.demo_case_dir / "ais" / "demo_ais_positions.csv"

    @property
    def is_demo_mode(self) -> bool:
        return self.data_mode == "demo"

    # ---- helpers for later phases --------------------------------------
    def ais_cleaning_config(self):
        """Cleaning thresholds as a Phase 3 CleaningConfig (import kept local)."""
        from app.ais.cleaning import CleaningConfig

        return CleaningConfig(
            max_plausible_speed_kn=self.ais_max_plausible_speed_kn,
            max_audit_records=self.ais_max_audit_records,
        )

    def describe(self) -> Dict[str, Any]:
        """JSON-friendly summary. Contains no credentials (there are none here)."""
        return {
            "dataMode": self.data_mode,
            "dataDir": str(self.data_dir),
            "demoCaseId": self.demo_case_id,
            "demoCaseSlug": self.demo_case_slug,
            "aisMaxPlausibleSpeedKn": self.ais_max_plausible_speed_kn,
            "aisMaxAuditRecords": self.ais_max_audit_records,
            "intelligencePort": self.intelligence_port,
            "logLevel": self.log_level,
        }

    def validate_paths(self) -> List[str]:
        """Return human-readable warnings about missing (not fatal) demo assets."""
        warnings: List[str] = []
        if self.is_demo_mode and not self.demo_ais_csv.exists():
            warnings.append(
                f"demo AIS file not found at {self.demo_ais_csv}; regenerate it with "
                "python3 intelligence/data/demo/generate_case_001.py"
            )
        return warnings


def get_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    """Read and VALIDATE configuration from the environment (or a supplied mapping)."""
    env = os.environ if env is None else env

    data_mode = _read_str(env, "ABYSS_DATA_MODE", "demo").lower()
    if data_mode not in DATA_MODES:
        raise ConfigurationError(
            f"ABYSS_DATA_MODE must be one of {DATA_MODES}, got {data_mode!r}"
        )

    demo_case_id = _read_str(env, "ABYSS_DEMO_CASE_ID", DEFAULT_DEMO_CASE_ID).upper()
    if not _CASE_ID_PATTERN.match(demo_case_id):
        raise ConfigurationError(
            f"ABYSS_DEMO_CASE_ID must look like CASE-001, got {demo_case_id!r}"
        )

    log_level = _read_str(env, "INTELLIGENCE_LOG_LEVEL", "INFO").upper()
    if log_level not in LOG_LEVELS:
        raise ConfigurationError(f"INTELLIGENCE_LOG_LEVEL must be one of {LOG_LEVELS}, got {log_level!r}")

    data_dir_raw = _read_str(env, "ABYSS_DATA_DIR", str(INTELLIGENCE_DIR / "data"))
    data_dir = Path(data_dir_raw).expanduser()
    if not data_dir.is_absolute():
        data_dir = (REPO_ROOT / data_dir).resolve() if data_dir_raw.startswith("intelligence") else (INTELLIGENCE_DIR / data_dir).resolve()

    return Settings(
        data_mode=data_mode,
        data_dir=data_dir,
        demo_case_id=demo_case_id,
        ais_max_plausible_speed_kn=_read_float(
            env, "ABYSS_AIS_MAX_PLAUSIBLE_SPEED_KN", 60.0, minimum=1.0, maximum=200.0
        ),
        ais_max_audit_records=_read_int(env, "ABYSS_AIS_MAX_AUDIT_RECORDS", 1000, minimum=1, maximum=1_000_000),
        intelligence_port=_read_int(env, "INTELLIGENCE_PORT", 8000, minimum=1, maximum=65535),
        log_level=log_level,
    )
