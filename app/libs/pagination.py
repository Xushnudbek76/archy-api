from typing import TypedDict

from app.libs.errors import ApiError

PAGE_SIZE = 20


class Page[T](TypedDict):
    items: list[T]
    total: int
    nextPage: int | None


def page_query(query, *, archived=False):
    allowed = {"page", "archived"} if archived else {"page"}
    page = query.get("page", "1")
    if (
        set(query) - allowed
        or any(len(query.getlist(key)) != 1 for key in query)
        or not page.isascii()
        or not page.isdigit()
        or len(page) > 9
        or int(page) < 1
        or (archived and query.get("archived", "false") not in {"true", "false"})
    ):
        raise ApiError(400)
    return int(page)


def page_response[T](items: list[T], total: int, page: int) -> Page[T]:
    if page > max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE):
        raise ApiError(404)
    return {
        "items": items,
        "total": total,
        "nextPage": page + 1 if page * PAGE_SIZE < total else None,
    }
