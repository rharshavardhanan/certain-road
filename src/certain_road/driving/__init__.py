"""Drive pipeline: what should the robot do right now?

Holds corridor.py (in-path, proximity, urgency, lateral offset). Will also
hold confirm.py (N-of-M temporal confirmation), decision.py (state machine +
confidence gate), controller.py (state -> Command).
"""
