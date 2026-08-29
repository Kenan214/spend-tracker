"""Chat advisor backend — read-only v1 slice of the "Future state: in-app
chat advisor for transaction classification, spend Q&A & affordability
decisions" plan in README.md.

Wraps the `claude` CLI rather than the Messages API/Agent SDK, so chat rides
on an existing Claude subscription instead of a separately metered API key
(see README's design notes for why). Each turn is a fresh `claude -p
--output-format json` subprocess restricted to exactly the
search_transactions tool `mcp_server.py` exposes — `--tools ""` drops every
built-in tool (Bash included), `--strict-mcp-config` ignores any other MCP
servers configured on this machine, and `--allowedTools` names only that
one tool so it doesn't need an interactive permission prompt. Continuity
across turns comes from `--resume <session_id>` (tracked in Streamlit
session state by app.py), not from resending the full history each time.

No write tool exists yet (no `apply_category_override`) — this is
deliberately the read-only slice called out in README.md; wire in a write
tool once this has been used a bit.
"""
import functools
import json
import shutil
import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
MCP_SERVER_PATH = MODULE_DIR / "mcp_server.py"
ALLOWED_TOOL = "mcp__spend_tracker__search_transactions"
TURN_TIMEOUT_SECONDS = 120
SETUP_CHECK_TIMEOUT_SECONDS = 10

# Anthropic's own documented native installer (no Node.js/npm required):
# https://code.claude.com/docs/en/setup
INSTALL_COMMAND = "curl -fsSL https://claude.ai/install.sh | bash"

# Fallback locations for the `claude` binary, checked when it's not on PATH.
# Needed because the native Mac app wrapper (launcher.applescript's `do
# shell script`) can run with a minimal PATH that omits Homebrew's
# /opt/homebrew/bin, even though the CLI works fine from a terminal.
_CLAUDE_BIN_CANDIDATES = (
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    str(Path.home() / ".claude" / "local" / "claude"),
    str(Path.home() / ".local" / "bin" / "claude"),
)

SYSTEM_PROMPT = (
    "You are the in-app chat advisor for Spend Tracker, a personal budgeting app. "
    "You can only see the user's transactions through the search_transactions tool "
    "— you have no other tools, and no ability to write or change any data. If the "
    "user wants a categorization fixed, tell them to use the 'Manual category "
    "overrides' expander on the Overview tab for now (a chat-driven write is a "
    "planned future step, not built yet). Transaction amount is signed: negative "
    "means money OUT (spend), positive means money IN (income/refund/credit) — "
    "e.g. 'spend over $30' means amount <= -30. Always call search_transactions "
    "for factual claims about the user's spend rather than guessing, and prefer "
    "its total_amount field over summing rows yourself when results are "
    "truncated. This is arithmetic over the user's logged transaction history, "
    "not personalized financial advice — say so for questions that call for real "
    "financial judgment (e.g. affordability)."
)


class ChatError(RuntimeError):
    """Raised with a message safe to show directly in the chat UI."""


@functools.lru_cache(maxsize=1)
def _claude_binary() -> str:
    """Resolve the claude CLI's absolute path without trusting PATH."""
    found = shutil.which("claude")
    if found:
        return found
    for candidate in _CLAUDE_BIN_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    raise ChatError(
        "Couldn't find the `claude` CLI (checked PATH and "
        f"{', '.join(_CLAUDE_BIN_CANDIDATES)}). Install Claude Code CLI, or "
        "if it's installed somewhere else, add its directory to PATH."
    )


def check_setup() -> dict:
    """Non-interactive check of whether the chat advisor is ready to use.

    Returns {"installed": bool, "logged_in": bool | None, "email": str | None}.
    logged_in is None if installed but status couldn't be determined (e.g. an
    unexpectedly old CLI version without `auth status`) — treated as "assume
    ready" by callers, since send_message will surface a clear error anyway
    if something's actually wrong.
    """
    try:
        binary = _claude_binary()
    except ChatError:
        return {"installed": False, "logged_in": None, "email": None}

    try:
        proc = subprocess.run(
            [binary, "auth", "status", "--json"],
            capture_output=True, text=True, timeout=SETUP_CHECK_TIMEOUT_SECONDS,
        )
        status = json.loads(proc.stdout)
        return {
            "installed": True,
            "logged_in": bool(status.get("loggedIn")),
            "email": status.get("email"),
        }
    except Exception:
        return {"installed": True, "logged_in": None, "email": None}


def _mcp_config_json() -> str:
    return json.dumps({
        "mcpServers": {
            "spend_tracker": {
                "command": sys.executable,
                "args": [str(MCP_SERVER_PATH)],
            }
        }
    })


def send_message(prompt: str, session_id: str | None) -> dict:
    """Run one chat turn via the claude CLI. Returns {"session_id", "text"}.

    Raises ChatError (message is safe to display) if the CLI is missing,
    times out, exits non-zero, returns unparseable output, or reports an
    in-band error.
    """
    cmd = [
        _claude_binary(), "-p", prompt,
        "--output-format", "json",
        "--mcp-config", _mcp_config_json(),
        "--strict-mcp-config",
        "--tools", "",
        "--allowedTools", ALLOWED_TOOL,
        "--append-system-prompt", SYSTEM_PROMPT,
    ]
    if session_id:
        cmd += ["--resume", session_id]

    try:
        # CodeQL flags `cmd` as tainted (it embeds `prompt`, which traces back
        # to the chat box in app.py) under py/command-line-injection. Not
        # exploitable: `cmd` is a list and shell=True is never set, so the
        # entire prompt lands as one argv element passed straight to execve —
        # no shell parses it, so it can't inject flags or a second command.
        proc = subprocess.run(  # lgtm[py/command-line-injection]
            cmd, capture_output=True, text=True, timeout=TURN_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise ChatError(
            "Claude Code CLI (`claude`) not found on PATH — the chat advisor needs "
            "it installed and logged in."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ChatError("The chat advisor timed out waiting for a response.") from exc

    if proc.returncode != 0:
        raise ChatError(
            f"claude CLI exited with an error (code {proc.returncode}):\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ChatError(f"Couldn't parse claude CLI output:\n{proc.stdout[:500]}") from exc

    if payload.get("is_error"):
        raise ChatError(payload.get("result") or "The chat advisor returned an error.")

    return {"session_id": payload["session_id"], "text": payload.get("result", "")}
