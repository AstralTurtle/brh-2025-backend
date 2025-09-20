from typing import Optional

import apkit.models as apm
from pydantic import BaseModel


class CreateUser(BaseModel):
    username: str
    display_name: str
    summary: Optional[str]
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class User(BaseModel, apm.Person):
    pass


class Post(BaseModel, apm.Note):
    embed_url: Optional[str]
