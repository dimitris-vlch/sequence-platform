"""Environment-driven application settings.

Values are read from the environment (or a local, git-ignored ``.env``
file). No real secrets are ever written into the repository;
``.env.example`` documents the expected variables with empty values.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Origins allowed to call the API from a browser during local development
# (the Vite dev server). Used when ``CORS_ORIGINS`` is unset, so the
# documented local setup needs no configuration at all.
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


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
    # Browser origins allowed to call /api cross-origin, comma-separated
    # ("https://spa.example.com,https://other.example.com"). Unset means
    # the documented local setup, DEFAULT_CORS_ORIGINS. See
    # ``cors_origin_list`` for the parsed value the app uses.
    cors_origins: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        """The origin allowlist for ``CORSMiddleware``, defaults included.

        A blank value counts as unset: an unfilled ``.env`` (what
        ``.env.example`` prescribes) yields ``""`` rather than ``None``,
        and an empty allowlist would silently reject every cross-origin
        caller instead of falling back to local development. Whitespace
        around entries is ignored.

        Never returns ``["*"]``: the middleware pairs this list with
        ``allow_credentials=True``, which a wildcard is invalid with.
        """
        if self.cors_origins is None or not self.cors_origins.strip():
            return list(DEFAULT_CORS_ORIGINS)
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


def get_settings() -> Settings:
    """Return settings populated from the current environment."""
    return Settings()
