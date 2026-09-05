"""Control transport. Holds protocol.py (Command <-> bytes, provisional wire
format). Will also hold transport.py (Serial / CAN / Null / Sim).

Named `canbus`, not `can`, because `python-can` owns the top-level `can`
module.
"""
