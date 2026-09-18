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
    # Same floor as every other account. This is the highest-privilege login
    # in the system and was previously the only one with no length rule at
    # all, so a one-character superadmin password was accepted. Both fields
    # default to None so a caller can change one without sending the other.
    superadmin_username: str | None = Field(default=None, min_length=3, max_length=64)
    superadmin_password: str | None = Field(default=None, min_length=8)




