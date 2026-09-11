from typing import Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["viewer", "operator", "admin"]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: Role
