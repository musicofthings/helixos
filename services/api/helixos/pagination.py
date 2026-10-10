"""Offset pagination for list endpoints.

Responses stay plain JSON arrays so existing clients keep working. Page
metadata travels in headers: ``X-Total-Count`` always, and ``X-Next-Offset``
when more items remain.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

from fastapi import Query, Response

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

PAGINATION_HEADERS = ["X-Total-Count", "X-Next-Offset"]


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> PageParams:
    """FastAPI dependency parsing ``limit`` / ``offset`` query parameters."""
    return PageParams(limit=limit, offset=offset)


def paginate(items: Sequence[T], page: PageParams, response: Response) -> list[T]:
    """Slice ``items`` and describe the page in response headers."""
    total = len(items)
    end = page.offset + page.limit
    response.headers["X-Total-Count"] = str(total)
    if end < total:
        response.headers["X-Next-Offset"] = str(end)
    return list(items[page.offset : end])
