from typing import Optional
from pydantic import BaseModel

class CreateUser(BaseModel):
    username: str
    display_name : str
    summary: Optional[str]
    