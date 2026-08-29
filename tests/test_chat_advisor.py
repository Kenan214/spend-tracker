import json
import subprocess

import pytest

import chat_advisor


@pytest.fixture(autouse=True)
def clear_binary_cache():
    chat_advisor._claude_binary.cache_clear()
    yield
    chat_advisor._claude_binary.cache_clear()


class TestClaudeBinary:
    def test_uses_which_when_on_path(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        assert chat_advisor._claude_binary() == "/usr/bin/claude"

    def test_falls_back_to_known_install_locations(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: None)
        # Candidates 0/1 are POSIX string literals that stringify differently
        # once round-tripped through Path on Windows (forward vs. backslash),
        # so they'd never match `str(self) == target` there. Candidate 2 is
        # built via Path.home() like the code under test builds it, so its
        # string form is self-consistent on every OS.
        target = chat_advisor._CLAUDE_BIN_CANDIDATES[2]
        monkeypatch.setattr(
            chat_advisor.Path, "is_file", lambda self: str(self) == target,
        )
        assert chat_advisor._claude_binary() == target

    def test_raises_chat_error_when_not_found_anywhere(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: None)
        monkeypatch.setattr(chat_advisor.Path, "is_file", lambda self: False)
        with pytest.raises(chat_advisor.ChatError):
            chat_advisor._claude_binary()


class TestCheckSetup:
    def test_not_installed(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: None)
        monkeypatch.setattr(chat_advisor.Path, "is_file", lambda self: False)
        assert chat_advisor.check_setup() == {"installed": False, "logged_in": None, "email": None}

    def test_installed_and_logged_in(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(
            chat_advisor.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(
                a[0], 0, stdout=json.dumps({"loggedIn": True, "email": "user@example.com"}), stderr="",
            ),
        )
        assert chat_advisor.check_setup() == {
            "installed": True, "logged_in": True, "email": "user@example.com",
        }

    def test_installed_but_status_check_fails(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")

        def raise_timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="claude", timeout=10)

        monkeypatch.setattr(chat_advisor.subprocess, "run", raise_timeout)
        assert chat_advisor.check_setup() == {"installed": True, "logged_in": None, "email": None}

    def test_installed_but_unparseable_status(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(
            chat_advisor.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="not json", stderr=""),
        )
        assert chat_advisor.check_setup() == {"installed": True, "logged_in": None, "email": None}


class TestSendMessage:
    def test_successful_turn_returns_session_and_text(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(
            chat_advisor.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(
                a[0], 0, stdout=json.dumps({"session_id": "abc123", "result": "hi there"}), stderr="",
            ),
        )
        result = chat_advisor.send_message("hello", None)
        assert result == {"session_id": "abc123", "text": "hi there"}

    def test_resume_passes_session_id_to_cli(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps({"session_id": "abc123", "result": "ok"}), stderr="",
            )

        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(chat_advisor.subprocess, "run", fake_run)
        chat_advisor.send_message("hello again", "abc123")
        assert "--resume" in captured["cmd"]
        assert captured["cmd"][captured["cmd"].index("--resume") + 1] == "abc123"

    def test_binary_not_found_raises_chat_error(self, monkeypatch):
        def raise_missing(cmd, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(chat_advisor.subprocess, "run", raise_missing)
        with pytest.raises(chat_advisor.ChatError):
            chat_advisor.send_message("hello", None)

    def test_timeout_raises_chat_error(self, monkeypatch):
        def raise_timeout(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=120)

        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(chat_advisor.subprocess, "run", raise_timeout)
        with pytest.raises(chat_advisor.ChatError, match="timed out"):
            chat_advisor.send_message("hello", None)

    def test_nonzero_exit_raises_chat_error_with_stderr(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(
            chat_advisor.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(a[0], 1, stdout="", stderr="boom"),
        )
        with pytest.raises(chat_advisor.ChatError, match="boom"):
            chat_advisor.send_message("hello", None)

    def test_unparseable_output_raises_chat_error(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(
            chat_advisor.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="not json", stderr=""),
        )
        with pytest.raises(chat_advisor.ChatError, match="Couldn't parse"):
            chat_advisor.send_message("hello", None)

    def test_in_band_error_raises_chat_error(self, monkeypatch):
        monkeypatch.setattr(chat_advisor.shutil, "which", lambda name: "/usr/bin/claude")
        monkeypatch.setattr(
            chat_advisor.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(
                a[0], 0, stdout=json.dumps({"is_error": True, "result": "quota exceeded"}), stderr="",
            ),
        )
        with pytest.raises(chat_advisor.ChatError, match="quota exceeded"):
            chat_advisor.send_message("hello", None)
