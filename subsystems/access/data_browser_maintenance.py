"""
File: data_browser_maintenance.py
Description: 編排 bounded 唯讀 Data Browser archive query。
"""


def query_data_browser_source(
    repository,
    source_id: str,
    *,
    limit: int,
    after: str | None,
    query: str | None,
):
    """Run one bounded read-only source query without exposing table identifiers."""
    if limit < 1 or limit > 100:
        raise ValueError("limit_invalid")
    return repository.query_page(
        source_id,
        limit=limit,
        after=after,
        query=query,
    )
