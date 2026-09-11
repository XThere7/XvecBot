"""
models/document.py
Pydantic models for documents — used in API request/response validation
and as DTOs between service layers.
"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
import uuid


class DocumentCreate(BaseModel):
    filename: str
    total_pages: int
    file_size: int


class DocumentRead(BaseModel):
    id: str
    filename: str
    upload_date: datetime
    total_pages: int
    file_size: int
    status: Literal["processing", "ready", "error"]

    model_config = {"from_attributes": True}


class DocumentList(BaseModel):
    documents: list[DocumentRead]
    total: int


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    total_pages: int
    chunk_count: int
    message: str = "Document ingested successfully"
