# ABYSS — AI-Powered Maritime Forensic Intelligence System

> **SIH 2026 — Problem Statement 26143**  
> Oil-spill attribution support from satellite observation + ocean/wind hindcasting + historical AIS.

ABYSS transforms an observed satellite oil slick into an **explainable forensic investigation**. It reconstructs a **probable origin region** and a **candidate release time window** from the observed slick and meteocean drift conditions, then filters and correlates historical AIS vessel traffic to produce a **ranked, explainable priority list of candidate vessels** whose trajectories and kinematics are *compatible* with that reconstruction.



**ABYSS is an investigation support system. It does not determine guilt or legal causation.**  
Candidate ranking orders evidence to prioritise human investigation. In demo mode, all datasets are synthetic and explicitly labelled as demonstration data.

---

## 1. Current System Architecture

The runnable hackathon evaluation stack operates as a clean, responsive, two-tier architecture:



* **No external network calls or cloud dependencies:** The operator console draws an equirectangular vector plot locally in SVG (no Mapbox, Leaflet tile servers, or Google Maps API keys required).
* **Single origin:** The Vite dev server proxies  directly to , eliminating CORS friction and preventing backend hosts from being hardcoded into bundle output.
* **Deterministic execution:** Same input data + same configuration = identical scores, rankings, and reports.

---

## 2. Current Technology Stack

| Layer | Technologies | Purpose |
|---|---|---|
| **Frontend Console** | React 18, Vite 5, Vanilla CSS3 (Custom Design System) | Operator dashboard, interactive timeline, evidence chain, SVG map, printable report |
| **Frontend Testing** | Node.js built-in test runner () | Pure math, projection, and report assembly verification (zero extraneous test framework deps) |
| **Backend API** | Python 3.11+, FastAPI, Uvicorn, Pydantic | High-performance asynchronous REST endpoints, request validation, error reporting |
| **Forensic & Data Engines** | NumPy, SciPy, Shapely, PyYAML | Vector drift integration, polygon convex hulls, trajectory kinematics, AIS cleaning |
| **Backend Testing** | Python  | Comprehensive unit and integration test suite (285 test cases) |

---

## 3. Repository Structure



---

## 4. Prerequisites

To run the ABYSS hackathon evaluation prototype, you need:

1. **Python 3.11+** (with virtual environment support)
2. **Node.js 18+** and **npm**

---

## 5. Quickstart: Running the Stack

Open two terminal windows:

### Terminal 1: Backend Intelligence Service (FastAPI)


*Health check:* Verify the service is active by visiting  or running:
{"dataSource":"Configuration (demo mode)","warnings":[],"status":"ok","service":"abyss-intelligence","dataMode":"demo","demoCaseId":"CASE-001"}

### Terminal 2: Frontend Operator Console (React / Vite)



Open your browser and navigate to:  
👉 **http://localhost:5173/**

---

## 6. Golden Demo Scenario: CASE-001

The repository includes a bundled, deterministic forensic demonstration case: **** (located at ).

### How to Run and Review the Investigation:
1. Open the console at .
2. The dashboard automatically requests  and loads the golden scenario:
   * **Observed Slick:** Synthetic Sentinel-1 SAR observation (), observed on  off the west coast of India.
   * **Hindcast Reconstruction:** Ocean currents and 10m wind fields integrate backwards across the candidate release window ( to ), deriving a **119.47 km² probable origin region**.
   * **Candidate Ranking:** 12 candidate vessels are screened, ranked, and color-coded.
3. Click on any vessel in the **Ranked candidate vessels** table to inspect synchronized evidence across all views:
   * **Map:** Highlights the selected vessel's reconstructed AIS track relative to the slick, origin region, and backdrift line.
   * **Candidate Details & Evidence Factors:** Displays the breakdown across all 5 evidential dimensions.
   * **Investigation Timeline:** Expands chronological encounters, closest points of approach, and AIS gap markers.
   * **Evidence Chain:** Traces the forensic cascade from raw sensor data to final priority rank.
   * **Report Generator:** Click **Generate Investigation Report** to compile a printable forensic dossier directly in your browser.

### Expected Baseline Results (CASE-001):
The pipeline scores and ranks vessels strictly based on multi-factor physics and kinematic evidence:
* **Rank 1 — DEMO MERIDIAN STAR (V001 / MMSI 900000001):** Total Score **83.564**. Inside the reconstructed origin region during the open release window; exhibits loitering / speed variation anomalies.
* **Rank 2 — DEMO CORAL VOYAGER (V002 / MMSI 900000002):** Total Score **83.200**. Carries a 4h 05m AIS gap crossing the origin region; evaluated as **physically feasible** at 10.5 knots.
* **Rank 3 — DEMO IRON HORIZON (V003 / MMSI 900000003):** Total Score **80.125**. Has an identical AIS gap timestamp, but bridging the distance would require **35.1 knots** (physically impossible for a bulk carrier; gap awarded 0 points).
* **Rank 4 — DEMO HARBOUR LIGHT (V004 / MMSI 900000004):** Total Score **0.000**. Demonstrates counterfactual exclusion: V004 was the physically closest vessel to the slick at observation time, but was 119 km away during the release window and never crossed the hindcast origin region.

---

## 7. Main Implemented Features

1. **Normalized Boundary & Ingestion Layer ():**
   * Pydantic-free boundary contracts (, , , , ).
   * Source adapters for satellite GeoJSON, AIS CSV position streams, and meteocean JSON grids.
   * Robust validation auditing sentinels (, , ), geographic bounds, and timestamps without silent drops.

2. **Satellite Detection & Look-Alike Screening ():**
   * Morphological segmentation metrics: slick area, perimeter, elongation, orientation, and centroid coordinates.
   * Rule-based screening against natural biogenic slicks, calm water zones, and algal blooms.

3. **Backward Environmental Drift Hindcasting ():**
   * Gridded spatial-temporal interpolation of surface currents and 10m wind fields.
   * Deterministic backward Lagrangian advection with configurable wind leeway coefficient.
   * Convex hull origin region derivation with spread and model confidence metrics.

4. **AIS Data Cleaning & Trajectory Construction ():**
   * Sanitization of duplicate timestamps, coordinate anomalies, and corrupt values with complete audit logs.
   * Trajectory reconstruction segmented by time, course changes, speed changes, and AIS outages.
   * Physics-gated gap feasibility evaluating minimum required speed to cross the origin area.

5. **5-Factor Evidential Scoring & Counterfactuals (, ):**
   * 100-point multi-factor model: Spatial Proximity (35 pts), Temporal Alignment (25 pts), Trajectory Integrity (20 pts), Behavioural Anomaly (10 pts), and AIS Gap Feasibility (10 pts).
   * Automated counterfactual explanations explaining why non-matching vessels (e.g. V004) are excluded.

6. **Interactive Operator Console ():**
   * Standalone SVG incident plot with coordinate graticules, dynamic metric scale bar, and track overlays.
   * Forensic chronological timeline with UTC timestamp guarantees.
   * Evidence cascade graph showing data provenance at every decision node.
   * Client-side printable investigation report generator.

---

## 8. Offline Demonstration & Reliability

* **100% Air-Gapped Operation:** All dependencies, algorithms, demo datasets, and projection math are packaged inside the repository.
* **Zero External Calls:** ABYSS does not call external map tile providers (OSM/Mapbox), remote APIs, or cloud services during demo execution.
* **No Authentication / Setup Friction:** Runs immediately out of the box with zero required API keys or environment variables.

---

## 9. Automated Testing & Verification

Both the backend and frontend include automated test suites:

### 1. Backend Python Test Suite (285 Tests)
Runs tests across all modules (ingestion, cleaning, trajectories, hindcast, detection, scoring, API, and CASE-001 scenario regression):

**Status: 285 passed, 0 failures, 0 errors**

### 2. Frontend Node.js Test Suite (68 Tests)
Runs tests on geo-projection mathematics, scale-bar computations, factor flattening, timeline construction, and report generation:

**Status: 68 passed, 0 failures, 0 errors**

### 3. Frontend Production Build
Validates Vite bundler optimization and packaging:

**Status: Built in <1s (0 errors, 0 warnings)**

---

## 10. Data Provenance & Scientific Honesty

* **Synthetic Demonstration Notice:** All bundled data () consists of synthetic demonstration fixtures. The UI prominently displays  chips and audit warnings on all screens.
* **Approved Forensic Language:** ABYSS outputs *candidate vessels, evidence compatibility, candidate ranking, probable origin, and behavioural anomalies*. It deliberately avoids accusatory assertions such as *guilty vessel, proven culprit, or criminal liability*.
* **Origin as a Region:** Reconstructed origins are presented as spatial regions with quantified uncertainty, never an over-confident single point.
* **AIS Gaps are Neutral:** An AIS gap alone is never treated as guilt; it is evaluated strictly for physical compatibility with the candidate event window.

---

## 11. Current Limitations & Future Scope

### Current Limitations (Prototype Stage)
* **Drift Engine:** Uses a 2D Eulerian-Lagrangian forward-Euler drift integrator across steady demo fields; not a full 3D ocean circulation hydrodynamic model.
* **Look-Alike Classifier:** Uses heuristic geometric/textural thresholds rather than a high-capacity deep CNN trained on multi-sensor SAR imagery.
* **Static Case Loading:** The prototype console currently focuses on deep forensic review of  rather than multi-tenant case management.

### Future Scope
* **Live Ingress Connectors:** Direct streaming integration with live Sentinel-1 GRD pipelines (Copernicus API) and terrestrial/satellite AIS receivers.
* **Advanced Hydrodynamics:** Integration with operational oceanographic models (HYCOM, Copernicus Marine CMEMS, NOAA GFS winds).
* **Enterprise Persistence:** Activation of a persistence tier (PostgreSQL / PostGIS) for persistent case histories and multi-analyst collaboration.

---

## 12. Disclaimer

ABYSS provides analytical evidence and candidate prioritization for maritime investigation support. Candidate ranking does not establish legal responsibility or causation.
