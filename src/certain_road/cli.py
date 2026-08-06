"""Single entrypoint. One sub-app per pipeline stage.

Stages are wired here and nowhere else; this module is the only place allowed
to know about more than one stage at a time.
"""

import typer

app = typer.Typer(
    name="certain-road",
    help="Road segment repair prioritisation under budget constraint.",
    no_args_is_help=True,
    add_completion=False,
)

STAGE_HELP = {
    "ingest": "Video/camera + track -> frames.parquet",
    "detect": "YOLOv8n training and inference",
    "assess": "Detections -> vision-estimated PCI per segment",
    "calibrate": "Fit or apply conformal intervals on segment vision-estimated PCI",
    "rsl": "Vision-estimated PCI interval -> remaining service life interval",
    "optimize": "Budget-constrained repair selection",
    "report": "Self-contained offline HTML report",
}

# Keep references so later tasks attach commands to the right stage rather than
# inventing parallel top-level apps.
STAGE_APPS: dict[str, typer.Typer] = {}
for _name, _help in STAGE_HELP.items():
    _sub = typer.Typer(name=_name, help=_help, no_args_is_help=True)
    STAGE_APPS[_name] = _sub
    app.add_typer(_sub, name=_name)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
