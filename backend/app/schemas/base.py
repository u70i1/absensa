"""Shared schema shapes; object-specific schemas live in their own modules."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")
SuccessT = TypeVar("SuccessT")
FailureT = TypeVar("FailureT")


class OrmResponseBase(BaseModel):
    """Allow response models to read fields from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class PaginationQueryBase(BaseModel):
    """Page-based pagination shared by list endpoints."""

    limit: int = Field(10, ge=1, le=100)
    page: int = Field(1, ge=1)


class BulkDeleteRequestBase(BaseModel):
    """IDs to delete in a single bulk operation."""

    ids: list[int]


class BulkSuccessResponseBase(BaseModel, Generic[ItemT]):
    """Successful item and its zero-based index in the request."""

    index: int
    item: ItemT


class BulkFailureResponseBase(BulkSuccessResponseBase[ItemT], Generic[ItemT]):
    """Failed item with the reason it could not be processed."""

    error: str


class BulkResponseBase(BaseModel, Generic[SuccessT, FailureT]):
    """Results of a bulk create or update operation."""

    succeeded: list[SuccessT]
    failed: list[FailureT]
