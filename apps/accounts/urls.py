from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("auth/csrf", views.CsrfView.as_view()),
    path("auth/signup", views.SignupView.as_view()),
    path("auth/confirm-email", views.ConfirmationView.as_view()),
    path("auth/login", views.LoginView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("auth/password-reset", views.PasswordResetView.as_view()),
    path("auth/password-reset/confirm", views.ResetConfirmationView.as_view()),
    path("users/me", views.CurrentUserView.as_view()),
]
