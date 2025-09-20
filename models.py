from typing import Optional
from pydantic import BaseModel
import apmodel as apm


class CreateUser(BaseModel):
    username: str
    display_name: str
    summary: Optional[str]


class User(BaseModel, apm.Person):
    pass
