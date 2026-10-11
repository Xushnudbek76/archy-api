from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class WorkspacePagination(PageNumberPagination):
    page_size = 20

    def get_paginated_response(self, data):
        return Response(
            {
                "items": data,
                "total": self.page.paginator.count,
                "nextPage": self.page.next_page_number() if self.page.has_next() else None,
            }
        )
