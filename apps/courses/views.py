from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import WorkspacePagination
from apps.core.serializers import StrictSerializer
from apps.courses import serializers, services
from apps.courses.models import Course


class CoursesView(APIView):
    def get(self, request):
        query = request.query_params
        if (
            set(query) - {"page", "archived"}
            or any(len(query.getlist(key)) != 1 for key in query)
            or query.get("archived", "false") not in {"true", "false"}
            or not query.get("page", "1").isascii()
            or not query.get("page", "1").isdigit()
            or len(query.get("page", "1")) > 9
            or int(query.get("page", "1")) < 1
        ):
            raise ValidationError("Invalid course query")
        courses = Course.objects.filter(
            owner=request.user, archived_at__isnull=query.get("archived") != "true"
        ).order_by("-created_at", "-id")
        pagination = WorkspacePagination()
        page = pagination.paginate_queryset(courses, request)
        return pagination.get_paginated_response(serializers.CourseSerializer(page, many=True).data)

    def post(self, request):
        data = serializers.CourseTitleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        course = services.create_course(request.user, data.validated_data["title"])
        return Response(serializers.CourseSerializer(course).data, status=201)


class CourseView(APIView):
    def patch(self, request, course_id):
        data = serializers.CourseTitleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        course = services.rename_course(request.user, course_id, data.validated_data["title"])
        return Response(serializers.CourseSerializer(course).data)


class ArchiveCourseView(APIView):
    def post(self, request, course_id):
        data = StrictSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        course = services.archive_course(request.user, course_id)
        return Response(serializers.CourseSerializer(course).data)
