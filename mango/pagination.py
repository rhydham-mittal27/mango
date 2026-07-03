"""mango/pagination.py

A paginated-response envelope, so a list endpoint returns `{"items": [...],
"total": N, "limit": L, "offset": O}` instead of a bare list with no way
for a client to know if there's more — a small thing every list endpoint
in a real app eventually needs and re-implements slightly differently.

Classes (1):
    - Page: generic paginated response schema — items + total + limit/offset.

Functions: none.
"""
from collections.abc import Sequence
from typing import Generic, TypeVar

from mango.schema import Schema

ItemT = TypeVar("ItemT")  # the item type a given Page is parametrized over


class Page(Schema, Generic[ItemT]):
    """Paginated response envelope: `Page[ThingRead]`.

        Page(items=rows, total=42, limit=50, offset=0)

    `total` is the full row count regardless of `limit`/`offset`, so a
    client can compute whether more pages exist (`offset + len(items) <
    total`) without a second request.
    """

    items: Sequence[ItemT]  # the rows for this page
    total: int  # total matching row count across all pages, not just this one
    limit: int  # the page size that was requested
    offset: int  # how many rows were skipped before this page started
