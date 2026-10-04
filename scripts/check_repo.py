"""Every repository check, in order: `uv run python scripts/check_repo.py` (or `make check`).

One summary line per step; exits non-zero if any step fails. CI runs exactly this.

1. ruff check            lint, over the Python files git tracks
2. ruff format --check   formatting, over the same files
3. import-linter         the stage-isolation contracts
4. pytest                the full suite
5. repo map              regenerates docs/REPO-MAP.md, reusing steps 3 and 4. It reports
                         and never fails: the map inventories git history, so any new
                         commit changes it, and it is rewritten only when it changed.
6. freshness             each generated file must equal a fresh in-memory rebuild apart
                         from its stamp line (configs/repo_map.yaml). Modification times
                         are not used, because a clone resets them. A difference confined
                         to a section the config excepts is reported, not failed (C5).

Ruff judges only what git tracks, so a working copy and a fresh clone are checked on the
same code. Untracked Python files (another session's work in progress) are counted in
the summary line, not checked.
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repo_map  # noqa: E402


def run(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def last_line(proc: subprocess.CompletedProcess) -> str:
    lines = [ln.strip() for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def freshness() -> tuple[bool, str]:
    ok, notes = True, []
    for entry in repo_map.CFG["generated"]:
        f = repo_map.freshness(entry)
        if f["missing"]:
            ok = False
            notes.append(f"{entry['path']} missing")
        elif f["outside"]:
            ok = False
            notes.append(f"{entry['path']} stale, first difference: {f['outside'][0][:80]}")
        elif f["changed"]:
            notes.append(f"{entry['path']} differs only in excepted sections ({entry['reason']})")
        else:
            notes.append(f"{entry['path']} fresh")
    return ok, "; ".join(notes)


def main() -> int:
    tracked = run("git", "ls-files", "*.py").stdout.split()
    untracked = run("git", "ls-files", "--others", "--exclude-standard", "*.py").stdout.split()
    ruff = (sys.executable, "-m", "ruff")
    runs: dict[str, subprocess.CompletedProcess] = {}
    passed: list[bool] = []

    def step(name: str, check) -> None:
        start = time.monotonic()
        ok, summary = check()
        passed.append(ok)
        took = time.monotonic() - start
        print(f"{name:<20} {'ok  ' if ok else 'FAIL'}  {summary}  ({took:.0f} s)", flush=True)

    def tool(name: str, *cmd: str):
        def check() -> tuple[bool, str]:
            runs[name] = run(*cmd)
            return runs[name].returncode == 0, last_line(runs[name])

        return check

    note = f" ({len(untracked)} untracked not checked)" if untracked else ""
    step("ruff check", tool("ruff check", *ruff, "check", *tracked))
    print(f"{'':<26}{len(tracked)} tracked Python files{note}")
    step("ruff format --check", tool("ruff format", *ruff, "format", "--check", *tracked))
    step("import-linter", tool("lint-imports", str(Path(sys.executable).parent / "lint-imports")))
    step("pytest", tool("pytest", sys.executable, "-m", "pytest"))
    step("repo map", lambda: (True, map_summary(repo_map.write_map(runs))))
    step("freshness", freshness)

    print(f"{sum(passed)} of {len(passed)} steps passed")
    return 0 if all(passed) else 1


def map_summary(changed: int) -> str:
    out = repo_map.CFG["output"]
    if not changed:
        return f"{out} unchanged"
    return f"{out} rewritten, {changed} lines changed: review and commit it"


if __name__ == "__main__":
    raise SystemExit(main())
