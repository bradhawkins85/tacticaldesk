from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    app_name: str = "Tactical Desk"
    database_url: str = Field(
        default="sqlite+aiosqlite:///./tacticaldesk.db",
        description="SQLAlchemy database URL",
    )
    mysql_host: str | None = Field(
        default=None,
        description="MySQL host",
        env="TACTICAL_DESK_MYSQL_HOST",
    )
    mysql_port: int = Field(
        default=3306,
        description="MySQL port",
        env="TACTICAL_DESK_MYSQL_PORT",
    )
    mysql_username: str | None = Field(
        default=None,
        description="MySQL username",
        env="TACTICAL_DESK_MYSQL_USER",
    )
    mysql_password: str | None = Field(
        default=None,
        description="MySQL password",
        env="TACTICAL_DESK_MYSQL_PASSWORD",
    )
    mysql_database: str | None = Field(
        default=None,
        description="MySQL database name",
        env="TACTICAL_DESK_MYSQL_DATABASE",
    )
    secret_key: str = Field(default="change-me", description="Secret key for signing tokens")
    enable_installers: bool = Field(
        default=False,
        description="Allow executing provisioning scripts from the API",
        env="TACTICAL_DESK_ENABLE_INSTALLERS",
    )
    ntfy_base_url: str | None = Field(
        default=None,
        description="Default ntfy base URL override",
        env="TACTICAL_DESK_NTFY_BASE_URL",
    )
    ntfy_topic: str | None = Field(
        default=None,
        description="Default ntfy topic override",
        env="TACTICAL_DESK_NTFY_TOPIC",
    )
    ntfy_token: str | None = Field(
        default=None,
        description="Default ntfy access token",
        env="TACTICAL_DESK_NTFY_TOKEN",
    )
    smtp_host: str | None = Field(
        default=None,
        description="Default SMTP host when not configured per module",
        env="TACTICAL_DESK_SMTP_HOST",
    )
    smtp_port: int = Field(
        default=587,
        description="Default SMTP port",
        env="TACTICAL_DESK_SMTP_PORT",
    )
    smtp_username: str | None = Field(
        default=None,
        description="Default SMTP username",
        env="TACTICAL_DESK_SMTP_USERNAME",
    )
    smtp_password: str | None = Field(
        default=None,
        description="Default SMTP password",
        env="TACTICAL_DESK_SMTP_PASSWORD",
    )
    smtp_sender: str | None = Field(
        default=None,
        description="Default SMTP sender email address",
        env="TACTICAL_DESK_SMTP_SENDER",
    )
    smtp_use_tls: bool = Field(
        default=True,
        description="Enable STARTTLS when connecting to SMTP",
        env="TACTICAL_DESK_SMTP_USE_TLS",
    )
    smtp_use_ssl: bool = Field(
        default=False,
        description="Use implicit TLS when connecting to SMTP",
        env="TACTICAL_DESK_SMTP_USE_SSL",
    )
    mcp_api_key: str | None = Field(
        default=None,
        description="API key required for ChatGPT MCP connector",
        env="TACTICAL_DESK_MCP_API_KEY",
    )

    class Config:
        env_file = ".env"

    @property
    def resolved_database_url(self) -> str:
        if all([self.mysql_host, self.mysql_username, self.mysql_password, self.mysql_database]):
            user = quote_plus(self.mysql_username)
            password = quote_plus(self.mysql_password)
            return (
                f"mysql+aiomysql://{user}:{password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            )
        return self.database_url


@lru_cache()
def get_settings() -> Settings:
    return Settings()
