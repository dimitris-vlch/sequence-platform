"""Environment-driven application settings.

Values are read from the environment (or a local, git-ignored ``.env``
file). No real secrets are ever written into the repository;
``.env.example`` documents the expected variables with empty values.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, all values optional.

    The application is fully functional without an NCBI API key; the
    key only raises the NCBI request-rate ceiling (3 req/s keyless,
    10 req/s with a key).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Entrez requires an email on requests; NCBI may block requests
    # without one. Optional at runtime, used by the NCBI client later.
    ncbi_email: str | None = None
    # Optional NCBI API key. Supplied via environment, never committed.
    ncbi_api_key: str | None = None


def get_settings() -> Settings:
    """Return settings populated from the current environment."""
    return Settings()
