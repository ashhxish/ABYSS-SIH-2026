"""ABYSS intelligence service - analysis package.

Modules are added phase by phase (see docs/architecture.md):

    app.config      environment-driven configuration with startup validation
    app.geo         geodesy helpers shared by the analysis modules
    app.ais         AIS ingestion, cleaning, trajectories, filtering, gaps
    app.hindcast    backward particle drift / origin reconstruction
    app.detection   satellite observation and oil-slick characterisation
    app.behaviour   behavioural baseline and anomaly analysis
    app.scoring     explainable evidence scoring
    app.schemas     request/response models (the service contract)

Design boundaries: this package performs ANALYSIS ONLY. It does not persist
state, does not talk to the database, and never decides that a vessel caused a
spill - it produces evidence and compatibility scores for investigation support.
"""

__all__ = ["config", "geo"]
