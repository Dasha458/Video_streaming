from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VideoIndexDocument(BaseModel):
    id: UUID = Field(..., description="Unique ID of the video (UUID)")
    name: str = Field(..., description="Video title", min_length=1)
    description: Optional[str] = Field(None, description="Video description")
    category: Optional[str] = Field(None, description="Category slug or name")
    channel_id: UUID = Field(..., description="Channel UUID")
    views: int = Field(0, description="Total number of views")


class VideoIndexMapping:
    """
    Defines the Elasticsearch mapping for the 'videos' index.
    """

    index_name = "videos"
    settings = {
        "analysis": {
            "analyzer": {
                "autocomplete_analyzer": {
                    "tokenizer": "autocomplete_tokenizer",
                    "filter": ["lowercase"],
                }
            },
            "tokenizer": {
                "autocomplete_tokenizer": {
                    "type": "edge_ngram",
                    "min_gram": 1,
                    "max_gram": 20,
                    "token_chars": ["letter", "digit"],
                }
            },
        }
    }
    mappings = {
        "properties": {
            "id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "autocomplete_analyzer",
                "search_analyzer": "standard",
            },
            "description": {"type": "text", "analyzer": "english"},
            "channel_id": {"type": "keyword"},
            "category": {"type": "keyword"},  # A single category
            "views": {"type": "integer"},
            # For the video hints/autocomplete feature
            "suggest_name": {
                "type": "completion",
                "analyzer": "standard",
                "search_analyzer": "standard",
                "preserve_separators": True,
                "preserve_position_increments": True,
                "max_input_length": 50,
            },
        }
    }


class VideoHintsResponse(BaseModel):
    hints: list[str]


class VideoResult(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    category: Optional[Any] = None  # list or str coming from ES
    views: int = 0
    thumbnail_url: Optional[str] = None
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    created_at: Optional[str] = None
    score: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


class VideoSearchResponse(BaseModel):
    results: list[VideoResult]
    total: int = Field(
        0, description="Total number of matching videos, for pagination."
    )
    offset: int = Field(0, description="Offset this page of results started at.")
    limit: int = Field(0, description="Page size this response was built with.")


class VideoHintQuery(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Partial query string for video title suggestions.",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Search query cannot be empty")
        return v.strip()


class VideoSearchRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, description="Search text input (e.g. 'funny cats')."
    )
    limit: int = Field(10, ge=1, le=50, description="Number of results to return.")
    offset: int = Field(
        0,
        ge=0,
        le=10_000,
        description="Number of results to skip, for paginating through matches.",
    )
    category: Optional[str] = Field(None, description="Filter by category name.")
    min_views: Optional[int] = Field(None, ge=0, description="Minimum number of views.")
    max_views: Optional[int] = Field(None, ge=0, description="Maximum number of views.")
    has_description: bool = Field(
        False, description="Filter to only include videos that have a description."
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Search query cannot be empty")
        return v.strip()

    @model_validator(mode="after")
    def check_views_range(self) -> "VideoSearchRequest":
        if (
            self.min_views is not None
            and self.max_views is not None
            and self.min_views > self.max_views
        ):
            raise ValueError("min_views cannot be greater than max_views")
        return self
