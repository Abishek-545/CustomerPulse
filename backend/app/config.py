from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./customerpulse.db"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    backend_cors_origins: str = "http://localhost:5173"
    mcp_transport: str = "auto"
    mcp_base_url: str | None = None
    mcp_internal_token: str | None = None
    max_agent_steps: int = 8
    checkpoint_backend: str = "auto"
    demo_recipient_email: str = "temp66642@gmail.com"
    email_mode: str = "log"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "CustomerPulse Retention Team"


settings = Settings()
