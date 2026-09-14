from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Multi-Currency Wallet Platform"
    database_url: str = "sqlite:///./wallet.db"
    jwt_secret: str = "development-only-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: list[str] = ["http://localhost:5173"]
    supported_currencies: list[str] = ["USD", "EUR", "GBP", "INR", "JPY"]
    base_currency: str = "USD"
    exchange_provider_url: str = "https://api.exchangerate.host/latest"
    exchange_rate_max_age_minutes: int = 1440
    exchange_refresh_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("cors_origins", "supported_currencies", mode="before")
    @classmethod
    def split_csv(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
