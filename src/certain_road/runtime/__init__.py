"""On-device composition root.

Wires perception, driving and the CAN transport into the loop that actually runs
on the Jetson. Like `cli.py` and `sim/`, this package composes other packages —
so it may import them, and nothing may import it.
"""
