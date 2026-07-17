from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./customerpulse.db"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    backend_cors_origins: str = "http://localhost:5173"


settings = Settings()
