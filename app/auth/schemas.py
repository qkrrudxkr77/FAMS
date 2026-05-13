from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    message: str
    data: Optional[T] = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "성공") -> "ApiResponse":
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str) -> "ApiResponse":
        return cls(success=False, message=message, data=None)


class TokenData(BaseModel):
    access_token: str
    token_type: str = "Bearer"


class LoginUser(BaseModel):
    email: str
    name: str = ""
    dept_name: str = ""
    position_name: str = ""
    level_name: str = ""
    dept_id: Optional[str] = None
