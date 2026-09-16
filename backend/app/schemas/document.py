from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

class DocumentUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=200_000)

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source: str | None
    uploaded_by: int
    created_at: datetime
    chunk_count: int
