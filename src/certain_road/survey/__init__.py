"""Survey pipeline: what do we know about this road?

segment.py groups a drive into segments, scoring.py turns detections into a
vision-estimated PCI, rsl.py gives that a remaining service life from a cited
deterioration curve (D018), and allocation.py chooses repairs under a budget.
"""
