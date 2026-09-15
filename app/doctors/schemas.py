from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DoctorCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    specialty: str = Field(min_length=1, max_length=50)


class DoctorUpdate(BaseModel):
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    specialty: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )


class DoctorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    specialty: str
    created_at: datetime
    updated_at: datetime


class DoctorOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
