from django.contrib import admin
from django.urls import include, path

from apps.core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("v1/", include("apps.accounts.urls")),
    path("v1/", include("apps.courses.urls")),
    path("v1/health/live", views.live),
    path("v1/health/ready", views.ready),
]
