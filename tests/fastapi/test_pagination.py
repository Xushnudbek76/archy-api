import pytest
from starlette.datastructures import QueryParams

from app.libs.errors import ApiError
from app.libs.pagination import page_query, page_response


@pytest.mark.parametrize(
    "query", ["page=0", "page=-1", "page=1&page=2", "unknown=x", "page=1000000000", "archived=yes"]
)
def test_page_query_rejects_invalid_parameters(query):
    with pytest.raises(ApiError):
        page_query(QueryParams(query), archived=True)


def test_page_envelope_and_empty_page():
    assert page_response([], 0, 1) == {"items": [], "total": 0, "nextPage": None}
    assert page_response(list(range(20)), 21, 1)["nextPage"] == 2
    with pytest.raises(ApiError) as error:
        page_response([], 21, 3)
    assert error.value.status == 404
