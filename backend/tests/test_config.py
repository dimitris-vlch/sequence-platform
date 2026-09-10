"""Configuration behaviour (Stage 10 hardening item 3).

There is no required configuration in this application, so the property to
pin is the opposite of fail-fast on missing values: it must start with
nothing set at all, and an unfilled ``.env`` (what ``.env.example``
prescribes) must not break it either.

Each test runs from an empty temporary directory, so a developer's local
``backend/.env`` can never change the outcome — the settings file is read
relative to the working directory.

``CORS_ORIGINS`` follows the same "nothing is required" rule: unset (or
blank) means the dev-origin defaults, so a deployment that has not been
told its SPA's origin behaves exactly like local development.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sequence_platform.config import DEFAULT_CORS_ORIGINS, Settings, get_settings


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


def test_cors_origins_fall_back_to_the_dev_origins_when_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unconfigured means the documented local setup, not an empty allowlist.

    ``delenv`` rather than a bare assertion: the test must not depend on the
    developer's shell, and the module docstring promises the same outcome
    from an empty working directory.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings()
    assert settings.cors_origins is None
    assert settings.cors_origin_list == DEFAULT_CORS_ORIGINS


def test_cors_origins_are_parsed_from_a_comma_separated_environment_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The deployed SPA origin is configuration, and whitespace is tolerated."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "CORS_ORIGINS", "https://sequence-platform.example.com, https://spa.example.com"
    )
    settings = Settings()
    assert settings.cors_origins == (
        "https://sequence-platform.example.com, https://spa.example.com"
    )
    assert settings.cors_origin_list == [
        "https://sequence-platform.example.com",
        "https://spa.example.com",
    ]


def test_blank_cors_origins_count_as_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``CORS_ORIGINS=`` (what an unfilled ``.env`` yields) is not an empty list.

    An empty allowlist would silently reject every cross-origin caller, so a
    blank value has to mean "not configured" rather than "allow nothing".
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CORS_ORIGINS", "  ")
    assert Settings().cors_origin_list == DEFAULT_CORS_ORIGINS
