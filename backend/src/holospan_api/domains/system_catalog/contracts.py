from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Capability(BaseModel):
    id: str
    name: str
    status: Literal["available", "planned"]
    description: str


class CapabilityCatalog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    service: str
    version: str
    deployment_mode: str = Field(alias="deploymentMode")
    capabilities: list[Capability]
