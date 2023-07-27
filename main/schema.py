from typing import List
from pydantic import BaseModel, Field

class CustomResponseSchema(BaseModel):
    """An answer to the question being asked, with a list of residencies."""

    residencies: List[str] = Field(
        ..., description="List of names of residencies in answer (limited to 2)"
    )
    answer: str = Field(..., description="Answer to the question that was asked")
