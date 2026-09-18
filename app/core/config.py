from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        )
    project_name: str = "SenaMed CRM"
    database_url: str # .env filedan uqiydi.
    redis_url: str


    secret_key: str
    jwt_algorithm:str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    superadmin_username: str
    superadmin_password: str

    # "production" or "development". Only ever relaxes guards, never tightens
    # them, so an unset/typo'd value stays safe.
    environment: str = "production"

    # /docs, /redoc and /openapi.json. Off by default: the full API surface,
    # including every admin-only route, is otherwise enumerable before login.
    docs_enabled: bool = False

    # Whether X-Forwarded-For may be trusted for rate-limit keying. See the
    # long note in app/core/rate_limit.py — wrong in either direction has a
    # real cost, so it is explicit rather than guessed.
    trust_proxy_headers: bool = False

    # Tests turn this off; the login limiter is otherwise shared Redis state
    # that makes any suite doing more than five logins a minute flaky.
    rate_limit_enabled: bool = True

    @property
    def is_development(self) -> bool:
        return self.environment.strip().lower() == "development"

settings = Settings()
