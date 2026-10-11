from django.urls import path

from apps.recordings import views

urlpatterns = [
    path("uploads", views.UploadsView.as_view()),
    path("uploads/<uuid:upload_id>", views.UploadView.as_view()),
    path("uploads/<uuid:upload_id>/chunks", views.ChunkView.as_view()),
    path("uploads/<uuid:upload_id>/complete", views.CompleteUploadView.as_view()),
    path("uploads/<uuid:upload_id>/cancel", views.CancelUploadView.as_view()),
    path("recordings", views.RecordingsView.as_view()),
    path("recordings/<uuid:recording_id>/audio", views.AudioView.as_view()),
]
