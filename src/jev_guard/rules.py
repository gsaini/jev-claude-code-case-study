"""The deterministic layer: parse the command, then let code decide everything code can decide.

Order of evaluation (first match wins):
1. **Hard deny** — catastrophic, unambiguous patterns. Code, never a model.
2. **Secrets** — paths and variables that hold credentials → ask. Deterministic, so code.
3. **Fast path** — plainly read-only commands → no opinion, no model call, no latency.
4. Everything else is *ambiguous* and goes to Jev.

Parsing is deliberately conservative: anything the parser can't read cleanly (unbalanced quotes,
command substitution) is never fast-pathed.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

OPERATORS = {";", "&&", "||", "|", "&", "|&"}
READ_ONLY = {
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "rg",
    "wc",
    "pwd",
    "echo",
    "which",
    "diff",
    "stat",
    "du",
    "file",
    "basename",
    "dirname",
    "realpath",
}  # fmt: skip — no env/xargs/sort/tree/uniq: each can run or write something
GIT_READ_ONLY = {"status", "log", "diff", "show", "blame", "rev-parse", "ls-files", "describe", "shortlog"}
TEST_RUNNERS = {("pytest",), ("python", "-m", "pytest"), ("ruff", "check"), ("ruff", "format", "--check")}
ROOT_TARGETS = {"/", "/*", "~", "~/", "~/*", "$HOME", "$HOME/", "${HOME}", ".", "./", "..", "*", "/usr", "/etc"}
SECRET_PATH = re.compile(
    r"(^|[/\s'\"=])(\.env(\.[\w-]+)?|\.npmrc|\.netrc|\.pypirc|id_rsa|id_ed25519|[\w-]+\.pem|credentials(\.json)?)\b"
    r"|\.ssh/|\.aws/|\.config/gcloud|\.kube/config",
)
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PIPE_TO_INTERPRETER = re.compile(
    r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh|dash|fish|python3?|node|perl|ruby)(\s+-s?)?\s*($|[;&|])"
)
SECRET_VAR = re.compile(r"\$\{?\w*(SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)\w*\}?", re.IGNORECASE)


@dataclass(frozen=True)
class RuleResult:
    decision: str  # "deny" | "ask" | "none" (fast path) | "ambiguous" (ask Jev)
    reason: str


def segments(command: str) -> list[list[str]] | None:
    """Split into simple commands on ; && || | &. None when the shell syntax can't be read safely."""
    if "$(" in command or "`" in command or "<(" in command:
        return None
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    out: list[list[str]] = [[]]
    for token in tokens:
        if token in OPERATORS:
            out.append([])
        else:
            out[-1].append(token)
    return [s for s in out if s]


def _program(segment: list[str]) -> str:
    """The program a simple command runs, skipping leading VAR=value assignments."""
    i = 0
    while i < len(segment) and ASSIGNMENT.match(segment[i]):
        i += 1
    return segment[i].rsplit("/", 1)[-1] if i < len(segment) else ""


def hard_deny(command: str, segs: list[list[str]] | None) -> str | None:
    compact = command.replace(" ", "")
    if ":(){" in compact and ":|:&" in compact:
        return "fork bomb"
    if re.search(r"\bmkfs(\.\w+)?\b", command) or re.search(r"\bdd\b.*\bof=/dev/", command):
        return "writes a filesystem or raw device"
    if PIPE_TO_INTERPRETER.search(command):
        return "pipes a download straight into an interpreter"
    for seg in segs or []:
        prog = _program(seg)
        args = seg[1:] if prog != "sudo" else seg[2:]
        prog = _program(seg[1:]) if prog == "sudo" and len(seg) > 1 else prog
        flags = "".join(a.lstrip("-") for a in args if a.startswith("-") and not a.startswith("--"))
        targets = [a for a in args if not a.startswith("-")]
        recursive = "r" in flags.lower() or "--recursive" in args
        if prog == "rm" and recursive and any(t.rstrip("/") in {x.rstrip("/") for x in ROOT_TARGETS} for t in targets):
            return f"recursive delete of {', '.join(targets)}"
        if prog == "chmod" and recursive and any(t in {"/", "~", "$HOME"} for t in targets):
            return "recursive permission change on a root directory"
    return None


def secrets(command: str) -> str | None:
    if SECRET_PATH.search(command):
        return "touches a file that usually holds credentials"
    if SECRET_VAR.search(command):
        return "reads a variable that usually holds a secret"
    return None


def fast_path(segs: list[list[str]] | None, command: str) -> bool:
    """True only for commands that are plainly read-only, with no redirection to a file."""
    if segs is None or ">" in command:
        return False
    for seg in segs:
        prog = _program(seg)
        if prog == "git":
            sub = next((w for w in seg[1:] if not w.startswith("-")), "")
            if sub not in GIT_READ_ONLY:
                return False
        elif prog == "find":
            if any(a in {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint"} for a in seg):
                return False
        elif prog not in READ_ONLY and not any(tuple(seg[: len(r)]) == r for r in TEST_RUNNERS):
            return False
    return True


def classify(command: str) -> RuleResult:
    segs = segments(command)
    if reason := hard_deny(command, segs):
        return RuleResult("deny", reason)
    if reason := secrets(command):
        return RuleResult("ask", reason)
    if fast_path(segs, command):
        return RuleResult("none", "read-only")
    return RuleResult("ambiguous", "needs a judgment")


_REDACTIONS = [
    (re.compile(r"(?i)\b(authorization:\s*(bearer|basic)\s+)\S+"), r"\1[REDACTED]"),
    (
        re.compile(r"(?i)\b([\w-]*(?:token|secret|password|passwd|api[_-]?key)[\w-]*\s*[=:]\s*)(['\"]?)[^\s'\"]+\2"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_-]{16,}"), "[REDACTED]"),
    (re.compile(r"\b(ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}"), "[REDACTED]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9+_-]{48,}={0,2}"), "[REDACTED]"),  # long tokens; spares 40-char git SHAs
]


def redact(command: str) -> str:
    """Strip likely secrets before a command leaves the machine (to Jev, or to the log)."""
    for pattern, replacement in _REDACTIONS:
        command = pattern.sub(replacement, command)
    return command
