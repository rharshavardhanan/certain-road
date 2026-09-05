from typer.testing import CliRunner

from certain_road.cli import app

runner = CliRunner()

STAGES = ["perception", "driving", "survey", "dashboard", "sim"]


def test_help_lists_every_stage():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for stage in STAGES:
        assert stage in result.stdout, f"{stage} missing from --help"
