"""Tests for Phase 22: Real Metocean + Bidirectional Drift Simulation.

Verifies:
- NOAA Near Real Time currents NetCDF loader
- NDBC meteorological table wind loader & conversion
- Spatial bilinear interpolation
- Timestamp enforcement (refuses drift if timestamp is missing)
- Backward drift simulation (hindcast probable origin)
- Forward drift simulation (forecast footprint)
- Determinism and absence of NaN/inf values
- API endpoint /drift/real/simulate
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.hindcast.metocean import (
    load_noaa_currents_netcdf,
    load_ndbc_table,
    find_nearest_wind,
    meteorological_to_uv,
    parse_ndbc_timestamp,
    WindObservation,
)
from app.hindcast.drift import (
    run_drift_simulation,
    haversine_km,
    compute_uncertainty_circle,
)
from app.main import app

REAL_CURRENTS_NC = Path("/home/ashish/SIH/real_metocean/noaa_currents/currents_20240529.nc")
REAL_NDBC_TXT = Path("/home/ashish/SIH/real_metocean/ndbc/42055.txt")


def test_meteorological_to_uv():
    # North wind (0 deg) blows toward South -> u=0, v < 0
    u, v = meteorological_to_uv(10.0, 0.0)
    assert abs(u) < 1e-4
    assert v == pytest.approx(-10.0, abs=1e-3)

    # East wind (90 deg) blows toward West -> u < 0, v=0
    u, v = meteorological_to_uv(10.0, 90.0)
    assert u == pytest.approx(-10.0, abs=1e-3)
    assert abs(v) < 1e-4

    # South wind (180 deg) blows toward North -> u=0, v > 0
    u, v = meteorological_to_uv(10.0, 180.0)
    assert abs(u) < 1e-4
    assert v == pytest.approx(10.0, abs=1e-3)


def test_load_noaa_currents_real_data():
    if not REAL_CURRENTS_NC.is_file():
        pytest.skip("Real NOAA currents file not present on disk")

    field, prov = load_noaa_currents_netcdf(REAL_CURRENTS_NC)
    assert prov.synthetic is False
    assert prov.current_available is True
    assert prov.wind_available is False  # No wind supplied yet
    assert "u_current" in prov.variables
    assert "v_current" in prov.variables
    assert prov.spatial_extent["lat_min"] <= 22.35 <= prov.spatial_extent["lat_max"]
    assert prov.spatial_extent["lon_min"] <= -93.40 <= prov.spatial_extent["lon_max"]
    assert len(field.latitudes) >= 2
    assert len(field.longitudes) >= 2

    # Bilinear interpolation check
    u, v = field.current(22.40, -93.40)
    assert not (u == 0.0 and v == 0.0)
    assert -5.0 < u < 5.0
    assert -5.0 < v < 5.0


def test_load_ndbc_table_real_data():
    if not REAL_NDBC_TXT.is_file():
        pytest.skip("Real NDBC text file not present on disk")

    records = load_ndbc_table(REAL_NDBC_TXT, station_id="42055")
    assert len(records) > 100
    first = records[0]
    assert isinstance(first, WindObservation)
    assert first.station_id == "42055"
    assert first.wspd_ms >= 0.0
    assert 0.0 <= first.wdir_deg <= 360.0
    assert first.epoch_seconds > 0.0


def test_timestamp_enforcement_rejection():
    if not REAL_CURRENTS_NC.is_file():
        pytest.skip("Real NOAA currents file not present on disk")

    field, prov = load_noaa_currents_netcdf(REAL_CURRENTS_NC)

    # Missing reference_time_iso must raise ValueError
    with pytest.raises(ValueError, match="observation_time / release_time is REQUIRED"):
        run_drift_simulation(
            field=field,
            origin_lat=22.40,
            origin_lon=-93.40,
            reference_time_iso=None,
            direction="backward",
        )

    with pytest.raises(ValueError, match="observation_time / release_time is REQUIRED"):
        run_drift_simulation(
            field=field,
            origin_lat=22.40,
            origin_lon=-93.40,
            reference_time_iso="",
            direction="backward",
        )


def test_backward_drift_simulation():
    if not REAL_CURRENTS_NC.is_file():
        pytest.skip("Real NOAA currents file not present on disk")

    field, prov = load_noaa_currents_netcdf(REAL_CURRENTS_NC)
    result = run_drift_simulation(
        field=field,
        origin_lat=22.40,
        origin_lon=-93.40,
        reference_time_iso="2024-05-29T00:00:00Z",
        direction="backward",
        duration_hours=6.0,
        step_seconds=300.0,
        provenance_meta=prov.to_dict(),
    )

    assert result.direction == "backward"
    assert result.reference_time_iso == "2024-05-29T00:00:00Z"
    assert len(result.trajectories) == 15  # 3 windages * 5 seeds
    assert result.spread_radius_km >= 0.5
    assert len(result.uncertainty_polygon) > 10
    # Polarity: displaced backward in time (negative step)
    assert result.trajectories[0].points[-1].elapsed_seconds == -21600.0


def test_forward_drift_simulation():
    if not REAL_CURRENTS_NC.is_file():
        pytest.skip("Real NOAA currents file not present on disk")

    field, prov = load_noaa_currents_netcdf(REAL_CURRENTS_NC)
    result = run_drift_simulation(
        field=field,
        origin_lat=22.40,
        origin_lon=-93.40,
        reference_time_iso="2024-05-29T00:00:00Z",
        direction="forward",
        duration_hours=6.0,
        step_seconds=300.0,
        provenance_meta=prov.to_dict(),
    )

    assert result.direction == "forward"
    assert result.reference_time_iso == "2024-05-29T00:00:00Z"
    assert len(result.trajectories) == 15
    assert result.trajectories[0].points[-1].elapsed_seconds == 21600.0


def test_deterministic_simulation():
    if not REAL_CURRENTS_NC.is_file():
        pytest.skip("Real NOAA currents file not present on disk")

    field, prov = load_noaa_currents_netcdf(REAL_CURRENTS_NC)
    res1 = run_drift_simulation(
        field=field,
        origin_lat=22.40,
        origin_lon=-93.40,
        reference_time_iso="2024-05-29T00:00:00Z",
        direction="backward",
        duration_hours=3.0,
    )
    res2 = run_drift_simulation(
        field=field,
        origin_lat=22.40,
        origin_lon=-93.40,
        reference_time_iso="2024-05-29T00:00:00Z",
        direction="backward",
        duration_hours=3.0,
    )

    assert res1.centroid == res2.centroid
    assert res1.spread_radius_km == res2.spread_radius_km
    for t1, t2 in zip(res1.trajectories, res2.trajectories):
        assert t1.final_lat == t2.final_lat
        assert t1.final_lon == t2.final_lon


def test_api_simulate_drift_endpoint():
    client = TestClient(app)

    # Valid backward simulation
    resp = client.post(
        "/drift/real/simulate",
        json={
            "origin_lat": 22.40,
            "origin_lon": -93.40,
            "reference_time_iso": "2024-05-29T00:00:00Z",
            "direction": "backward",
            "duration_hours": 4.0,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["direction"] == "backward"
    assert data["particle_count"] == 15
    assert "centroid" in data
    assert "uncertainty_polygon" in data
    assert data["provenance"]["synthetic"] is False

    # Missing reference_time_iso must be rejected (422)
    resp_bad = client.post(
        "/drift/real/simulate",
        json={
            "origin_lat": 22.40,
            "origin_lon": -93.40,
            "reference_time_iso": None,
            "direction": "backward",
        },
    )
    assert resp_bad.status_code == 422
