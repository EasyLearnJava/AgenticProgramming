"""
nimbus/config.py: the app's settings, and the only module that reads the environment. Pydantic checks each value when
the app starts. Vercel sets the build's own (VERCEL, VERCEL_ENV, the commit, the deployment, its names, and the secret
that gets an automated call past its protection, if that's on), which are read from the real environment only; you set
the rest, in Vercel's project settings, or in .env.local on your computer, which git never sees.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from nimbus.constants import GEMINI_MODEL, PROJECT_ROOT

SHORT_COMMIT_CHARS = 7
# The settings Vercel itself sets on its machines.
VERCEL_FIELDS = frozenset(
    {
        "is_vercel",
        "vercel_env",
        "vercel_git_commit_sha",
        "vercel_deployment_id",
        "vercel_url",
        "vercel_branch_url",
        "vercel_project_production_url",
        "vercel_automation_bypass_secret",
    }
)


class WithoutVercelFields(PydanticBaseSettingsSource):
    """
    A source's values without the ones Vercel sets: `vercel env pull` copies VERCEL="1" and VERCEL_ENV="development"
    into .env.local, and read from there they'd make a computer look like Vercel.
    """

    def __init__(self, settings_cls: type[BaseSettings], source: PydanticBaseSettingsSource) -> None:
        """Wraps a source (the .env files')."""
        super().__init__(settings_cls)
        self.source = source

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        """Not used: __call__ gives every value at once, from the source it wraps."""
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """The wrapped source's values, Vercel's own left out."""
        return {name: value for name, value in self.source().items() if name not in VERCEL_FIELDS}


class Settings(BaseSettings):
    """What the app reads from the environment, each value checked; an empty value counts as unset."""

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), env_ignore_empty=True, extra="ignore")

    # ① Set by Vercel: whether the app runs there (VERCEL=1), in which environment, the commit it built, and the
    # deployment.
    is_vercel: bool = Field(default=False, validation_alias=AliasChoices("is_vercel", "VERCEL"))
    vercel_env: Literal["production", "preview", "development"] | None = None
    vercel_git_commit_sha: str | None = None
    vercel_deployment_id: str | None = None
    # And (step 9) the deployment's own names, which the MCP lane may call: its URL, its branch's, the project's
    # production domain; and the secret that gets an automated call past Vercel's protection, if that's turned on.
    vercel_url: str | None = None
    vercel_branch_url: str | None = None
    vercel_project_production_url: str | None = None
    vercel_automation_bypass_secret: SecretStr | None = None
    # ② Set by you, if you want more or fewer log lines.
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    # ③ Set by you (step 3): the key for Gemini, a Secret variable in Vercel, and which Gemini model answers. Without a
    # key, the chat says it isn't set up.
    google_api_key: SecretStr | None = None
    gemini_model: str = Field(default=GEMINI_MODEL, pattern=r"^[a-z0-9][a-z0-9.\-]*$")
    # Park guidance uses Qdrant for text, BM25 and hosted dense vectors; the local catalog is metadata only.
    flights_enabled: bool = False
    hotels_enabled: bool = False
    # Isolated synthetic booking demo. Never accepts a Nuitée production credential or real passenger details.
    booking_demo_enabled: bool = True
    booking_demo_secret: SecretStr | None = Field(default=None, min_length=32)
    parks_enabled: bool = True
    parks_retrieval_mode: Literal["auto", "lexical", "hybrid"] = "hybrid"
    parks_semantic_provider: Literal["qdrant"] = "qdrant"
    parks_qdrant_collection: str = Field(default="nimbus_park_guidance_v3", pattern=r"^[a-z][a-z0-9_]{0,63}$")
    parks_rerank_enabled: bool = True
    parks_qdrant_api_key: SecretStr | None = None
    parks_index_path: Path = PROJECT_ROOT / "data" / "parks" / "catalog.json"
    parks_prepared_path: Path = PROJECT_ROOT / "data" / "parks" / "prepared.json"
    # Optional official NPS notices; keep the credential in .env.local or a Sensitive deployment variable.
    nps_api_key: SecretStr | None = None
    # Opt-in browser-scoped travel preferences; an independent stable secret signs its opaque browser identity.
    memory_enabled: bool = False
    mem0_api_key: SecretStr | None = None
    memory_cookie_secret: SecretStr | None = Field(default=None, min_length=32)
    # Optional private weather-answer reuse. Hosted Qdrant inference keeps ML packages off Vercel.
    semantic_cache_mode: Literal["off", "shadow", "on"] = "off"
    semantic_cache_threshold: float = Field(default=0.80, ge=0.80, le=1.0, allow_inf_nan=False)
    qdrant_url: str = ""
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = Field(default="nimbus_weather_cache", pattern=r"^[a-z][a-z0-9_]{0,63}$")

    @field_validator("qdrant_url")
    @classmethod
    def cloud_cache_endpoint(cls, value: str) -> str:
        """Keep the database credential on the configured HTTPS Qdrant Cloud cluster, with no redirects."""
        if not value:
            return ""
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".cloud.qdrant.io")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or parsed.port not in {None, 443, 6333}
        ):
            raise ValueError("Use the HTTPS Qdrant Cloud cluster endpoint without credentials or a path")
        return value.rstrip("/")

    # ④ Set by you: LangSmith's tracing, its key and project, and whether it hides each run's inputs and outputs. The
    # app traces only when these say to hide both, through a client of its own that hides both, into this project
    # (model.py).
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str | None = None
    langsmith_workspace_id: UUID | None = None
    langsmith_hide_inputs: bool = False
    langsmith_hide_outputs: bool = False
    # ⑥ Set by you (step 10): Apify's token, a Sensitive variable in Vercel, for the lanes with auth; without it,
    # they're closed.
    apify_token: SecretStr | None = None
    # ⑦ Set by you (step 12): Axiom's token, which can only ingest, and its dataset; without both, the lines stay in
    # Vercel's logs. And Sentry's DSN; without it, errors stay in the lines.
    axiom_token: SecretStr | None = None
    axiom_dataset: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
    sentry_dsn: SecretStr | None = None
    # ⑧ Set by you (step 14): a second Axiom token, which can only query the dataset, for the Observability pages;
    # without it and the dataset, they say Axiom isn't connected.
    axiom_query_token: SecretStr | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """
        ⑤ Where the settings come from, the first that has a value winning: the code's own values, the real
        environment, then the .env files, without Vercel's variables.
        """
        return init_settings, env_settings, WithoutVercelFields(settings_cls, dotenv_settings), file_secret_settings

    @property
    def environment(self) -> str:
        """Where the app runs: Vercel's environment, else "local"."""
        return self.vercel_env or "local"

    @property
    def commit(self) -> str | None:
        """The commit Vercel built, shortened as git shows it; None on a computer."""
        sha = self.vercel_git_commit_sha
        return None if sha is None else sha[:SHORT_COMMIT_CHARS]

    @property
    def public_deployment(self) -> str | None:
        value = self.vercel_deployment_id or ""
        return value if re.fullmatch(r"dpl_[a-zA-Z0-9_-]{1,96}", value) else None

    @property
    def build_label(self) -> str:
        """The menu's last line: which build is running."""
        return f"Build {self.commit} · {self.environment}" if self.commit else f"Build: {self.environment}"


@lru_cache
def get_settings() -> Settings:
    """The settings, read once, when the app starts."""
    return Settings()
