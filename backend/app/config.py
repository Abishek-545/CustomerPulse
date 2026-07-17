from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./customerpulse.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    backend_cors_origins: str = "http://localhost:5173"


settings = Settings()
