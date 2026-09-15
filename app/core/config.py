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

settings = Settings()