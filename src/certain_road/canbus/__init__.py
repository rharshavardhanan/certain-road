"""Control transport. Will hold protocol.py (Command <-> bytes) and
transport.py (Serial / CAN / Null / Sim).

Named `canbus`, not `can`, because `python-can` owns the top-level `can`
module.
"""
