"""Configuration behaviour (Stage 10 hardening item 3).

There is no required configuration in this application, so the property to
pin is the opposite of fail-fast on missing values: it must start with
nothing set at all, and an unfilled ``.env`` (what ``.env.example``
prescribes) must not break it either.

Each test runs from an empty temporary directory, so a developer's local
``backend/.env`` can never change the outcome — the settings file is read
relative to the working directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sequence_platform.config import Settings, get_settings


def test_settings_need_no_environment_at_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every setting has a safe default: the documented keyless setup."""
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.ncbi_email is None
    assert settings.ncbi_api_key is None


def test_documented_environment_variables_are_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NCBI_EMAIL", "someone@example.com")
    monkeypatch.setenv("NCBI_API_KEY", "synthetic-key")
    settings = Settings()
    assert settings.ncbi_email == "someone@example.com"
    assert settings.ncbi_api_key == "synthetic-key"


def test_empty_values_and_unknown_keys_do_not_break_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``NCBI_EMAIL=`` (as ``.env.example`` shows) is valid, not malformed.

    Both fields are plain optional strings, so there is no value a user can
    put in them that fails validation — the only thing that could go wrong is
    a key the application does not know, which is ignored by design
    (``extra="ignore"``).
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NCBI_EMAIL", "")
    monkeypatch.setenv("NCBI_API_KEY", "")
    monkeypatch.setenv("NOT_A_SETTING", "ignored")
    settings = Settings()
    assert settings.ncbi_email == ""
    assert settings.ncbi_api_key == ""


def test_get_settings_reads_the_current_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NCBI_EMAIL", "current@example.com")
    assert get_settings().ncbi_email == "current@example.com"
