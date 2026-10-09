from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts import serializers, services


@method_decorator(csrf_protect, name="dispatch")
class PublicAuthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]

    def validated(self, request, serializer_class):
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(PublicAuthView):
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class SignupView(PublicAuthView):
    throttle_scope = "signup"

    def post(self, request):
        data = self.validated(request, serializers.SignupSerializer)
        services.signup(data["email"], data["password"], data.get("displayName", ""))
        return Response({"message": "Check your email for the next step."}, status=202)


class ConfirmationView(PublicAuthView):
    def post(self, request):
        data = self.validated(request, serializers.ConfirmationSerializer)
        try:
            services.confirm_email(data["token"])
        except services.InvalidToken:
            raise ValidationError("Invalid confirmation") from None
        return Response({"message": "Email confirmed."})


class LoginView(PublicAuthView):
    throttle_scope = "login"

    def post(self, request):
        data = self.validated(request, serializers.LoginSerializer)
        user = authenticate(request, username=data["email"], password=data["password"])
        if user is None:
            raise AuthenticationFailed("Invalid credentials")
        login(request, user)
        return Response(serializers.UserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({"message": "Signed out."})


class PasswordResetView(PublicAuthView):
    throttle_scope = "reset"

    def post(self, request):
        data = self.validated(request, serializers.EmailSerializer)
        services.request_password_reset(data["email"])
        return Response({"message": "Check your email for the next step."}, status=202)


class ResetConfirmationView(PublicAuthView):
    def post(self, request):
        data = self.validated(request, serializers.ResetConfirmationSerializer)
        try:
            services.reset_password(data["uid"], data["token"], data["password"])
        except services.InvalidToken:
            raise ValidationError("Invalid password reset") from None
        return Response({"message": "Password updated."})


class CurrentUserView(APIView):
    def get(self, request):
        return Response(serializers.UserSerializer(request.user).data)
