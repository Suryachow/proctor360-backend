from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Proctor360 API"
    database_url: str = "sqlite:///./proctor.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "replace_me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    exam_otp_expire_minutes: int = 30
    admin_email: str = "admin@proctor360.com"
    admin_password: str = "Admin123!"
    admin_mfa_secret: str = "JBSWY3DPEHPK3PXP"
    admin_mfa_window: int = 1
    admin_mfa_static_code: str = "123456"
    compliance_mode: str = "GDPR,ISO27001,FERPA"
    ai_engine_url: str = "http://localhost:8100"
    groq_api_key: str = ""
    groq_api_keys: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    cors_allow_origins: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
    trusted_hosts: str = "localhost,127.0.0.1,0.0.0.0,localhost"
    enforce_https_headers: bool = False
    rate_limit_general_per_minute: int = 180
    rate_limit_auth_per_minute: int = 30
    rate_limit_proctor_per_minute: int = 600
    rate_limit_use_redis: bool = False
    rate_limit_redis_prefix: str = "proctor:ratelimit"
    idempotency_ttl_seconds: int = 600
    idempotency_cleanup_interval_seconds: int = 300
    idempotency_cleanup_batch_size: int = 1000
    ai_http_timeout_seconds: float = 10.0
    ai_http_max_retries: int = 3
    ai_http_retry_backoff_seconds: float = 0.35
    observability_enable_metrics: bool = True
    observability_json_logs: bool = True
    observability_log_level: str = "INFO"

    # EVENT STRATEGY (KAFKA + N8N)
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_violation_topic: str = "proctor.violations"
    n8n_webhook_url: str = "http://localhost:5678/webhook-test/proctor-intervention"

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_origins.split(",") if item.strip()]

    @property
    def trusted_hosts_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]


settings = Settings()
