# `make check` runs every check CI runs; the steps are in scripts/check_repo.py.
.PHONY: check
check:
	uv run python scripts/check_repo.py
