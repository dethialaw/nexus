"""API schemas, distinct from core entities."""

from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]
