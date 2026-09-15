import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.users.models import UserRoleEnum, UserStatusEnum


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str
    role: UserRoleEnum
    status: UserStatusEnum


class ManagerCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)


class ManagerCredentialsUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)


class AssistantCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)


class AssistantCredentialsUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class SuperAdminCredentialsUpdate(BaseModel):
    superadmin_username: str | None
    superadmin_password: str | None




