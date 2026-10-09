from django.urls import path

from apps.core import views

urlpatterns = [path("v1/health/live", views.live), path("v1/health/ready", views.ready)]
