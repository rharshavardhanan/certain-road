"""The texture rebuild reads docs/texture-provenance.md's file map completely (D094)."""

import sys

from certain_road.core.paths import repo_root

sys.path.insert(0, str(repo_root() / "scripts"))

from fetch_trial_textures import parse  # noqa: E402

ROWS = [
    r
    for ln in (repo_root() / "docs" / "texture-provenance.md").read_text().splitlines()
    if (r := parse(ln))
]


def test_every_texture_is_mapped():
    """All 49 (D086), including the last line, which ends in a code fence."""
    assert len(ROWS) == 49
    assert len({r[0] for r in ROWS}) == 49


def test_a_doi_slash_does_not_split_the_source():
    out, src, part, orig, w, h = ROWS[0]
    assert (out, src, part, orig, w, h) == (
        "1_potholes_india_pune/potholes_01.jpg",
        "QR4Change",
        None,
        "Img (1001).jpg",
        2250,
        3000,
    )


def test_bd_n6_rows_name_their_zenodo_part():
    parts = {r[2] for r in ROWS if r[1] == "BD-N6"}
    assert parts == {"Part1", "Part2"}
    assert all(r[2] is None for r in ROWS if r[1] == "QR4Change")
