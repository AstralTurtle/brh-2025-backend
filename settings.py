from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import cache


class Settings(BaseSettings):
    # Example settings
   private_key: str
   host: str
   
   model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
   
@cache
def get_settings() -> Settings:
    return Settings()