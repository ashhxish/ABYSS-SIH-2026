"""ABYSS - AIS module.

Phase 3:  cleaning.py        - ingestion, normalisation, validation, audit trail
Phase 4:  trajectory.py      - ordered tracks, gaps, stops, course changes
Phases 5-7: filtering.py     - spatial, temporal and trajectory compatibility
Phase 9:  gap_analysis.py    - AIS gap feasibility and relevance (facts + judgements)
Phase 10: scoring (app.scoring) consumes these assessments.
"""

__all__ = ["cleaning", "trajectory", "filtering", "gap_analysis"]
