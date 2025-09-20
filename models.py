from typing import List, Optional

from pydantic import BaseModel


class CreateUser(BaseModel):
    username: str
    display_name: str
    summary: Optional[str] = ""
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class CreatePost(BaseModel):
    content: str
    to: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    summary: Optional[str] = None  # For content warnings
    sensitive: Optional[bool] = False
    in_reply_to: Optional[str] = None  # For replies
