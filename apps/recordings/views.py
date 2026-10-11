from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import BaseParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.errors import ClientError
from apps.core.pagination import WorkspacePagination
from apps.recordings import serializers, services
from apps.recordings.models import Recording, Upload
from apps.recordings.playback import audio_response


def page_number(request):
    query = request.query_params
    page = query.get("page", "1")
    if (
        set(query) - {"page"}
        or any(len(query.getlist(key)) != 1 for key in query)
        or not page.isascii()
        or not page.isdigit()
        or len(page) > 9
        or int(page) < 1
    ):
        raise ValidationError("Invalid list query")


class UploadsView(APIView):
    def get(self, request):
        page_number(request)
        uploads = (
            Upload.objects.filter(course__owner=request.user, status=Upload.Status.UPLOADING)
            .select_related("course", "recording")
            .order_by("-created_at", "-id")
        )
        pagination = WorkspacePagination()
        items = pagination.paginate_queryset(uploads, request)
        return pagination.get_paginated_response(
            serializers.UploadSerializer(items, many=True).data
        )

    def post(self, request):
        data = serializers.UploadRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload, created = services.admit_upload(request.user, data.validated_data)
        return Response(serializers.UploadSerializer(upload).data, status=201 if created else 200)


class UploadView(APIView):
    def get(self, request, upload_id):
        return Response(
            serializers.UploadSerializer(services.owned_upload(request.user, upload_id)).data
        )


class ChunkParser(BaseParser):
    media_type = "application/octet-stream"

    def parse(self, stream, media_type=None, parser_context=None):
        data = stream.read(services.CHUNK_BYTES + 1)
        if len(data) > services.CHUNK_BYTES:
            raise ClientError(413, "invalid_chunk", "Upload a chunk of at most 4 MiB.")
        return data


class ChunkView(APIView):
    parser_classes = [ChunkParser]

    def patch(self, request, upload_id):
        services.owned_upload(request.user, upload_id)
        offset = request.headers.get("Upload-Offset", "")
        if not offset.isascii() or not offset.isdigit() or len(offset) > 16:
            raise ValidationError("Invalid offset")
        upload = services.receive_chunk(request.user, upload_id, int(offset), request.data)
        return Response(serializers.UploadSerializer(upload).data)


class CompleteUploadView(APIView):
    def post(self, request, upload_id):
        data = serializers.EmptySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = services.complete_upload(request.user, upload_id)
        if upload.status == Upload.Status.FAILED:
            raise ClientError(400, upload.error_code, services.ERRORS[upload.error_code])
        return Response(serializers.UploadSerializer(upload).data)


class CancelUploadView(APIView):
    def post(self, request, upload_id):
        data = serializers.EmptySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(
            serializers.UploadSerializer(services.cancel_upload(request.user, upload_id)).data
        )


class RecordingsView(APIView):
    def get(self, request):
        page_number(request)
        recordings = (
            Recording.objects.filter(course__owner=request.user)
            .select_related("course")
            .order_by("-created_at", "-id")
        )
        pagination = WorkspacePagination()
        items = pagination.paginate_queryset(recordings, request)
        return pagination.get_paginated_response(
            serializers.RecordingSerializer(items, many=True).data
        )


class AudioView(APIView):
    def get(self, request, recording_id):
        recording = get_object_or_404(Recording, pk=recording_id, course__owner=request.user)
        return audio_response(recording, request)
