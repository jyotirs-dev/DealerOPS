"""
orchestration – Pipeline wiring
================================
The orchestration layer is deliberately *thin*.  It calls each module
in sequence (extract → match → assign → write plan) and aggregates
the results.  No business logic should be added here — if a decision
is domain-specific, it belongs in ``domain/`` or ``validation/``.
"""
