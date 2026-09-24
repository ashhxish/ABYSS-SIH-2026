/**
 * Trimmed snapshot of the LIVE CASE-001 API responses, captured from the running
 * Phase 13 service (`POST /investigate` and `POST /detect`). Used as the test
 * fixture so assertions run against real engine output rather than invented
 * numbers. The data itself is the synthetic demonstration dataset.
 *
 * Regenerate with the snippet in README if the intelligence service changes.
 */
export const DETECTION = {
  "spillId": "SPILL-001",
  "caseId": "CASE-001",
  "acquisitionTime": "2026-03-14T06:00:00Z",
  "classification": "possible oil slick (dark formation candidate)",
  "detected": true,
  "detectionConfidence": 0.91,
  "detectionConfidenceNote": "Prototype confidence for the synthetic scene. It is NOT a scientifically validated detection probability and does not constitute ground truth.",
  "meetsConfidenceThreshold": true,
  "uiLabel": "DEMO DATA",
  "datasetLabel": "Synthetic Demonstration Dataset",
  "synthetic": true,
  "sensor": {
    "name": "synthetic demonstration SAR scene",
    "band": "C-band SAR-like (demonstration stand-in, not a real acquisition)",
    "synthetic": true
  },
  "characterisation": {
    "geometry": {
      "type": "Polygon",
      "coordinates": [
        [
          [
            72.207883,
            18.499508
          ],
          [
            72.209174,
            18.497192
          ],
          [
            72.209677,
            18.494347
          ],
          [
            72.209383,
            18.491023
          ],
          [
            72.208298,
            18.487276
          ],
          [
            72.206439,
            18.483171
          ],
          [
            72.203838,
            18.478777
          ],
          [
            72.200541,
            18.474171
          ],
          [
            72.196603,
            18.46943
          ],
          [
            72.192092,
            18.464636
          ],
          [
            72.187085,
            18.459871
          ],
          [
            72.181667,
            18.455216
          ],
          [
            72.175932,
            18.450752
          ],
          [
            72.169978,
            18.446554
          ],
          [
            72.163906,
            18.442694
          ],
          [
            72.15782,
            18.439238
          ],
          [
            72.151825,
            18.436246
          ],
          [
            72.146022,
            18.433769
          ],
          [
            72.140512,
            18.431849
          ],
          [
            72.135389,
            18.430519
          ],
          [
            72.130739,
            18.429801
          ],
          [
            72.126644,
            18.429708
          ],
          [
            72.123172,
            18.430242
          ],
          [
            72.120384,
            18.431393
          ],
          [
            72.118326,
            18.433142
          ],
          [
            72.117035,
            18.435458
          ],
          [
            72.116532,
            18.438303
          ],
          [
            72.116826,
            18.441627
          ],
          [
            72.117912,
            18.445374
          ],
          [
            72.119771,
            18.449479
          ],
          [
            72.122371,
            18.453873
          ],
          [
            72.125668,
            18.458479
          ],
          [
            72.129606,
            18.46322
          ],
          [
            72.134117,
            18.468014
          ],
          [
            72.139125,
            18.472779
          ],
          [
            72.144542,
            18.477434
          ],
          [
            72.150277,
            18.481898
          ],
          [
            72.156231,
            18.486096
          ],
          [
            72.162304,
            18.489956
          ],
          [
            72.168389,
            18.493412
          ],
          [
            72.174385,
            18.496404
          ],
          [
            72.180187,
            18.498881
          ],
          [
            72.185697,
            18.500801
          ],
          [
            72.190821,
            18.502132
          ],
          [
            72.19547,
            18.502849
          ],
          [
            72.199566,
            18.502942
          ],
          [
            72.203037,
            18.502408
          ],
          [
            72.205826,
            18.501257
          ],
          [
            72.207883,
            18.499508
          ]
        ]
      ]
    },
    "vertexCount": 49,
    "areaKm2": 41.258,
    "centroid": {
      "lat": 18.466325,
      "lon": 72.163105
    },
    "boundingBox": {
      "minLat": 18.429708,
      "maxLat": 18.502942,
      "minLon": 72.116532,
      "maxLon": 72.209677
    },
    "perimeterKm": 27.114,
    "approximateLengthKm": 12.0,
    "approximateWidthKm": 4.4,
    "orientationDeg": 52.0,
    "orientationNote": "Major axis of the elliptical synthetic slick, degrees clockwise from north."
  },
  "lookAlikeAssessment": {
    "classesConsidered": [
      "low wind area",
      "natural or biogenic film",
      "radar artefact",
      "sea-state variation"
    ],
    "checkedClasses": [
      "low wind area"
    ],
    "notAssessedClasses": [
      "natural or biogenic film",
      "radar artefact",
      "sea-state variation"
    ],
    "lowWindArea": false,
    "windSpeedMs": 8.0,
    "thresholdMs": 3.0,
    "lookAlikeWarning": false,
    "notes": [
      "Natural/biogenic films, radar artefacts and sea-state variations cannot be excluded from a single synthetic scene: they are reported as NOT assessed. A real investigation needs multi-sensor or in-situ confirmation.",
      "Wind speed at slick centroid (8.0 m/s >= 3.0 m/s) argues against a low-wind calm look-alike."
    ]
  },
  "lookAlikeWarning": false,
  "warnings": [
    "synthetic demonstration data (DEMO DATA) - not a real satellite acquisition"
  ]
}

export const INVESTIGATION = {
  "caseId": "CASE-001",
  "datasetLabel": "Synthetic Demonstration Dataset",
  "observedAt": "2026-03-14T06:00:00Z",
  "synthetic": true,
  "module": "investigation",
  "moduleVersion": "1.0.0",
  "weights": {
    "spatial": 35.0,
    "gap": 10.0,
    "trajectory": 20.0,
    "behaviour": 10.0,
    "temporal": 25.0
  },
  "statistics": {
    "vesselsScored": 12,
    "recordsCleaned": 3666,
    "insideRegionDuringWindow": 3,
    "gapsJudged": 2,
    "behaviourAnomaliesReported": 4,
    "originAreaKm2": 119.47,
    "originConfidence": 0.774,
    "weightsTotal": 100.0,
    "meanScore": 20.574,
    "topCandidateMmsi": "900000001",
    "tieGroupCount": 1
  },
  "ranking": {
    "orderingRule": "descending total score; ties broken by ascending MMSI (deterministic - equal evidence yields equal scores)",
    "tieGroups": [
      [
        "900000004",
        "900000005",
        "900000006",
        "900000007",
        "900000008",
        "900000009",
        "900000010",
        "900000011",
        "900000012"
      ]
    ],
    "notes": [
      "descending total score; ties broken by ascending MMSI (deterministic - equal evidence yields equal scores)",
      "an equal score is a real result: the evidence does not separate those candidates, and the identifier tie-break is a display choice, not a finding",
      "ranking orders evidence for investigation support; it never establishes legal responsibility"
    ],
    "entries": [
      {
        "mmsi": "900000001",
        "vesselId": "V001",
        "name": "DEMO MERIDIAN STAR",
        "vesselType": "Tanker (synthetic demonstration vessel)",
        "totalScore": 83.564,
        "distanceToSlickKm": 256.094,
        "factors": {
          "spatial": {
            "points": 35.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 0.0,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 20.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": true
            }
          },
          "behaviour": {
            "points": 3.564,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.3564,
              "scoredAnomaly": 0.3564,
              "scoredEligible": true,
              "description": "erratic speeds during the window; extended slow/loitering periods during the window"
            }
          },
          "temporal": {
            "points": 25.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": true,
              "relation": "during_window"
            }
          }
        },
        "reasons": [
          "distance to origin region: inside the estimated origin region during the window [35/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: movement through the region during the window is physically plausible (97/97 in-window segments within the 18 kn cap) [20/20]",
          "stop/slow pattern: own-baseline anomaly 0.36 while present in the region (erratic speeds during the window; extended slow/loitering periods during the window) [3.564/10]",
          "proximity to release window: present inside the origin region while the release window was open [25/25]"
        ],
        "rank": 1,
        "counterfactual": {
          "againstMmsi": "900000004",
          "againstName": "DEMO HARBOUR LIGHT",
          "text": "DEMO HARBOUR LIGHT is nearest to the observed slick (1.1 km) yet ranked 4 with 0 points against 83.564: slick proximity is not release proximity - DEMO MERIDIAN STAR was inside the origin region during the window, where proximity to the slick scores nothing",
          "factorDeltas": {
            "spatial": 35.0,
            "trajectory": 20.0,
            "behaviour": 3.564,
            "temporal": 25.0
          }
        },
        "compatibility": {
          "mmsi": "900000001",
          "minDistanceKmDuringWindow": 0.0,
          "minDistanceKmWholeTrack": 0.0,
          "insideRegionDuringWindow": true,
          "insideRegionAnytime": true,
          "insideRegionRelation": "during_window",
          "firstInsideTimestamp": "2026-03-13T05:55:00Z",
          "recordsInWindow": 97,
          "windowPresenceSeconds": 15600,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 97,
          "plausibleSegmentsInWindow": 97,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 17.55,
          "movementThroughRegion": true,
          "closestInWindow": {
            "timestamp": "2026-03-13T10:00:00Z",
            "lat": 18.284389,
            "lon": 71.880075,
            "distanceKm": 0.0
          },
          "filters": {
            "spatial": true,
            "temporal": true,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000001",
          "baseline": {
            "records": 425,
            "medianSogKn": 11.4,
            "spreadSogKn": 10.2,
            "turnsPerHour": 0.0,
            "slowFraction": 0.2259,
            "trackHours": 35.333
          },
          "window": {
            "records": 97,
            "medianSogKn": 11.3,
            "spreadSogKn": 10.1,
            "turnsPerHour": 0.0,
            "slowFraction": 0.4948,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0088,
            "variability": 1.0,
            "turnExcess": 0.0,
            "loiterExcess": 0.269
          },
          "rawAnomaly": 0.3564,
          "isAnomaly": true,
          "scoredEligible": true,
          "scoredAnomaly": 0.3564,
          "description": "erratic speeds during the window; extended slow/loitering periods during the window",
          "notes": [
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000001",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 15.21,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000002",
        "vesselId": "V002",
        "name": "DEMO CORAL VOYAGER",
        "vesselType": "Tanker (synthetic demonstration vessel)",
        "totalScore": 83.2,
        "distanceToSlickKm": 255.055,
        "factors": {
          "spatial": {
            "points": 35.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 0.0,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 3.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.3,
              "capPerGap": 0.3,
              "gaps": [
                {
                  "start": "2026-03-13T11:55:00Z",
                  "feasible": true,
                  "relevance": 1.0,
                  "contribution": 0.3
                }
              ]
            }
          },
          "trajectory": {
            "points": 20.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": true
            }
          },
          "behaviour": {
            "points": 0.2,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.02,
              "scoredAnomaly": 0.02,
              "scoredEligible": true,
              "description": "broadly consistent with own baseline"
            }
          },
          "temporal": {
            "points": 25.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": true,
              "relation": "during_window"
            }
          }
        },
        "reasons": [
          "distance to origin region: inside the estimated origin region during the window [35/35]",
          "AIS-gap behaviour: AIS gap of 4.1 h overlaps the window and is traversable at 10.5 kn - weak, capped evidence [3/10]",
          "course-change correlation: movement through the region during the window is physically plausible (48/48 in-window segments within the 16 kn cap) [20/20]",
          "stop/slow pattern: own-baseline anomaly 0.02 while present in the region (broadly consistent with own baseline) [0.2/10]",
          "proximity to release window: present inside the origin region while the release window was open [25/25]"
        ],
        "rank": 2,
        "counterfactual": {
          "againstMmsi": "900000001",
          "againstName": "DEMO MERIDIAN STAR",
          "text": "Ranked below DEMO MERIDIAN STAR (83.564 vs 83.2): DEMO MERIDIAN STAR led on behaviour +3.364, gap +-3",
          "factorDeltas": {
            "gap": -3.0,
            "behaviour": 3.364
          }
        },
        "compatibility": {
          "mmsi": "900000002",
          "minDistanceKmDuringWindow": 0.0,
          "minDistanceKmWholeTrack": 0.0,
          "insideRegionDuringWindow": true,
          "insideRegionAnytime": true,
          "insideRegionRelation": "during_window",
          "firstInsideTimestamp": "2026-03-13T11:20:00Z",
          "recordsInWindow": 49,
          "windowPresenceSeconds": 2100,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 48,
          "plausibleSegmentsInWindow": 48,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 16.05,
          "movementThroughRegion": true,
          "closestInWindow": {
            "timestamp": "2026-03-13T11:20:00Z",
            "lat": 18.212328,
            "lon": 71.790773,
            "distanceKm": 0.0
          },
          "filters": {
            "spatial": true,
            "temporal": true,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000002",
          "baseline": {
            "records": 325,
            "medianSogKn": 10.5,
            "spreadSogKn": 0.4,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "trackHours": 31.0
          },
          "window": {
            "records": 49,
            "medianSogKn": 10.5,
            "spreadSogKn": 0.4,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0,
            "variability": 0.0667,
            "turnExcess": 0.0,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.02,
          "isAnomaly": false,
          "scoredEligible": true,
          "scoredAnomaly": 0.02,
          "description": "broadly consistent with own baseline",
          "notes": [
            "behaviour consistent with own baseline during the window",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000002",
          "hasGap": true,
          "gapCount": 1,
          "capSpeedKn": 13.91,
          "anyFeasible": true,
          "anyRelevant": true,
          "bestEvidenceValue": 1.0,
          "gaps": [
            {
              "start": "2026-03-13T11:55:00Z",
              "end": "2026-03-13T16:00:00Z",
              "durationHours": 4.0833,
              "straightLineKm": 79.432,
              "impliedSpeedKn": 10.504,
              "overlapsWindow": true,
              "overlapHours": 4.0833,
              "gapFractionInWindow": 1.0,
              "before": {
                "lat": 18.279065,
                "lon": 71.873729,
                "timestamp": "2026-03-13T11:55:00Z",
                "distanceToRegionKm": 0.0,
                "insideRegion": true
              },
              "after": {
                "lat": 18.7375,
                "lon": 72.451454,
                "timestamp": "2026-03-13T16:00:00Z",
                "distanceToRegionKm": 61.588,
                "insideRegion": false
              },
              "endpointNearRegion": true,
              "capSpeedKn": 13.91,
              "feasible": true,
              "relevance": 1.0,
              "reasons": [
                "gap 2026-03-13T11:55:00Z to 2026-03-13T16:00:00Z (4.08 h, 79.4 km straight line)",
                "bridging requires 10.5 kn against a cap of 13.9 kn (own max 10.7 kn x 1.3)",
                "overlaps the window (4.08 h of the gap) with an endpoint inside the origin region - relevant"
              ],
              "note": "a gap alone never raises suspicion (docs/methodology.md)"
            }
          ],
          "notes": [
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000003",
        "vesselId": "V003",
        "name": "DEMO IRON HORIZON",
        "vesselType": "Tanker (synthetic demonstration vessel)",
        "totalScore": 80.125,
        "distanceToSlickKm": 273.129,
        "factors": {
          "spatial": {
            "points": 35.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 0.0,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": [
                {
                  "start": "2026-03-13T11:55:00Z",
                  "feasible": false,
                  "relevance": 1.0,
                  "contribution": 0.0
                }
              ]
            }
          },
          "trajectory": {
            "points": 20.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": true
            }
          },
          "behaviour": {
            "points": 0.125,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.0125,
              "scoredAnomaly": 0.0125,
              "scoredEligible": true,
              "description": "broadly consistent with own baseline"
            }
          },
          "temporal": {
            "points": 25.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": true,
              "relation": "during_window"
            }
          }
        },
        "reasons": [
          "distance to origin region: inside the estimated origin region during the window [35/35]",
          "AIS-gap behaviour: relevant gap but physically impossible to traverse (35.1 kn required vs 15.9 kn cap) [0/10]",
          "course-change correlation: movement through the region during the window is physically plausible (48/48 in-window segments within the 18 kn cap) [20/20]",
          "stop/slow pattern: own-baseline anomaly 0.01 while present in the region (broadly consistent with own baseline) [0.125/10]",
          "proximity to release window: present inside the origin region while the release window was open [25/25]"
        ],
        "rank": 3,
        "counterfactual": {
          "againstMmsi": "900000002",
          "againstName": "DEMO CORAL VOYAGER",
          "text": "Ranked below DEMO CORAL VOYAGER (83.2 vs 80.125): DEMO CORAL VOYAGER led on gap +3, behaviour +0.075",
          "factorDeltas": {
            "gap": 3.0,
            "behaviour": 0.075
          }
        },
        "compatibility": {
          "mmsi": "900000003",
          "minDistanceKmDuringWindow": 0.0,
          "minDistanceKmWholeTrack": 0.0,
          "insideRegionDuringWindow": true,
          "insideRegionAnytime": true,
          "insideRegionRelation": "during_window",
          "firstInsideTimestamp": "2026-03-13T11:40:00Z",
          "recordsInWindow": 49,
          "windowPresenceSeconds": 900,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 48,
          "plausibleSegmentsInWindow": 48,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 18.3,
          "movementThroughRegion": true,
          "closestInWindow": {
            "timestamp": "2026-03-13T11:40:00Z",
            "lat": 18.220191,
            "lon": 71.787636,
            "distanceKm": 0.0
          },
          "filters": {
            "spatial": true,
            "temporal": true,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000003",
          "baseline": {
            "records": 186,
            "medianSogKn": 12.1,
            "spreadSogKn": 0.4,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "trackHours": 19.417
          },
          "window": {
            "records": 49,
            "medianSogKn": 12.2,
            "spreadSogKn": 0.2,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0083,
            "variability": 0.0333,
            "turnExcess": 0.0,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.0125,
          "isAnomaly": false,
          "scoredEligible": true,
          "scoredAnomaly": 0.0125,
          "description": "broadly consistent with own baseline",
          "notes": [
            "behaviour consistent with own baseline during the window",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000003",
          "hasGap": true,
          "gapCount": 1,
          "capSpeedKn": 15.86,
          "anyFeasible": false,
          "anyRelevant": true,
          "bestEvidenceValue": 0.0,
          "gaps": [
            {
              "start": "2026-03-13T11:55:00Z",
              "end": "2026-03-13T16:00:00Z",
              "durationHours": 4.0833,
              "straightLineKm": 265.782,
              "impliedSpeedKn": 35.146,
              "overlapsWindow": true,
              "overlapHours": 4.0833,
              "gapFractionInWindow": 1.0,
              "before": {
                "lat": 18.246133,
                "lon": 71.833792,
                "timestamp": "2026-03-13T11:55:00Z",
                "distanceToRegionKm": 0.0,
                "insideRegion": true
              },
              "after": {
                "lat": 19.429228,
                "lon": 74.028296,
                "timestamp": "2026-03-13T16:00:00Z",
                "distanceToRegionKm": 242.004,
                "insideRegion": false
              },
              "endpointNearRegion": true,
              "capSpeedKn": 15.86,
              "feasible": false,
              "relevance": 1.0,
              "reasons": [
                "gap 2026-03-13T11:55:00Z to 2026-03-13T16:00:00Z (4.08 h, 265.8 km straight line)",
                "bridging requires 35.1 kn against a cap of 15.9 kn (own max 12.2 kn x 1.3)",
                "INFEASIBLE: required speed exceeds what this vessel ever reported - the gap cannot hide a transit",
                "overlaps the window (4.08 h of the gap) with an endpoint inside the origin region - relevant"
              ],
              "note": "a gap alone never raises suspicion (docs/methodology.md)"
            }
          ],
          "notes": [
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000004",
        "vesselId": "V004",
        "name": "DEMO HARBOUR LIGHT",
        "vesselType": "Cargo (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 1.087,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 119.171,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.015,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "broadly consistent with own baseline"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "never"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 119.2 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour broadly consistent with own baseline; no presence in the region to correlate with [0/10]",
          "proximity to release window: never observed inside the origin region during the window [0/25]"
        ],
        "rank": 4,
        "counterfactual": {
          "againstMmsi": "900000003",
          "againstName": "DEMO IRON HORIZON",
          "text": "Ranked below DEMO IRON HORIZON (80.125 vs 0): DEMO IRON HORIZON led on spatial +35, temporal +25, trajectory +20, behaviour +0.125",
          "factorDeltas": {
            "spatial": 35.0,
            "trajectory": 20.0,
            "behaviour": 0.125,
            "temporal": 25.0
          }
        },
        "compatibility": {
          "mmsi": "900000004",
          "minDistanceKmDuringWindow": 119.171,
          "minDistanceKmWholeTrack": 13.16,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": false,
          "insideRegionRelation": "never",
          "firstInsideTimestamp": null,
          "recordsInWindow": 57,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 16800,
          "segmentsInWindow": 57,
          "plausibleSegmentsInWindow": 57,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 13.8,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T18:00:00Z",
            "lat": 17.196093,
            "lon": 72.136627,
            "distanceKm": 119.171
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000004",
          "baseline": {
            "records": 200,
            "medianSogKn": 8.9,
            "spreadSogKn": 7.2,
            "turnsPerHour": 0.06,
            "slowFraction": 0.24,
            "trackHours": 16.583
          },
          "window": {
            "records": 57,
            "medianSogKn": 8.9,
            "spreadSogKn": 0.3,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0,
            "variability": 0.05,
            "turnExcess": 0.0,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.015,
          "isAnomaly": false,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "broadly consistent with own baseline",
          "notes": [
            "behaviour consistent with own baseline during the window",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000004",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 11.96,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000005",
        "vesselId": "V005",
        "name": "DEMO SILVER TIDE",
        "vesselType": "Cargo (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 82.088,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 108.066,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.0214,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "broadly consistent with own baseline"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "after_window"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 108.1 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour broadly consistent with own baseline; no presence in the region to correlate with [0/10]",
          "proximity to release window: enters the origin region only AFTER the window closed at 2026-03-13T18:00:00Z - right place, wrong time [0/25]"
        ],
        "rank": 5,
        "counterfactual": {
          "againstMmsi": "900000004",
          "againstName": "DEMO HARBOUR LIGHT",
          "text": "Scored equally with DEMO HARBOUR LIGHT (0 vs 0); ordered after it by the MMSI tie-break (deterministic, not evidential)",
          "factorDeltas": {}
        },
        "compatibility": {
          "mmsi": "900000005",
          "minDistanceKmDuringWindow": 108.066,
          "minDistanceKmWholeTrack": 0.0,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": true,
          "insideRegionRelation": "after_window",
          "firstInsideTimestamp": "2026-03-13T23:20:00Z",
          "recordsInWindow": 94,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 27900,
          "segmentsInWindow": 94,
          "plausibleSegmentsInWindow": 94,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 16.8,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T18:00:00Z",
            "lat": 17.520907,
            "lon": 71.085053,
            "distanceKm": 108.066
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000005",
          "baseline": {
            "records": 237,
            "medianSogKn": 11.0,
            "spreadSogKn": 0.4,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "trackHours": 19.667
          },
          "window": {
            "records": 94,
            "medianSogKn": 11.05,
            "spreadSogKn": 0.4,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0045,
            "variability": 0.0667,
            "turnExcess": 0.0,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.0214,
          "isAnomaly": false,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "broadly consistent with own baseline",
          "notes": [
            "behaviour consistent with own baseline during the window",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000005",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 14.56,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000006",
        "vesselId": "V006",
        "name": "DEMO FROST PELICAN",
        "vesselType": "Cargo (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 164.848,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 174.28,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.3465,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "erratic speeds during the window"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "never"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 174.3 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour anomaly 0.35 (erratic speeds during the window) but OUTSIDE the origin region during the window - context only, not evidence [0/10]",
          "proximity to release window: never observed inside the origin region during the window [0/25]"
        ],
        "rank": 6,
        "counterfactual": {
          "againstMmsi": "900000005",
          "againstName": "DEMO SILVER TIDE",
          "text": "Scored equally with DEMO SILVER TIDE (0 vs 0); ordered after it by the MMSI tie-break (deterministic, not evidential)",
          "factorDeltas": {}
        },
        "compatibility": {
          "mmsi": "900000006",
          "minDistanceKmDuringWindow": 174.28,
          "minDistanceKmWholeTrack": 159.812,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": false,
          "insideRegionRelation": "never",
          "firstInsideTimestamp": null,
          "recordsInWindow": 49,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 49,
          "plausibleSegmentsInWindow": 49,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 12.3,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T10:00:00Z",
            "lat": 18.040573,
            "lon": 73.623502,
            "distanceKm": 174.28
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000006",
          "baseline": {
            "records": 431,
            "medianSogKn": 7.8,
            "spreadSogKn": 5.3,
            "turnsPerHour": 0.32,
            "slowFraction": 0.4014,
            "trackHours": 71.833
          },
          "window": {
            "records": 49,
            "medianSogKn": 8.1,
            "spreadSogKn": 5.2,
            "turnsPerHour": 0.375,
            "slowFraction": 0.0204,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0385,
            "variability": 0.8667,
            "turnExcess": 0.375,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.3465,
          "isAnomaly": true,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "erratic speeds during the window",
          "notes": [
            "behaviour anomaly detected but the vessel was outside the origin region during the window - reported as context, scored 0",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000006",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 10.66,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000007",
        "vesselId": "V007",
        "name": "DEMO NORTHERN GATE",
        "vesselType": "Tanker (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 266.198,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 81.091,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.02,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "broadly consistent with own baseline"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "never"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 81.1 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour broadly consistent with own baseline; no presence in the region to correlate with [0/10]",
          "proximity to release window: never observed inside the origin region during the window [0/25]"
        ],
        "rank": 7,
        "counterfactual": {
          "againstMmsi": "900000006",
          "againstName": "DEMO FROST PELICAN",
          "text": "Scored equally with DEMO FROST PELICAN (0 vs 0); ordered after it by the MMSI tie-break (deterministic, not evidential)",
          "factorDeltas": {}
        },
        "compatibility": {
          "mmsi": "900000007",
          "minDistanceKmDuringWindow": 81.091,
          "minDistanceKmWholeTrack": 81.091,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": false,
          "insideRegionRelation": "never",
          "firstInsideTimestamp": null,
          "recordsInWindow": 97,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 97,
          "plausibleSegmentsInWindow": 97,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 19.05,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T13:35:00Z",
            "lat": 17.490687,
            "lon": 71.807742,
            "distanceKm": 81.091
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000007",
          "baseline": {
            "records": 274,
            "medianSogKn": 12.5,
            "spreadSogKn": 0.4,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "trackHours": 22.75
          },
          "window": {
            "records": 97,
            "medianSogKn": 12.5,
            "spreadSogKn": 0.4,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0,
            "variability": 0.0667,
            "turnExcess": 0.0,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.02,
          "isAnomaly": false,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "broadly consistent with own baseline",
          "notes": [
            "behaviour consistent with own baseline during the window",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000007",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 16.51,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000008",
        "vesselId": "V008",
        "name": "DEMO SEA LARK",
        "vesselType": "Fishing (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 217.278,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 158.097,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.43,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "slowdown against own baseline; erratic speeds during the window; extended slow/loitering periods during the window"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "never"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 158.1 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour anomaly 0.43 (slowdown against own baseline; erratic speeds during the window; extended slow/loitering periods during the window) but OUTSIDE the origin region during the window - context only, not evidence [0/10]",
          "proximity to release window: never observed inside the origin region during the window [0/25]"
        ],
        "rank": 8,
        "counterfactual": {
          "againstMmsi": "900000007",
          "againstName": "DEMO NORTHERN GATE",
          "text": "Scored equally with DEMO NORTHERN GATE (0 vs 0); ordered after it by the MMSI tie-break (deterministic, not evidential)",
          "factorDeltas": {}
        },
        "compatibility": {
          "mmsi": "900000008",
          "minDistanceKmDuringWindow": 158.097,
          "minDistanceKmWholeTrack": 158.097,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": false,
          "insideRegionRelation": "never",
          "firstInsideTimestamp": null,
          "recordsInWindow": 49,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 49,
          "plausibleSegmentsInWindow": 49,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 6.9,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T12:00:00Z",
            "lat": 18.242443,
            "lon": 70.290368,
            "distanceKm": 158.097
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000008",
          "baseline": {
            "records": 430,
            "medianSogKn": 3.0,
            "spreadSogKn": 4.4,
            "turnsPerHour": 0.07,
            "slowFraction": 0.5302,
            "trackHours": 71.833
          },
          "window": {
            "records": 49,
            "medianSogKn": 1.6,
            "spreadSogKn": 4.4,
            "turnsPerHour": 0.125,
            "slowFraction": 0.7551,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.4667,
            "variability": 0.7333,
            "turnExcess": 0.125,
            "loiterExcess": 0.2249
          },
          "rawAnomaly": 0.43,
          "isAnomaly": true,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "slowdown against own baseline; erratic speeds during the window; extended slow/loitering periods during the window",
          "notes": [
            "behaviour anomaly detected but the vessel was outside the origin region during the window - reported as context, scored 0",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000008",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 5.98,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000009",
        "vesselId": "V009",
        "name": "DEMO SKY BRIDGE",
        "vesselType": "Passenger (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 129.125,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 102.347,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.1166,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "broadly consistent with own baseline"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "never"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 102.3 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour broadly consistent with own baseline; no presence in the region to correlate with [0/10]",
          "proximity to release window: never observed inside the origin region during the window [0/25]"
        ],
        "rank": 9,
        "counterfactual": {
          "againstMmsi": "900000008",
          "againstName": "DEMO SEA LARK",
          "text": "Scored equally with DEMO SEA LARK (0 vs 0); ordered after it by the MMSI tie-break (deterministic, not evidential)",
          "factorDeltas": {}
        },
        "compatibility": {
          "mmsi": "900000009",
          "minDistanceKmDuringWindow": 102.347,
          "minDistanceKmWholeTrack": 102.347,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": false,
          "insideRegionRelation": "never",
          "firstInsideTimestamp": null,
          "recordsInWindow": 49,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 49,
          "plausibleSegmentsInWindow": 49,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 29.1,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T16:20:00Z",
            "lat": 19.298511,
            "lon": 72.009628,
            "distanceKm": 102.347
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000009",
          "baseline": {
            "records": 432,
            "medianSogKn": 19.0,
            "spreadSogKn": 0.8,
            "turnsPerHour": 0.237,
            "slowFraction": 0.0,
            "trackHours": 71.833
          },
          "window": {
            "records": 49,
            "medianSogKn": 18.9,
            "spreadSogKn": 0.8,
            "turnsPerHour": 0.375,
            "slowFraction": 0.0,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0053,
            "variability": 0.1333,
            "turnExcess": 0.375,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.1166,
          "isAnomaly": false,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "broadly consistent with own baseline",
          "notes": [
            "behaviour consistent with own baseline during the window",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000009",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 25.22,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000010",
        "vesselId": "V010",
        "name": "DEMO COASTAL WREN",
        "vesselType": "Cargo (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 236.519,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 52.896,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.0143,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "broadly consistent with own baseline"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "never"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 52.9 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour broadly consistent with own baseline; no presence in the region to correlate with [0/10]",
          "proximity to release window: never observed inside the origin region during the window [0/25]"
        ],
        "rank": 10,
        "counterfactual": {
          "againstMmsi": "900000009",
          "againstName": "DEMO SKY BRIDGE",
          "text": "Scored equally with DEMO SKY BRIDGE (0 vs 0); ordered after it by the MMSI tie-break (deterministic, not evidential)",
          "factorDeltas": {}
        },
        "compatibility": {
          "mmsi": "900000010",
          "minDistanceKmDuringWindow": 52.896,
          "minDistanceKmWholeTrack": 36.398,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": false,
          "insideRegionRelation": "never",
          "firstInsideTimestamp": null,
          "recordsInWindow": 49,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 49,
          "plausibleSegmentsInWindow": 49,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 10.65,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T10:00:00Z",
            "lat": 18.156008,
            "lon": 72.461354,
            "distanceKm": 52.896
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000010",
          "baseline": {
            "records": 191,
            "medianSogKn": 7.0,
            "spreadSogKn": 0.2,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "trackHours": 31.833
          },
          "window": {
            "records": 49,
            "medianSogKn": 7.1,
            "spreadSogKn": 0.2,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0143,
            "variability": 0.0333,
            "turnExcess": 0.0,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.0143,
          "isAnomaly": false,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "broadly consistent with own baseline",
          "notes": [
            "behaviour consistent with own baseline during the window",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000010",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 9.23,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000011",
        "vesselId": "V011",
        "name": "DEMO ANCHOR TUG",
        "vesselType": "Tug (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 98.395,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 106.815,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.6619,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "slowdown against own baseline; erratic speeds during the window; extended slow/loitering periods during the window"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "never"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 106.8 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour anomaly 0.66 (slowdown against own baseline; erratic speeds during the window; extended slow/loitering periods during the window) but OUTSIDE the origin region during the window - context only, not evidence [0/10]",
          "proximity to release window: never observed inside the origin region during the window [0/25]"
        ],
        "rank": 11,
        "counterfactual": {
          "againstMmsi": "900000010",
          "againstName": "DEMO COASTAL WREN",
          "text": "Scored equally with DEMO COASTAL WREN (0 vs 0); ordered after it by the MMSI tie-break (deterministic, not evidential)",
          "factorDeltas": {}
        },
        "compatibility": {
          "mmsi": "900000011",
          "minDistanceKmDuringWindow": 106.815,
          "minDistanceKmWholeTrack": 98.343,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": false,
          "insideRegionRelation": "never",
          "firstInsideTimestamp": null,
          "recordsInWindow": 49,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 28800,
          "segmentsInWindow": 49,
          "plausibleSegmentsInWindow": 49,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 9.15,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T18:00:00Z",
            "lat": 17.814521,
            "lon": 72.841017,
            "distanceKm": 106.815
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000011",
          "baseline": {
            "records": 432,
            "medianSogKn": 3.0,
            "spreadSogKn": 6.0,
            "turnsPerHour": 0.251,
            "slowFraction": 0.5,
            "trackHours": 71.833
          },
          "window": {
            "records": 49,
            "medianSogKn": 0.1,
            "spreadSogKn": 6.0,
            "turnsPerHour": 0.125,
            "slowFraction": 0.7347,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.9667,
            "variability": 1.0,
            "turnExcess": 0.125,
            "loiterExcess": 0.2347
          },
          "rawAnomaly": 0.6619,
          "isAnomaly": true,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "slowdown against own baseline; erratic speeds during the window; extended slow/loitering periods during the window",
          "notes": [
            "behaviour anomaly detected but the vessel was outside the origin region during the window - reported as context, scored 0",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000011",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 7.93,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      },
      {
        "mmsi": "900000012",
        "vesselId": "V012",
        "name": "DEMO FAR CURRENT",
        "vesselType": "Cargo (synthetic demonstration vessel)",
        "totalScore": 0.0,
        "distanceToSlickKm": 93.601,
        "factors": {
          "spatial": {
            "points": 0.0,
            "maxPoints": 35.0,
            "detail": {
              "minDistanceKmDuringWindow": 139.838,
              "falloffKm": 30.0
            }
          },
          "gap": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "value": 0.0,
              "capPerGap": 0.3,
              "gaps": []
            }
          },
          "trajectory": {
            "points": 0.0,
            "maxPoints": 20.0,
            "detail": {
              "plausibleSegmentFraction": 1.0,
              "engaged": false
            }
          },
          "behaviour": {
            "points": 0.0,
            "maxPoints": 10.0,
            "detail": {
              "rawAnomaly": 0.0312,
              "scoredAnomaly": 0.0,
              "scoredEligible": false,
              "description": "broadly consistent with own baseline"
            }
          },
          "temporal": {
            "points": 0.0,
            "maxPoints": 25.0,
            "detail": {
              "insideRegionDuringWindow": false,
              "relation": "after_window"
            }
          }
        },
        "reasons": [
          "distance to origin region: closest in-window approach 139.8 km - beyond the 30 km falloff, no spatial evidence [0/35]",
          "AIS-gap behaviour: no AIS gap - the absence of a gap is not evidence either [0/10]",
          "course-change correlation: no transit of the origin region during the window - no course correlation to score [0/20]",
          "stop/slow pattern: behaviour broadly consistent with own baseline; no presence in the region to correlate with [0/10]",
          "proximity to release window: enters the origin region only AFTER the window closed at 2026-03-13T18:00:00Z - right place, wrong time [0/25]"
        ],
        "rank": 12,
        "counterfactual": {
          "againstMmsi": "900000011",
          "againstName": "DEMO ANCHOR TUG",
          "text": "Scored equally with DEMO ANCHOR TUG (0 vs 0); ordered after it by the MMSI tie-break (deterministic, not evidential)",
          "factorDeltas": {}
        },
        "compatibility": {
          "mmsi": "900000012",
          "minDistanceKmDuringWindow": 139.838,
          "minDistanceKmWholeTrack": 0.0,
          "insideRegionDuringWindow": false,
          "insideRegionAnytime": true,
          "insideRegionRelation": "after_window",
          "firstInsideTimestamp": "2026-03-14T00:10:00Z",
          "recordsInWindow": 32,
          "windowPresenceSeconds": 0,
          "windowCoverageSeconds": 18600,
          "segmentsInWindow": 32,
          "plausibleSegmentsInWindow": 32,
          "plausibleSegmentFraction": 1.0,
          "speedCapKn": 19.95,
          "movementThroughRegion": false,
          "closestInWindow": {
            "timestamp": "2026-03-13T18:00:00Z",
            "lat": 17.334174,
            "lon": 70.857713,
            "distanceKm": 139.838
          },
          "filters": {
            "spatial": false,
            "temporal": false,
            "trajectory": true
          },
          "notes": [
            "distances are to the ESTIMATED origin region (with positional buffer), never to any hidden truth",
            "pass/fail flags annotate the facts; points are assigned by the evidence engine",
            "windowPresenceSeconds counts time INSIDE the region while the window was open; windowCoverageSeconds counts time the window is covered by records at all (AIS availability) - the two are deliberately separate measurements",
            "config: {'spatialFalloffKm': 30.0, 'trajectoryPlausibilityFloor': 0.9, 'maxPlausibleSpeedKn': 60.0, 'speedSafetyFactor': 1.5, 'minSpeedCapKn': 5.0}"
          ],
          "warnings": []
        },
        "behaviour": {
          "mmsi": "900000012",
          "baseline": {
            "records": 102,
            "medianSogKn": 13.0,
            "spreadSogKn": 0.6,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "trackHours": 17.0
          },
          "window": {
            "records": 32,
            "medianSogKn": 12.95,
            "spreadSogKn": 0.6,
            "turnsPerHour": 0.0,
            "slowFraction": 0.0,
            "hours": 8.0
          },
          "components": {
            "speedShift": 0.0038,
            "variability": 0.1,
            "turnExcess": 0.0,
            "loiterExcess": 0.0
          },
          "rawAnomaly": 0.0312,
          "isAnomaly": false,
          "scoredEligible": false,
          "scoredAnomaly": 0.0,
          "description": "broadly consistent with own baseline",
          "notes": [
            "behaviour consistent with own baseline during the window",
            "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability(window speed spread vs reference) + 0.20*turnExcess(window rate vs reference) + 0.20*loiterExcess(window slow fraction vs own baseline); prototype component weights"
          ],
          "note": "raw anomaly compares the vessel with itself; the scoring phase gates it on spatial presence in the origin region"
        },
        "gapAnalysis": {
          "mmsi": "900000012",
          "hasGap": false,
          "gapCount": 0,
          "capSpeedKn": 17.29,
          "anyFeasible": false,
          "anyRelevant": false,
          "bestEvidenceValue": 0.0,
          "gaps": [],
          "notes": [
            "no AIS gap in the track; the ABSENCE of a gap is not evidence either - gap contribution is 0",
            "a gap alone never raises suspicion: it contributes only when relevant to the window/region AND physically feasible, and the engine caps its share (config: {'feasibilityMargin': 1.3, 'minFeasibleSpeedKn': 5.0, 'globalMaxSpeedKn': 60.0, 'endpointNearRegionKm': 30.0})"
          ]
        }
      }
    ]
  },
  "origin": {
    "region": {
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [
              71.787338,
              18.228618
            ],
            [
              71.789359,
              18.223349
            ],
            [
              71.794437,
              18.220387
            ],
            [
              71.802223,
              18.219936
            ],
            [
              71.812179,
              18.222029
            ],
            [
              71.823613,
              18.226519
            ],
            [
              71.835731,
              18.233098
            ],
            [
              71.87687,
              18.259513
            ],
            [
              71.966986,
              18.317384
            ],
            [
              71.978869,
              18.325526
            ],
            [
              71.98982,
              18.33474
            ],
            [
              71.999093,
              18.344399
            ],
            [
              72.006062,
              18.353844
            ],
            [
              72.010261,
              18.362432
            ],
            [
              72.011407,
              18.369577
            ],
            [
              72.00943,
              18.374792
            ],
            [
              72.004465,
              18.377721
            ],
            [
              71.996851,
              18.378167
            ],
            [
              71.987102,
              18.376098
            ],
            [
              71.975875,
              18.371655
            ],
            [
              71.963927,
              18.36514
            ],
            [
              71.955702,
              18.359911
            ],
            [
              71.947477,
              18.35468
            ],
            [
              71.939251,
              18.349446
            ],
            [
              71.931025,
              18.344211
            ],
            [
              71.922798,
              18.338973
            ],
            [
              71.914569,
              18.333733
            ],
            [
              71.906338,
              18.32849
            ],
            [
              71.898105,
              18.323245
            ],
            [
              71.832123,
              18.281205
            ],
            [
              71.820206,
              18.273006
            ],
            [
              71.809192,
              18.263728
            ],
            [
              71.799831,
              18.254002
            ],
            [
              71.792771,
              18.24449
            ],
            [
              71.788506,
              18.235831
            ],
            [
              71.787338,
              18.228618
            ]
          ]
        ]
      },
      "areaKm2": 119.47,
      "bounds": {
        "minLat": 18.219936,
        "maxLat": 18.378167,
        "minLon": 71.787338,
        "maxLon": 72.011407
      },
      "confidence": 0.774,
      "spreadKm": 6.776,
      "vertexCount": 36,
      "method": "backward particle drift of the observed slick across the candidate release window; convex hull of particle snapshots",
      "notes": [
        "the origin is reported as a REGION, never a single point",
        "confidence reflects internal spread of this prototype model, not scientific accuracy"
      ]
    },
    "releaseWindow": {
      "start": "2026-03-13T10:00:00Z",
      "end": "2026-03-13T18:00:00Z",
      "durationHours": 8.0,
      "source": "candidate release window (case input prior)",
      "hoursBeforeObservation": {
        "start": 20.0,
        "end": 12.0
      },
      "note": "candidate-window prior supplied with the case; the region itself is reconstructed from the slick and the environmental field"
    },
    "observedAt": "2026-03-14T06:00:00Z",
    "drift": {
      "windageCoefficient": 0.03,
      "windageSource": "environmental field",
      "stepSeconds": 300.0,
      "sampleHours": 0.5,
      "regionBufferKm": 2.0,
      "integration": "backward Euler (dt < 0) of surface current + windage * wind",
      "parametersArePrototypeValues": true,
      "config": {
        "stepSeconds": 300.0,
        "sampleHours": 0.5,
        "windageOverride": null,
        "regionBufferKm": 2.0,
        "boundaryStride": 2,
        "confidenceSpreadReferenceKm": 30.0
      },
      "backdriftPath": [
        [
          18.466325,
          72.163105
        ],
        [
          18.46114,
          72.15481
        ],
        [
          18.455953,
          72.146523
        ],
        [
          18.450763,
          72.138243
        ],
        [
          18.445571,
          72.129969
        ],
        [
          18.440377,
          72.121701
        ],
        [
          18.435181,
          72.113439
        ],
        [
          18.429983,
          72.105183
        ],
        [
          18.424782,
          72.096933
        ],
        [
          18.419579,
          72.088688
        ],
        [
          18.414373,
          72.080447
        ],
        [
          18.409166,
          72.072212
        ],
        [
          18.403956,
          72.063981
        ],
        [
          18.398744,
          72.055754
        ],
        [
          18.39353,
          72.047531
        ],
        [
          18.388313,
          72.039312
        ],
        [
          18.383094,
          72.031096
        ],
        [
          18.377873,
          72.022884
        ],
        [
          18.37265,
          72.014675
        ],
        [
          18.367424,
          72.006468
        ],
        [
          18.362196,
          71.998263
        ],
        [
          18.356966,
          71.990061
        ],
        [
          18.351734,
          71.981858
        ],
        [
          18.346499,
          71.973656
        ],
        [
          18.341262,
          71.965454
        ],
        [
          18.336023,
          71.957252
        ],
        [
          18.330781,
          71.949049
        ],
        [
          18.325537,
          71.940844
        ],
        [
          18.320291,
          71.932638
        ],
        [
          18.315043,
          71.92443
        ],
        [
          18.309792,
          71.916221
        ],
        [
          18.30454,
          71.908008
        ],
        [
          18.299284,
          71.899793
        ],
        [
          18.294027,
          71.891574
        ],
        [
          18.288767,
          71.883352
        ],
        [
          18.283505,
          71.875126
        ],
        [
          18.278241,
          71.866895
        ],
        [
          18.272974,
          71.85866
        ],
        [
          18.267706,
          71.85042
        ],
        [
          18.262435,
          71.842175
        ],
        [
          18.257161,
          71.833923
        ]
      ],
      "field": {
        "provider": "DemoEnvironmentalProvider",
        "synthetic": true,
        "datasetLabel": "Synthetic Demonstration Dataset",
        "timeBehaviour": "steady (prototype simplification: no temporal variation in this demo field)",
        "windageCoefficient": 0.03
      }
    },
    "seedCount": 25,
    "sampleCount": 425,
    "notes": [
      "particles are the observed slick integrated backwards across the candidate release window; the region is their convex hull",
      "prototype drift model - not a validated ocean model (docs/methodology.md)",
      "candidate window provenance: candidate release window (case input prior)"
    ],
    "warnings": []
  },
  "warnings": [
    "AIS: Synthetic Demonstration Dataset - synthetic AIS is demonstration data and is never presented as real-world evidence",
    "9 row(s) were rejected during cleaning and are listed in rejected[] with reasons - nothing was dropped silently",
    "1 individual value(s) were removed from 1 kept row(s); see removedValues[]",
    "synthetic demonstration data (DEMO DATA) - not a real incident"
  ],
  "notes": [
    "inputs: cleaned AIS + case JSON + slick polygon + environmental field; scenario answer keys are never read by this pipeline",
    "every factor is reported with its reason, including factors that scored 0",
    "equal totals are shown as tie groups - the evidence, not the identifier, is the result"
  ],
  "limitations": [
    "prototype drift model: forward-Euler integration of a steady demo field, not a validated ocean model (docs/methodology.md)",
    "the windage coefficient is a prototype value, configurable, not scientifically calibrated",
    "the release window is a candidate-window prior supplied with the case; the origin REGION is what the product reconstructs from slick + environmental data",
    "thresholds (falloff distance, feasibility margin, anomaly references) are prototype choices reported in the output - they are not physical constants",
    "AIS coverage is uneven by nature: a gap is ambiguous and never, on its own, evidence against a vessel",
    "the origin is a REGION with uncertainty - ABYSS never publishes a single-point origin and never a probability of guilt",
    "candidate ranking orders evidence for investigation support; it does not establish legal responsibility",
    "this dataset is synthetic demonstration data and describes no real vessel, voyage, spill or incident"
  ],
  "disclaimer": "ABYSS provides analytical evidence for investigation support. Candidate ranking does not establish legal responsibility. This dataset is synthetic: it does not describe any real vessel, voyage, spill or incident, and nothing in it asserts that any vessel caused an oil spill."
}
