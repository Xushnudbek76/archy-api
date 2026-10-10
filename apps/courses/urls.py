from django.urls import path

from apps.courses.views import ArchiveCourseView, CoursesView, CourseView

urlpatterns = [
    path("courses", CoursesView.as_view()),
    path("courses/<uuid:course_id>", CourseView.as_view()),
    path("courses/<uuid:course_id>/archive", ArchiveCourseView.as_view()),
]
