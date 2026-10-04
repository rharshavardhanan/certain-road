"""Generate docs/REPO-MAP.md: what exists, when it was built, and what is left.

Never hand-edit the output; rerun this script. Every number, date and status in the
document is read at build time from the filesystem, git, docstrings,
`docs/DECISIONS.md` and `results/`. Where the evidence is absent the document says
so instead of guessing.

Five sections (pipeline, entry points, task status, what is left, how to reproduce)
stand on one table: what each script reads and writes, recovered from its source by
`script_io`. It follows `root / "results" / "T12"` joins, path variables and
f-strings (which become globs). It parses literals; it does not trace execution, so
a path assembled at run time from arguments or data is invisible to it.

Tunables live in `configs/repo_map.yaml`.
"""

import ast
import difflib
import glob
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from enum import StrEnum
from fnmatch import fnmatch
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "configs" / "repo_map.yaml").read_text())
NO_DOC = "no docstring"
WRITE_HINTS = ("write", "save", "dump", "export", "mkdir", "touch", "imwrite")
ROOT_NAMES = {"root", "repo", "repo_root", "root_dir", "project_root"}
PASS_THROUGH = {"str", "Path", "fspath", "resolve", "absolute", "expanduser", "as_posix"}
SCOPES = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
PATH_RE = re.compile(r"^[\w.*-]+(/[\w.*-]+)+/?$")
SOURCE_RE = re.compile(r"`([^`]+)`|<code>([^<]+)</code>")
TASK_RE = re.compile(r"\bT(\d+)[ab]?\b")
DEC_RE = re.compile(r"\bD\d{3}\b")
DATA_URI_RE = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")
PROJECT_CFG = yaml.safe_load((ROOT / "configs" / "project.yaml").read_text())
PATH_HELPERS: dict[str, str] = {}  # raw_dir() -> data/raw, filled from core/paths.py below


class Status(StrEnum):
    DONE = "done"
    PARTIAL = "partial"
    NOT_RUN = "not run"
    UNKNOWN = "unknown"


# --- extraction: pure functions, pinned by tests/test_repo_map.py -------------------


def first_sentence(doc: str | None) -> str:
    if not doc or not doc.strip():
        return NO_DOC
    para = " ".join(doc.strip().split("\n\n")[0].split())
    m = re.match(r"(.+?[.?!])(?=\s|$)", para)
    return m.group(1) if m else para


def derive_status(present: dict[str, bool]) -> Status:
    if not present:
        return Status.UNKNOWN
    found = sum(present.values())
    if found == len(present):
        return Status.DONE
    return Status.PARTIAL if found else Status.NOT_RUN


def decision_gaps(
    cited: dict[str, list[str]], defined_now: set[str], defined_at_head: set[str]
) -> tuple[dict[str, list[str]], list[str]]:
    absent = {d: files for d, files in sorted(cited.items()) if d not in defined_now}
    return absent, sorted(defined_now - defined_at_head)


def sources_in(text: str) -> list[str]:
    found = set()
    for line in text.splitlines():
        if "Source:" in line:
            for a, b in SOURCE_RE.findall(line.split("Source:", 1)[1]):
                found.add(a or b)
    return sorted(found)


def config_value(key: str) -> object:
    value: object = PROJECT_CFG
    for k in key.split("."):
        value = value.get(k) if isinstance(value, dict) else None
    return value


def _config_subscript(node: ast.AST) -> str | None:
    """The configs/project.yaml string a CFG["a"]["b"] subscript evaluates to."""
    names = []
    while isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        names.insert(0, str(node.slice.value))
        node = node.value
    value = config_value(".".join(names)) if names and _is_config(node) else None
    return value if isinstance(value, str) else None


def stale_lines(committed: str, rebuilt: str, stamp: str) -> list[str]:
    """Lines a fresh build would change, as -old/+new, with the stamp line set aside."""

    def keep(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if not re.search(stamp, ln)]

    diff = difflib.unified_diff(keep(committed), keep(rebuilt), lineterm="", n=0)
    return [ln for ln in diff if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]


def drop_sections(text: str, headings: list[str]) -> str:
    """The text without each '## ' section whose heading starts with one of `headings`."""
    kept, dropping = [], False
    for ln in text.splitlines():
        if ln.startswith("## "):
            dropping = any(ln.startswith(h) for h in headings)
        if not dropping:
            kept.append(ln)
    return "\n".join(kept)


def _part(node: ast.AST, env: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Subscript):
        return _config_subscript(node)
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "*" for v in node.values)
    if isinstance(node, ast.Name) and env.get(node.id):
        return env[node.id]
    return None


def _is_root(node: ast.AST) -> bool:
    if "__file__" in ast.unparse(node):
        return True
    if isinstance(node, ast.Call):
        return _call_name(node).lower() in ROOT_NAMES
    name = getattr(node, "id", None) or getattr(node, "attr", "")
    return name.lower() in ROOT_NAMES


def _resolve(node: ast.AST, env: dict[str, str], roots: list[str]) -> str | None:
    """'' for the repository root, a relative path under it, or None."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        base = _resolve(node.left, env, roots)
        if base is None:
            return None
        part = _part(node.right, env) or "*"
        return f"{base}/{part}".strip("/") if base else part.strip("/")
    if isinstance(node, ast.IfExp | ast.BoolOp):
        options = [node.body, node.orelse] if isinstance(node, ast.IfExp) else node.values
        return next((p for o in options if (p := _resolve(o, env, roots))), None)
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.Call) and _call_name(node) in PASS_THROUGH and node.args:
        return _resolve(node.args[0], env, roots)
    if isinstance(node, ast.Call) and _call_name(node) in PATH_HELPERS:
        return PATH_HELPERS[_call_name(node)]
    if isinstance(node, ast.Subscript) and (value := _config_subscript(node)):
        return value if value.split("/")[0] in roots else None
    if isinstance(node, ast.Constant | ast.JoinedStr):
        s = _part(node, {})
        ok = s and PATH_RE.match(s) and s.split("/")[0] in roots
        return s.rstrip("/") if ok else None
    if isinstance(node, ast.Name | ast.Call | ast.Attribute | ast.Subscript) and _is_root(node):
        return ""
    return None


def _call_name(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _mode_writes(mode: ast.AST | None) -> bool:
    return isinstance(mode, ast.Constant) and any(c in str(mode.value) for c in "wax")


def _writes_by_name(name: str) -> bool:
    low = name.lower()
    return low.startswith("to_") or any(h in low for h in WRITE_HINTS)


def _is_write(node: ast.AST, parents: dict) -> bool:
    while True:  # str(p), Path(p) and p.resolve() pass the path through unchanged
        parent = parents.get(node)
        if isinstance(parent, ast.Call) and _call_name(parent) in PASS_THROUGH:
            node = parent
        elif isinstance(parent, ast.Attribute) and parent.attr in PASS_THROUGH:
            node = parents.get(parent)
        else:
            break
    if isinstance(parent, ast.Attribute) and parent.value is node:
        call = parents.get(parent)
        if not (isinstance(call, ast.Call) and call.func is parent):
            return False
        if parent.attr == "open":
            return _mode_writes(call.args[0] if call.args else _kw(call, "mode"))
        return _writes_by_name(parent.attr)
    call = parents.get(parent) if isinstance(parent, ast.keyword) else parent
    if not isinstance(call, ast.Call):
        return False
    name = _call_name(call)
    if name == "add_argument":
        flags = [a.value for a in call.args if isinstance(a, ast.Constant)]
        return any("out" in str(f) for f in flags)
    if name == "open":
        return _mode_writes(call.args[1] if len(call.args) > 1 else _kw(call, "mode"))
    if "copy" in name.lower():
        return any(a is node for a in call.args[1:])
    return _writes_by_name(name)


def _is_config(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        return _call_name(node) in ("safe_load", "load")
    name = getattr(node, "id", None) or getattr(node, "attr", "")
    return any(k in name.lower() for k in ("cfg", "config"))


def _config_keys(tree: ast.AST, parents: dict) -> list[str]:
    keys = set()
    for node in ast.walk(tree):
        outer = parents.get(node)
        if not isinstance(node, ast.Subscript) or (
            isinstance(outer, ast.Subscript) and outer.value is node
        ):
            continue
        levels, cur = [], node
        while isinstance(cur, ast.Subscript):
            levels.append(cur.slice)
            cur = cur.value
        names = []
        for s in reversed(levels):
            if not (isinstance(s, ast.Constant) and isinstance(s.value, str)):
                break
            names.append(s.value)
        if names and _is_config(cur):
            keys.add(".".join(names))
    return sorted(k for k in keys if not any(o.startswith(k + ".") for o in keys))


def _cli_args(tree: ast.AST) -> list[dict]:
    calls = [
        n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) == "add_argument"
    ]
    out = []
    for call in sorted(calls, key=lambda c: (c.lineno, c.col_offset)):
        flags = [a.value for a in call.args if isinstance(a, ast.Constant)]
        if not flags:
            continue
        name = next((f for f in flags if str(f).startswith("--")), flags[0])
        req, nargs, default = (_kw(call, k) for k in ("required", "nargs", "default"))
        positional = not str(name).startswith("-")
        optional_nargs = isinstance(nargs, ast.Constant) and nargs.value in ("?", "*")
        required = (isinstance(req, ast.Constant) and req.value is True) or (
            positional and not optional_nargs
        )
        choices = _kw(call, "choices")
        out.append(
            {
                "name": name,
                "required": required,
                "default": ast.unparse(default) if default is not None else None,
                "choices": ast.unparse(choices) if choices is not None else None,
            }
        )
    return out


def _walk_scope(node: ast.AST):
    """Like ast.walk, without entering nested functions or classes."""
    yield node
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, SCOPES):
            yield from _walk_scope(child)


def _scope_env(scope: ast.AST, base: dict[str, str], roots: list[str]) -> dict[str, str]:
    """Path variables of one module or function body, on top of the module's."""
    env = dict(base)
    kinds = ast.Assign | ast.AnnAssign
    assigns = [n for s in scope.body for n in _walk_scope(s) if isinstance(n, kinds)]
    for node in sorted(assigns, key=lambda n: n.lineno):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = _resolve(node.value, env, roots) if node.value is not None else None
        for t in targets:
            if isinstance(t, ast.Name) and value is not None:
                env[t.id] = value
    return env


def script_io(source: str, roots: list[str] | None = None) -> dict:
    """Reads, writes, config keys and CLI arguments, parsed from a script's source."""
    roots = roots or CFG["path_roots"]
    tree = ast.parse(source)
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    module_env = _scope_env(tree, {}, roots)
    found: list[tuple[str, bool]] = []

    def visit(node: ast.AST, env: dict[str, str]) -> None:
        if isinstance(node, SCOPES):
            return
        path = _resolve(node, env, roots) if isinstance(node, ast.expr) else None
        if path is not None:
            parent = parents.get(node)
            is_definition = isinstance(parent, ast.Assign | ast.AnnAssign) and parent.value is node
            if path and path.split("/")[0] in roots and not is_definition:
                found.append((path, _is_write(node, parents)))
            return
        for child in ast.iter_child_nodes(node):
            visit(child, env)

    for scope in [tree, *(n for n in ast.walk(tree) if isinstance(n, SCOPES))]:
        env = module_env if scope is tree else _scope_env(scope, module_env, roots)
        for stmt in scope.body:
            visit(stmt, env)
    written = sorted({p for p, w in found if w})
    every = written + [p for p, w in found if not w]

    def is_base(p: str, others: list[str]) -> bool:
        return any(o != p and o.startswith(p + "/") for o in others)

    return {
        "writes": [p for p in written if not is_base(p, written)],
        "reads": sorted(
            {p for p, w in found if not w and p not in written and not is_base(p, every)}
        ),
        "config_keys": _config_keys(tree, parents),
        "args": _cli_args(tree),
    }


def _load_path_helpers() -> None:
    """raw_dir() and friends, from the single return each makes in core/paths.py."""
    tree = ast.parse((ROOT / "src/certain_road/core/paths.py").read_text())
    functions = [f for f in tree.body if isinstance(f, ast.FunctionDef)]
    for _ in functions:  # helpers call each other; repeat until every chain resolves
        for fn in functions:
            ret = next((s.value for s in fn.body if isinstance(s, ast.Return)), None)
            path = _resolve(ret, {}, CFG["path_roots"]) if ret is not None else None
            if path:
                PATH_HELPERS[fn.name] = path


_load_path_helpers()


# --- evidence gathering ----------------------------------------------------------


def sh(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def text_of(path: Path) -> str | None:
    try:
        return path.read_text()
    except (UnicodeDecodeError, OSError):
        return None


def expand(pattern: str) -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(ROOT / pattern)))


def newest_mtime(paths: list[Path]) -> float | None:
    times = []
    for p in paths:
        if p.is_dir():
            times += [f.stat().st_mtime for f in p.rglob("*") if f.is_file()]
        elif p.exists():
            times.append(p.stat().st_mtime)
    return max(times) if times else None


def stamp(t: float | None) -> str:
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else Status.UNKNOWN


def matches(path: str, pattern: str) -> bool:
    """True when one path names or contains the other; a glob never crosses a '/'."""
    a, b = path.split("/"), pattern.split("/")
    if len(a) != len(b) and Path(min(a, b, key=len)[-1]).suffix:
        return False  # the shorter one ends in a file name, and a file contains nothing
    return all(fnmatch(x, y) or fnmatch(y, x) for x, y in zip(a, b, strict=False))


def rebuild(script: str) -> str:
    """A generated file's content, built in memory by the same function its script calls."""
    blank = {"utc": "", "commit": ""}  # the stamp line is set aside by the comparison
    for p in (ROOT / "scripts", ROOT / "src"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    if script == "make_report.py":
        from make_report import build_report

        return build_report(ROOT, blank)
    if script == "build_dashboard.py":  # with the arguments build_dashboard.main passes
        from certain_road.dashboard.render import build_page

        return build_page(ROOT, blank, worst_k=int(config_value("allocation.worst_k")))
    raise KeyError(f"no in-memory builder for {script}")


def freshness(entry: dict) -> dict:
    """How a generated file differs from a fresh rebuild, in all and outside excepted sections."""
    path = ROOT / entry["path"]
    if not path.exists():
        return {"missing": True, "changed": [], "outside": []}
    committed, rebuilt = path.read_text(), rebuild(entry["script"])
    changed = stale_lines(committed, rebuilt, entry["stamp"])
    excepted = entry.get("except_sections", [])
    outside = (
        stale_lines(drop_sections(committed, excepted), drop_sections(rebuilt, excepted),
                    entry["stamp"])
        if changed else []
    )  # fmt: skip
    return {"missing": False, "changed": changed, "outside": outside}


def links(a: str, b: str) -> bool:
    """matches(), restricted to paths specific enough to say which script produced what."""
    n = CFG["link_fixed_segments"]
    fixed = all(not set("*?[") & set(seg) for p in (a, b) for seg in p.split("/")[:n])
    return fixed and matches(a, b)


def history() -> list[dict]:
    raw = sh("git", "log", "--reverse", "--name-only", "--format=%x1e%h%x1f%cs%x1f%s%x1f%B%x1f")
    commits = []
    for chunk in raw.stdout.split("\x1e")[1:]:
        h, date, subject, message, files = chunk.split("\x1f")
        commits.append(
            {"hash": h, "date": date, "subject": subject, "message": message,
             "files": [f for f in files.splitlines() if f]}
        )  # fmt: skip
    return commits


def decision_index(text: str) -> dict[str, tuple[str, str]]:
    rows = re.findall(r"^\| (D\d{3}) \| (.*) \| (.*?) \|$", text, re.M)
    return {d: (title, status) for d, title, status in rows}


def decision_headers(text: str) -> set[str]:
    return set(re.findall(r"^## (D\d{3})\b", text, re.M))


def introducing_commits() -> dict[str, str]:
    raw = sh(
        "git", "log", "--reverse", "--follow", "-p", "-U0", "--format=%x1e%h %cs",
        "--", "docs/DECISIONS.md",
    ).stdout  # fmt: skip
    first: dict[str, str] = {}
    for chunk in raw.split("\x1e")[1:]:
        head = chunk.split("\n", 1)[0]
        for d in re.findall(r"^\+## (D\d{3})\b", chunk, re.M):
            first.setdefault(d, head)
    return first


def module_name(f: str) -> str:
    return f.removeprefix("src/").removesuffix(".py").replace("/", ".").removesuffix(".__init__")


def symbol_doc(node: ast.AST) -> str:
    doc = ast.get_docstring(node)
    return doc.strip().splitlines()[0] if doc else NO_DOC


def signature(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{node.name}({ast.unparse(node.args)}){ret}"


def public_symbols(tree: ast.Module) -> list[ast.AST]:
    kinds = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    return [n for n in tree.body if isinstance(n, kinds) and not n.name.startswith("_")]


def resolve_from(node: ast.ImportFrom, own: str | None, is_pkg: bool) -> str | None:
    if not node.level:
        return node.module
    if own is None:
        return None
    parts = own.split(".") if is_pkg else own.split(".")[:-1]
    parts = parts[: len(parts) - (node.level - 1)]
    return ".".join(parts + ([node.module] if node.module else []))


def certain_road_uses(f: str, tree: ast.AST, modules: set[str]) -> set[tuple[str, str]]:
    """(module, symbol) pairs a file uses from certain_road; symbol '' means the module."""
    own = module_name(f) if f.startswith("src/") else None
    uses, aliases = set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = resolve_from(node, own, f.endswith("__init__.py"))
            if not base or not base.startswith("certain_road"):
                continue
            uses.add((base, ""))
            for a in node.names:
                sub = f"{base}.{a.name}"
                if sub in modules:
                    aliases[a.asname or a.name] = sub
                    uses.add((sub, ""))
                else:
                    uses.add((base, a.name))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name in modules:
                    aliases[a.asname or a.name] = a.name
                    uses.add((a.name, ""))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and getattr(node.value, "id", None) in aliases:
            uses.add((aliases[node.value.id], node.attr))
    return uses


def code_tokens(tree: ast.Module) -> set[str]:
    """Imported modules, identifiers and whole string constants: what code names, not prose."""
    tokens = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            tokens |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            tokens.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            tokens.add(node.value)
    return {t.lower() for t in tokens}


def purpose(path: Path) -> str:
    text = text_of(path)
    if text is None:
        return NO_DOC
    if path.suffix == ".py":
        try:
            return first_sentence(ast.get_docstring(ast.parse(text)))
        except SyntaxError:
            return NO_DOC
    if path.suffix == ".md":
        return next(
            (ln.lstrip("#").strip() for ln in text.splitlines() if ln.startswith("#")), NO_DOC
        )
    comments = []
    for ln in text.splitlines():
        if ln.startswith("#"):
            comments.append(ln.lstrip("#").strip())
        elif comments or ln.strip():
            break
    return first_sentence(" ".join(comments)) if comments else NO_DOC


def line_count(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return Status.UNKNOWN
    if b"\0" in data[:8192]:
        return "binary"
    try:
        return str(len(data.decode().splitlines()))
    except UnicodeDecodeError:
        return "binary"


class Repo:
    """Everything the sections need, gathered once."""

    def __init__(self) -> None:
        self.out = CFG["output"]
        listed = sh("git", "ls-files", "-co", "--exclude-standard").stdout.splitlines()
        self.files = sorted(f for f in set(listed) if f != self.out and (ROOT / f).is_file())
        porcelain = sh("git", "status", "--porcelain", "-uall").stdout.splitlines()
        self.dirty = {ln[3:]: ln[:2].strip() for ln in porcelain if ln[3:] != self.out}
        self.commits = history()
        self.first, self.last, self.first_seq = {}, {}, {}
        for seq, c in enumerate(self.commits):
            for f in c["files"]:
                self.first.setdefault(f, c["date"])
                self.first_seq.setdefault(f, seq)
                self.last[f] = c["date"]
        self.head = sh("git", "rev-parse", "--short", "HEAD").stdout.strip()
        self.branch = sh("git", "branch", "--show-current").stdout.strip()
        self.lane = CFG["read_only_lane"]

        counts = Counter(str(Path(f).parent) for f in self.files)
        documented = {str(Path(f).parent) for f in self.files
                      if Path(f).suffix in CFG["never_collapse"]}  # fmt: skip
        self.collapsed = {
            d for d, n in counts.items() if n > CFG["collapse_over_files"] and d not in documented
        }

        self.scripts = {}
        for f in self.files:
            if f.startswith("scripts/") and f.endswith(".py"):
                src = (ROOT / f).read_text()
                tree = ast.parse(src)
                doc = first_sentence(ast.get_docstring(tree))
                tag = re.match(r"(T\d+)[ab]?\b", doc)
                tokens = code_tokens(tree)
                needs = [k for k, words in CFG["external"].items() if tokens & set(words)]
                self.scripts[Path(f).name] = {
                    "path": f, "doc": doc, "tag": tag.group(1) if tag else None,
                    "needs": needs, **script_io(src),
                }  # fmt: skip

        for s in self.scripts.values():  # a generated file names what it read: trust it
            for g in (e["path"] for e in CFG["generated"]):
                if g in s["writes"] and (ROOT / g).exists():
                    named = sources_in((ROOT / g).read_text())
                    s["reads"] = sorted(set(s["reads"]) | set(named))

        self.decisions_text = (ROOT / "docs/DECISIONS.md").read_text()
        head_log = sh("git", "show", "HEAD:docs/DECISIONS.md").stdout
        self.index = decision_index(self.decisions_text)
        self.defined = decision_headers(self.decisions_text) | set(self.index)
        self.defined_head = decision_headers(head_log) | set(decision_index(head_log))
        self.cited: dict[str, list[str]] = defaultdict(list)
        for f in self.files:
            if f in CFG["citation_exclude"] or str(Path(f).parent) in self.collapsed:
                continue
            text = text_of(ROOT / f)
            text = DATA_URI_RE.sub("", text or "")  # base64 holds D-number lookalikes
            for d in sorted(set(DEC_RE.findall(text))):
                self.cited[d].append(f)

        self.task_log = (ROOT / "TASK_LOG.md").read_text()
        span = re.search(r"T(\d+)–T(\d+)", self.task_log)
        order_text = self.task_log.split("**Order:**", 1)[1].split("\n\n", 1)[0]
        order = re.findall(r"T\d+", order_text.split(". ", 1)[0])  # the order is one sentence
        tasks = [f"T{i}" for i in range(int(span.group(1)), int(span.group(2)) + 1)]
        for t in tasks:
            if t not in order:
                order.insert(order.index(f"T{int(t[1:]) - 1}") + 1, t)
        self.tasks = order

        results_md = text_of(ROOT / "results/RESULTS.md") or ""
        self.result_sections: list[tuple[str, list[str], list[str]]] = []
        for block in results_md.split("\n## ")[1:]:
            heading = block.split("\n", 1)[0]
            named = re.findall(r"(.+?)\s*\(([^)]*T\d+[^)]*)\)(?:,\s*)?", heading)
            self.result_sections.append((heading, named, sources_in(block)))

    def status_of(self, f: str) -> str:
        code = self.dirty.get(f) or next(
            (c for d, c in self.dirty.items() if d.endswith("/") and f.startswith(d)), ""
        )
        flags = {"M": "modified", "??": "untracked", "A": "added", "D": "deleted"}
        notes = [flags.get(code, code)] if code else []
        if any(f == p or (p.endswith("/") and f.startswith(p)) for p in self.lane):
            notes.append("read-only lane")
        return " · ".join(notes)


# --- sections ----------------------------------------------------------------------


def cell(x: object) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def table(question: str, header: list[str], rows: list[list]) -> list[str]:
    out = [question, "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return out + [""]


def code(paths: list[str]) -> str:
    return "<br>".join(f"`{p}`" for p in paths) if paths else "—"


def s1_what(r: Repo) -> list[str]:
    out = ["## 1. What this project is", ""]
    for q in CFG["quotes"]:
        text = text_of(ROOT / q["file"]) or ""
        if q["start"] not in text or q["stop"] not in text:
            out += [f"`{q['file']}`: quote markers not found ({Status.UNKNOWN}).", ""]
            continue
        block = text[text.index(q["start"]) : text.index(q["stop"])].strip()
        out += [f"Quoted from `{q['file']}`:", ""]
        out += [("> " + ln).rstrip() for ln in block.splitlines()] + [""]
    py = Counter(f.split("/")[0] for f in r.files if f.endswith(".py"))
    out += [
        f"Evidence at build time, beside the quotes' own status lines: {len(r.commits)} "
        f"commits from {r.commits[0]['date']} to {r.commits[-1]['date']}; Python files: "
        + ", ".join(f"{n} in `{d}/`" for d, n in sorted(py.items()))
        + ".",
        "",
    ]
    return out


def stage_edge(r: Repo, stages: list[dict], i: int) -> tuple[str, bool]:
    """The edge label, and whether a parsed path links the two stages."""
    a, b = stages[i], stages[i + 1]
    if a["scripts"] and set(a["scripts"]) == set(b["scripts"]):
        return "in-process: " + ", ".join(a["scripts"]), True
    reads = [p for s in b["scripts"] for p in r.scripts.get(s, {}).get("reads", [])]
    if not a["scripts"]:
        linked = [p for p in reads if any(matches(p, u) for u in a.get("source_under", []))]
        return "<br/>".join(sorted(set(linked))) or Status.UNKNOWN, bool(linked)
    writes = [p for s in a["scripts"] for p in r.scripts.get(s, {}).get("writes", [])]
    dirs = [str(Path(w).parent) for w in writes if Path(w).suffix]
    linked = [p for p in reads if any(links(p, w) for w in writes + dirs)]
    return "<br/>".join(sorted(set(linked or writes))) or Status.UNKNOWN, bool(linked)


def s2_pipeline(r: Repo) -> list[str]:
    stages = CFG["pipeline"]
    lines = ["flowchart TD"]
    for i, s in enumerate(stages):
        scripts = "<br/>".join(s["scripts"]) if s["scripts"] else "source data"
        lines.append(f'  s{i}["{s["stage"]}<br/><small>{scripts}</small>"]')
    for i in range(len(stages) - 1):
        label, linked = stage_edge(r, stages, i)
        lines.append(f'  s{i} {"-->" if linked else "-.->"}|"{label}"| s{i + 1}')
    last = stages[-1]["scripts"]
    outs = sorted({p for s in last for p in r.scripts.get(s, {}).get("writes", [])})
    lines.append(f'  s{len(stages) - 1} --> out["{"<br/>".join(outs) or Status.UNKNOWN}"]')
    return [
        "## 2. Pipeline",
        "",
        "Which artifact carries each stage to the next? A solid edge lists what the later "
        "stage's scripts read from what the earlier stage's scripts write (the same path, or "
        "inside a directory it writes into), parsed from their source; "
        "`configs/repo_map.yaml` names the scripts per stage. A dotted edge means no parsed "
        "path links the two (for example, weights passed as a CLI argument); it lists what "
        "the earlier stage writes.",
        "",
        "```mermaid",
        *lines,
        "```",
        "",
    ]


def s3_directories(r: Repo) -> list[str]:
    out = ["## 3. Directory map", ""]
    areas = CFG["areas"]
    groups: dict[str, list[str]] = defaultdict(list)
    for f in r.files:
        top = f.split("/")[0]
        groups[top if "/" in f and top in areas else "(root and other)"].append(f)
    question = (
        "What is each file for, and when was it first and last committed? Purpose is the "
        "first sentence of a module docstring or a leading config comment, or a Markdown "
        "file's first heading. Directories holding more than "
        f"{CFG['collapse_over_files']} files directly are one row."
    )
    for area in [*areas, "(root and other)"]:
        if area == "data":
            out += [f"### `{area}/`", "", *untracked_dir(area)]
            continue
        rows, seen = [], set()
        for f in groups.get(area, []):
            parent = str(Path(f).parent)
            if parent in r.collapsed:
                if parent in seen:
                    continue
                seen.add(parent)
                members = [g for g in r.files if str(Path(g).parent) == parent]
                kinds = Counter(Path(g).suffix or "(none)" for g in members)
                dated = [r.first.get(g) for g in members if g in r.first]
                rows.append(
                    [f"`{parent}/`", f"{len(members)} files",
                     min(dated) if dated else "uncommitted",
                     max(r.last[g] for g in members if g in r.last) if dated else "uncommitted",
                     ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())),
                     " · ".join(sorted({r.status_of(g) for g in members} - {""}))]
                )  # fmt: skip
                continue
            rows.append(
                [f"`{f}`", line_count(ROOT / f), r.first.get(f, "uncommitted"),
                 r.last.get(f, "uncommitted"), purpose(ROOT / f), r.status_of(f)]
            )  # fmt: skip
        header = ["Path", "Lines", "First commit", "Last commit", "Purpose", "Working tree"]
        title = f"`{area}/`" if area != "(root and other)" else "Repository root and other"
        out += [f"### {title}", "", *table(question, header, rows)]
    return out


def untracked_dir(area: str) -> list[str]:
    base = ROOT / area
    if not base.exists():
        return [f"`{area}/` is absent ({Status.UNKNOWN}).", ""]
    rows = []
    depth = CFG["untracked_depth"]
    for d in sorted(p for p in base.rglob("*") if p.is_dir()):
        if len(d.relative_to(base).parts) > depth:
            continue
        files = [f for f in d.rglob("*") if f.is_file()]
        size = sum(f.stat().st_size for f in files)
        rows.append([f"`{d.relative_to(ROOT)}/`", f"{len(files):,} files", f"{size:,} bytes"])
    q = (
        f"What does the gitignored `{area}/` hold? It is never committed, so it has no "
        f"commit dates or docstrings; listed by directory to depth {depth}."
    )
    return table(q, ["Directory", "Files", "Size"], rows)


def s4_modules(r: Repo) -> list[str]:
    src = [f for f in r.files if f.startswith("src/") and f.endswith(".py")]
    trees = {f: ast.parse((ROOT / f).read_text()) for f in src}
    modules = {module_name(f) for f in src}
    reexport: dict[tuple[str, str], tuple[str, str]] = {}
    for f, tree in trees.items():
        own = module_name(f)
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                base = resolve_from(node, own, f.endswith("__init__.py"))
                for a in node.names if base and base.startswith("certain_road") else []:
                    reexport[(own, a.asname or a.name)] = (base, a.name)
    users: dict[tuple[str, str], set[str]] = defaultdict(set)
    for f in r.files:
        if f.endswith(".py") and f.split("/")[0] in ("src", "scripts", "tests", "kaggle"):
            try:
                tree = trees.get(f) or ast.parse((ROOT / f).read_text())
            except SyntaxError:
                continue
            for mod, sym in certain_road_uses(f, tree, modules):
                seen = 0
                while (mod, sym) in reexport and seen < len(reexport):
                    mod, sym = reexport[(mod, sym)]
                    seen += 1
                users[(mod, sym)].add(f)
    out = [
        "## 4. Module reference",
        "",
        "Public means a top-level function or class whose name has no leading underscore. "
        "'Imported outside its package' counts files in other packages, `scripts/` and "
        "`kaggle/` (code) and `tests/` separately; none at all marks it possibly unused.",
        "",
    ]
    by_pkg: dict[str, list[str]] = defaultdict(list)
    for f in src:
        mod = module_name(f)
        by_pkg[mod if f.endswith("__init__.py") else mod.rsplit(".", 1)[0]].append(f)
    for pkg in sorted(by_pkg):
        pkg_dir = "src/" + pkg.replace(".", "/") + "/"
        rows = []
        for f in sorted(by_pkg[pkg]):
            mod, tree = module_name(f), trees[f]
            rows.append([f"`{mod}`", "(module)", "", first_sentence(ast.get_docstring(tree)), ""])
            for node in public_symbols(tree):
                who = {u for u in users[(mod, node.name)] if not u.startswith(pkg_dir)}
                tests = sorted(u for u in who if u.startswith("tests/"))
                code_users = sorted(who - set(tests))
                if not who:
                    used = "**possibly unused**"
                elif not code_users:
                    used = f"tests only ({len(tests)})"
                else:
                    used = f"{len(code_users)} code, {len(tests)} test files"
                rows.append(["", f"`{node.name}`", f"`{signature(node)}`", symbol_doc(node), used])
        q = f"What does `{pkg}` expose, and is anything outside the package using it?"
        header = ["Module", "Symbol", "Signature", "Docstring first line", "Imported outside"]
        out += [f"### `{pkg}`", "", *table(q, header, rows)]
    return out


def keys_with_values(keys: list[str]) -> str:
    """Config keys, each with its configs/project.yaml value when that is a string."""
    shown = []
    for k in keys:
        v = config_value(k)
        shown.append(f"`{k}` = `{v}`" if isinstance(v, str) else f"`{k}`")
    return "<br>".join(shown) or "—"


def s5_entry_points(r: Repo) -> list[str]:
    rows = []
    for name, s in sorted(r.scripts.items()):
        args = "<br>".join(
            f"`{a['name']}`" + (" (required)" if a["required"] else "")
            + (f" = {a['default']}" if a["default"] else "")
            + (f" ∈ {a['choices']}" if a["choices"] else "")
            for a in s["args"]
        ) or "none"  # fmt: skip
        outputs = [p for w in s["writes"] for p in expand(w)]
        last = stamp(newest_mtime(outputs)) if outputs else "outputs absent"
        rows.append(
            [f"`{name}`" + (" (read-only lane)" if r.status_of(s["path"]).endswith("lane") else ""),
             s["doc"], args, code(s["reads"]), code(s["writes"]),
             keys_with_values(s["config_keys"]), last]
        )  # fmt: skip
    q = (
        "What can be run, with which arguments, reading and writing what? Paths and config "
        "keys are parsed from literals (an f-string placeholder becomes `*`); 'last output' "
        "is the newest modification time among the outputs that exist."
    )
    header = ["Script", "Purpose", "CLI arguments", "Reads", "Writes", "Config keys", "Last output"]
    return ["## 5. Entry points", "", *table(q, header, rows)]


def task_names(r: Repo) -> dict[str, tuple[str, str]]:
    names: dict[str, tuple[str, str]] = {}
    for _, named, _ in r.result_sections:
        for text, inner in named:
            for t in re.findall(r"T\d+", inner):
                names.setdefault(t, (text.strip(" :,"), "RESULTS.md heading"))
    for s in sorted(r.scripts.values(), key=lambda s: s["path"]):
        if s["tag"] and "—" in s["doc"]:
            names.setdefault(s["tag"], (s["doc"].split("—", 1)[1].strip(), f"`{s['path']}`"))
    for c in r.commits:
        for t in {f"T{n}" for n in TASK_RE.findall(c["subject"])}:
            subject = re.sub(r"^[T\d/ab+ ]+:\s*", "", c["subject"])
            names.setdefault(t, (subject, f"commit {c['hash']}"))
    return names


def task_rows(r: Repo) -> list[dict]:
    names = task_names(r)
    claims = {}
    progress = r.task_log.split("## Progress", 1)[1].split("\n## ", 1)[0]
    for cells in re.findall(r"^\| (T[^|]+?) \| ([^|]*) \|", progress, re.M):
        ids = re.findall(r"\d+", cells[0])
        for n in range(int(ids[0]), int(ids[-1]) + 1):
            claims[f"T{n}"] = cells[1].replace("**", "").strip()
    rows = []
    for t in r.tasks:
        expected = set()
        scripts = sorted(n for n, s in r.scripts.items() if s["tag"] == t)
        for n in scripts:
            expected |= set(r.scripts[n]["writes"])
        expected |= {str(p.relative_to(ROOT)) for p in expand(f"results/{t}")}
        expected |= {str(p.relative_to(ROOT)) for p in expand(f"results/{t}_*")}
        for _, named, sources in r.result_sections:
            heading_tasks = {x for _, inner in named for x in re.findall(r"T\d+", inner)}
            for src in sources:
                in_path = {f"T{n}" for n in re.findall(r"(?<![\w])T(\d+)(?=[/_]|$)", src)}
                if t in in_path or (not in_path and heading_tasks == {t}):
                    expected.add(src)
        expected = {p for p in expected if not any(o.startswith(p + "/") for o in expected)}
        present = {p: bool(expand(p)) for p in sorted(expected)}
        commits = [c for c in r.commits if t in {f"T{n}" for n in TASK_RE.findall(c["subject"])}]
        rows.append(
            {"task": t, "name": names.get(t, (Status.UNKNOWN, "no source")),
             "status": derive_status(present), "present": present, "scripts": scripts,
             "commit": commits[-1] if commits else None, "claim": claims.get(t)}
        )  # fmt: skip
    return rows


def evidence(row: dict) -> str:
    if not row["present"]:
        where = f"commit {row['commit']['hash']} names it, but " if row["commit"] else ""
        return where + "no output path found in scripts' writes, results/, or RESULTS.md"
    parts = []
    for p, ok in row["present"].items():
        if not ok:
            parts.append(f"`{p}` missing")
            continue
        hits = expand(p)
        n = sum(1 for h in hits for f in (h.rglob("*") if h.is_dir() else [h]) if f.is_file())
        parts.append(f"`{p}` present ({n} file{'s' if n != 1 else ''})")
    return "; ".join(parts)


def s6_tasks(r: Repo, rows: list[dict]) -> list[str]:
    table_rows = [
        [row["task"], f"{row['name'][0]} <sub>({row['name'][1]})</sub>", f"**{row['status']}**",
         evidence(row), ", ".join(f"`{s}`" for s in row["scripts"]) or "—",
         f"`{row['commit']['hash']}` {row['commit']['date']}" if row["commit"] else "—",
         row["claim"] or "—"]
        for row in rows
    ]  # fmt: skip
    q = (
        "Where does each spec task stand, and what decided it? Expected outputs are the "
        "writes of scripts whose docstring opens with the task id, `results/Tn*` "
        "directories, and the sources RESULTS.md names under the task's heading. All "
        f"present: {Status.DONE}; some: {Status.PARTIAL}; none: {Status.NOT_RUN}; no "
        f"expected output found: {Status.UNKNOWN}. The commit is the last whose subject "
        "names the task. The last column is `TASK_LOG.md`'s own claim, frozen when that file "
        "was superseded (see its banner): shown for contrast, never used."
    )
    header = ["Task", "Name (source)", "Status", "Evidence", "Scripts", "Commit",
              "TASK_LOG.md says"]  # fmt: skip
    return ["## 6. Task status", "", *table(q, header, table_rows)]


def s7_timeline(r: Repo) -> list[str]:
    out = ["## 7. Timeline", ""]
    by_day: dict[str, list[dict]] = defaultdict(list)
    for c in r.commits:
        by_day[c["date"]].append(c)
    for day, commits in by_day.items():
        rows = []
        for c in commits:
            areas = Counter(f.split("/")[0] if "/" in f else "(root)" for f in c["files"])
            rows.append(
                [f"`{c['hash']}`", c["subject"],
                 ", ".join(sorted(set(re.findall(r"\bT\d+[ab]?\b", c["message"])))) or "—",
                 ", ".join(sorted(set(DEC_RE.findall(c["message"])))) or "—",
                 " · ".join(f"{a} {n}" for a, n in sorted(areas.items()))]
            )  # fmt: skip
        q = f"What was committed on {day}, naming which tasks and decisions?"
        header = ["Commit", "Subject", "Tasks", "Decisions", "Files touched (by area)"]
        out += [f"### {day}", "", *table(q, header, rows)]
    intro = introducing_commits()
    rows = []
    for d in sorted(r.defined | set(r.index)):
        title, status = r.index.get(d, (Status.UNKNOWN, Status.UNKNOWN))
        if d not in r.defined_head:
            introduced = "uncommitted"
        else:
            introduced = f"`{intro[d]}`" if d in intro else Status.UNKNOWN
        cites = r.cited.get(d, [])
        rows.append([d, title, status, introduced, ", ".join(f"`{f}`" for f in cites) or "—"])
    q = (
        "Where did each decision come from, and what cites it? Title and status are the "
        "index row in `docs/DECISIONS.md`; the commit is the first that added its `## Dnnn` "
        "heading; citing files exclude the log itself."
    )
    header = ["Decision", "Title", "Status", "Introduced by", "Cited by"]
    return [*out, "### Decisions", "", *table(q, header, rows)]


def sha_records() -> dict[str, list[tuple[str, str]]]:
    found: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def walk(o: object, src: str) -> None:
        if isinstance(o, dict):
            shas = [v for k, v in o.items() if str(k).endswith("sha256") and isinstance(v, str)]
            pts = [v for v in o.values() if isinstance(v, str) and v.endswith(".pt")]
            for p in pts:
                for s in shas:
                    found[p.removeprefix(str(ROOT) + "/")].append((s, src))
            for v in o.values():
                walk(v, src)
        elif isinstance(o, list):
            for v in o:
                walk(v, src)

    for f in sorted((ROOT / "results").rglob("*.json")):
        if len(f.relative_to(ROOT / "results").parts) <= 3:
            try:
                walk(json.loads(f.read_text()), str(f.relative_to(ROOT)))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return found


def s8_models(r: Repo) -> list[str]:
    d = CFG["decimals"]
    shas = sha_records()
    locked = {}
    for f in sorted((ROOT / "results/LOCKED").glob("*.json")):
        j = json.loads(f.read_text())
        locked.setdefault(j.get("weights"), []).append((str(f.relative_to(ROOT)), j))
    rows = []
    for pt in sorted((ROOT / "runs").rglob("*.pt")):
        p = str(pt.relative_to(ROOT))
        recorded = shas.get(p, [])
        sha = "<br>".join(f"`{s[:12]}…` ({src})" for s, src in recorded) or "none recorded"
        args_file = next((a for a in (pt.parent, pt.parent.parent) if (a / "args.yaml").exists()),
                         None)  # fmt: skip
        if args_file:
            args = yaml.safe_load((args_file / "args.yaml").read_text())
            train = " · ".join(f"{k}={args.get(k)}" for k in CFG["train_args"] if k in args)
        else:
            train = Status.UNKNOWN
        evals = []
        for src, j in locked.get(p, []):
            m = j["pycocotools_metrics"]
            evals.append(
                f"{j['set']}, {j['images']} images: mAP50 {m['map50']:.{d}f}, "
                f"mAP50-95 {m['map50_95']:.{d}f} ({src})"
            )
        rows.append([f"`{p}`", f"{pt.stat().st_size:,}", sha, train, "<br>".join(evals) or "—"])
    q = (
        "Which weights exist, how were they trained, and what did locked evaluation measure? "
        "A sha256 is shown only where a result file records it beside the path; mAP is "
        "pycocotools, from `results/LOCKED/*.json`."
    )
    out = ["## 8. Model and artifact registry", ""]
    out += table(q, ["Weights", "Bytes", "Recorded sha256", "Training args", "Locked eval"], rows)
    return out + deployed(r, locked)


def deployed(r: Repo, locked: dict) -> list[str]:
    text = r.decisions_text
    if "## D082 " not in text:
        return [f"Deployment per class: {Status.UNKNOWN} (D082 is not in docs/DECISIONS.md).", ""]
    section = text.split("## D082 ", 1)[1].split("\n## ", 1)[0]
    rules = re.findall(r"\*\*The (.+?) comes? from Model (\w)\.\*\*", section)
    classes = yaml.safe_load((ROOT / "configs/project.yaml").read_text())["classes"]
    by_model = {j["model"]: (w, src) for w, recs in locked.items() for src, j in recs}
    rows = []
    for name in classes.values():
        model = next((m for subject, m in rules if name in subject or
                      (name.endswith("crack") and "crack terms" in subject)), None)  # fmt: skip
        w, src = by_model.get(model, (None, None))
        rows.append(
            [f"`{name}`", f"Model {model}" if model else Status.UNKNOWN,
             f"`{w}` ({src})" if w else Status.UNKNOWN]
        )  # fmt: skip
    q = (
        "Which model is deployed for which class? Read from D082's rule in "
        "`docs/DECISIONS.md`; the weights are the ones that model was locked-evaluated with."
    )
    note = "D082 is in the working tree but not yet committed." if "D082" not in (
        r.defined_head) else "D082 is committed."  # fmt: skip
    return [*table(q, ["Class", "Model", "Weights"], rows), note, ""]


def s9_tests(r: Repo) -> list[str]:
    src_modules = {module_name(f): f for f in r.files if f.startswith("src/") and f.endswith(".py")}
    stems = {Path(s["path"]).stem: s["path"] for s in r.scripts.values()}
    tested, rows = set(), []
    for f in [f for f in r.files if f.startswith("tests/") and f.endswith(".py")]:
        tree = ast.parse((ROOT / f).read_text())
        mods = {m for m, _ in certain_road_uses(f, tree, set(src_modules)) if m in src_modules}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in stems:
                mods.add(stems[node.module])
        tested |= mods
        rows.append([f"`{f}`", ", ".join(f"`{m}`" for m in sorted(mods)) or "—"])
    untested = sorted(
        m for m, f in src_modules.items()
        if m not in tested and public_symbols(ast.parse((ROOT / f).read_text()))
    )  # fmt: skip
    run = sh(sys.executable, "-m", "pytest")
    summary = next(
        (ln for ln in reversed(run.stdout.splitlines()) if re.search(r"\d+ (passed|failed)", ln)),
        Status.UNKNOWN,
    )
    summary = re.sub(r"\s+in [\d.]+s.*$", "", summary.strip("= "))
    lint = sh(str(Path(sys.executable).parent / "lint-imports"))
    kept = re.search(r"Contracts: .*", lint.stdout)
    contracts = len(re.findall(r"^\[importlinter:contract:", (ROOT / ".importlinter").read_text(),
                               re.M))  # fmt: skip
    return [
        "## 9. Test coverage map",
        "",
        *table("Which modules does each test file import?", ["Test file", "Imports"], rows),
        *table(
            "Which `src/` modules with public symbols does no test import directly?",
            ["Module"],
            [[f"`{m}`"] for m in untested],
        ),
        f"pytest, run at build time: **{summary}** (exit {run.returncode}).",
        "",
        f"import-linter: {contracts} contracts in `.importlinter`; lint-imports reports "
        f"**{kept.group(0) if kept else Status.UNKNOWN}** (exit {lint.returncode}).",
        "",
    ]


def s10_left(r: Repo, rows: list[dict]) -> list[str]:
    blockers = defaultdict(list)
    section = r.task_log.split("## Blocked on the user", 1)[1].split("\n## ", 1)[0]
    for uid, need, blocks, state in re.findall(
        r"^\| (U\d+) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|", section, re.M
    ):
        for t in re.findall(r"T\d+", blocks):
            blockers[t].append(f"{uid}: {need.strip()} (TASK_LOG.md: {state.strip()})")
    left = [
        [row["task"], f"**{row['status']}**",
         code([p for p, ok in row["present"].items() if not ok]),
         "<br>".join(blockers.get(row["task"], [])) or Status.UNKNOWN]
        for row in rows if row["status"] in (Status.NOT_RUN, Status.PARTIAL)
    ]  # fmt: skip
    out = ["## 10. What is left", "", f"### a) Tasks {Status.NOT_RUN}", ""]
    out += table(
        "Which tasks have outputs missing, and what unblocks them? Unblockers are the "
        "'Blocked on the user' rows of `TASK_LOG.md` naming the task; that file is "
        "superseded, so these are its last record (see its banner).",
        ["Task", "Status", "Missing", "Unblocked by"],
        left,
    )
    absent, uncommitted = decision_gaps(dict(r.cited), r.defined, r.defined_head)
    out += ["### b) Open decisions", ""]
    out += table(
        "Which decisions are not plainly Accepted, by their index row?",
        ["Decision", "Title", "Status"],
        [[d, t, s] for d, (t, s) in sorted(r.index.items()) if s.strip() != "Accepted"],
    )
    out += table(
        "Which D-numbers are cited in the repo but absent from `docs/DECISIONS.md`?",
        ["Decision", "Cited by"],
        [[d, ", ".join(f"`{f}`" for f in fs)] for d, fs in absent.items()] or [["none", "—"]],
    )
    out += table(
        "Which decisions are written in the working tree but absent from `HEAD:docs/DECISIONS.md`?",
        ["Decision", "Title"],
        [[d, r.index.get(d, (Status.UNKNOWN,))[0]] for d in uncommitted] or [["none", "—"]],
    )
    out += ["### c) Loose ends", ""]
    marker = re.compile(r"#.*\b(" + "|".join(CFG["todo_markers"]) + r")\b")
    todos = []
    for f in r.files:
        if f.split("/")[0] in CFG["todo_scan"]:
            for i, ln in enumerate((text_of(ROOT / f) or "").splitlines(), 1):
                if marker.search(ln):
                    todos.append([f"`{f}:{i}`", ln.strip()])
    out += table(
        f"Which comments carry {', '.join(CFG['todo_markers'])}?",
        ["Where", "Line"],
        todos or [["none", "—"]],
    )
    writes = [w for s in r.scripts.values() for w in s["writes"]]
    orphans = [
        f for f in r.files
        if f.startswith("results/") and f.endswith(".json") and str(Path(f).parent)
        not in r.collapsed and not any(matches(f, w) for w in writes)
    ]  # fmt: skip
    out += table(
        "Which result files does no script's parsed writes produce?",
        ["File"],
        [[f"`{f}`"] for f in orphans] or [["none"]],
    )
    stale = []
    for entry in CFG["generated"]:
        f = freshness(entry)
        if f["missing"]:
            stale.append([f"`{entry['path']}`", Status.NOT_RUN, "—"])
        elif f["outside"]:
            stale.append([f"`{entry['path']}`", f"{len(f['outside'])} lines", f["outside"][0]])
        elif f["changed"]:
            where = ", ".join(f"`{h}`" for h in entry["except_sections"])
            stale.append([f"`{entry['path']}`", f"only in {where}", entry["reason"]])
    out += table(
        "Which generated files differ from a fresh rebuild, beyond their stamp line? Each is "
        "rebuilt in memory by the function its script calls; modification times are not "
        "used, because a clone resets them.",
        ["Generated", "Differs", "First difference or reason"],
        stale or [["none", "—", "—"]],
    )
    return out


def s11_reproduce(r: Repo, rows: list[dict]) -> list[str]:
    steps = {n: s for n, s in r.scripts.items() if s["writes"]}
    task_rank = {t: i for i, t in enumerate(r.tasks)}
    after = {
        n: {
            m
            for m in steps
            if m != n and any(links(w, p) for w in steps[m]["writes"] for p in steps[n]["reads"])
        }
        for n in steps
    }
    # A prerequisite ranks as early as the earliest task that needs it.
    rank = {n: task_rank.get(s["tag"], len(task_rank)) for n, s in steps.items()}
    for _ in steps:
        for n in steps:
            for m in after[n]:
                rank[m] = min(rank[m], rank[n])

    def key(n: str) -> tuple:
        own = task_rank.get(steps[n]["tag"], len(task_rank))
        return (rank[n], own, r.first_seq.get(steps[n]["path"], len(r.commits)), n)

    reach = {n: set(after[n]) for n in steps}  # everything n depends on, transitively
    for _ in steps:
        for n in steps:
            for m in list(reach[n]):
                reach[n] |= reach[m]
    order, pending = [], set(steps)
    while pending:
        # Eligible: every unmet prerequisite is in a cycle with it (or there are none).
        eligible = [n for n in pending if all(n in reach[m] for m in after[n] & pending)]
        pick = min(eligible or pending, key=key)
        order.append(pick)
        pending.remove(pick)
    out_rows = []
    for i, n in enumerate(order, 1):
        s = steps[n]
        req = " ".join(
            a["name"] + f" <{a['name'].lstrip('-').upper()}>" if a["name"].startswith("-")
            else f"<{a['name']}>" for a in s["args"] if a["required"]
        )  # fmt: skip
        cmd = f"uv run python {s['path']} {req}".strip()
        deps = sorted(after[n] & set(order[: i - 1]))
        out_rows.append(
            [i, f"`{cmd}`", ", ".join(s["needs"]) or "local", s["tag"] or "—",
             ", ".join(f"`{d}`" for d in deps) or "—"]
        )  # fmt: skip
    q = (
        "In what order do the scripts rebuild everything? A script runs after every script "
        "that writes a path it reads; ties follow the task order in `TASK_LOG.md`, then "
        "first commit. Scripts with no parsed writes are libraries and omitted; a cycle is "
        "broken at the earliest-ranked script."
    )
    header = ["Step", "Command", "Needs", "Task", "After"]
    return ["## 11. How to reproduce from scratch", "", *table(q, header, out_rows)]


def build() -> str:
    r = Repo()
    rows = task_rows(r)
    head = [
        "# Repository map",
        "",
        f"Generated {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %z}",
        "",
        f"Commit `{r.head}` on `{r.branch}`; {len(r.dirty)} paths differ from it in the "
        "working tree.",
        "",
        "Do not edit by hand — rerun scripts/repo_map.py",
        "",
    ]
    body = [
        s1_what(r),
        s2_pipeline(r),
        s3_directories(r),
        s4_modules(r),
        s5_entry_points(r),
        s6_tasks(r, rows),
        s7_timeline(r),
        s8_models(r),
        s9_tests(r),
        s10_left(r, rows),
        s11_reproduce(r, rows),
    ]
    doc = "\n".join(head + [ln for section in body for ln in section])
    return doc.replace(f"{ROOT}/", "")  # repo paths print relative: no machine's home path


def main() -> None:
    out = ROOT / CFG["output"]
    out.write_text(build())
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
