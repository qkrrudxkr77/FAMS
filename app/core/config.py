from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    jwt_issuer: str = "bodyfriend-fams"
    workthrough_secret_key: str
    fams_secret_key: str
    access_token_expiry: int = 43200000   # 12시간 (ms)
    refresh_token_expiry: int = 1209600000  # 14일 (ms)

    mysql_host: str = "localhost"
    mysql_port: int = 8882
    mysql_db: str = "repohub"
    mysql_user: str = "admin"
    mysql_password: str = ""

    works_auth_url: str = "https://auth.worksmobile.com/oauth2/v2.0/token"
    works_base_url: str = "https://www.worksapis.com/v1.0"
    works_client_id: str = ""
    works_client_secret: str = ""
    works_service_account_id: str = ""
    works_private_key_path: str = "secrets/private_20260421171835.key"
    works_scope: str = "directory.read,orgunit.read,user.read"
    works_token_ttl_seconds: int = 3000

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    app_env: str = "dev"
    app_port: int = 8001


settings = Settings()
