from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypeForm

T = TypeVar("T")


class Meta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(alias="requestId")
    timestamp: datetime


class Envelope[T](BaseModel):
    data: T
    meta: Meta

    @classmethod
    def model_parametrized_name(cls, params: tuple[TypeForm[Any], ...]) -> str:
        return f"{getattr(params[0], '__name__', 'Data')}Envelope"


class ErrorDetail(BaseModel):
    field: str | None = None
    code: str
    message: str


class ErrorBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str = Field(alias="requestId")
    timestamp: datetime


class ErrorEnvelope(BaseModel):
    error: ErrorBody
