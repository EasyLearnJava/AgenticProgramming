"""
nimbus/config.py: the app's settings, and the only module that reads the environment. Pydantic checks each value when
the app starts. Vercel sets the build's own (VERCEL, VERCEL_ENV, the commit, the deployment), which are read from the
real environment only; you set the rest, in Vercel's project settings, or in .env.local on your computer, which git
never sees.
"""

from functools import lru_cache
from typing import Any, Literal

from pydantic import AliasChoices, Field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

SHORT_COMMIT_CHARS = 7
# The settings Vercel itself sets on its machines.
VERCEL_FIELDS = frozenset({"is_vercel", "vercel_env", "vercel_git_commit_sha", "vercel_deployment_id"})


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
    # ② Set by you, if you want more or fewer log lines.
    log_level: Literal["debug", "info", "warning", "error"] = "info"

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
        ③ Where the settings come from, the first that has a value winning: the code's own values, the real
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
    def build_label(self) -> str:
        """The menu's last line: which build is running."""
        return f"Build {self.commit} · {self.environment}" if self.commit else f"Build: {self.environment}"


@lru_cache
def get_settings() -> Settings:
    """The settings, read once, when the app starts."""
    return Settings()
