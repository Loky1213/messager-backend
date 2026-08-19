from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    TokenRefreshView,
    LogoutView,
    MeView,
    UpdateProfileView,
    UserListView,
)

urlpatterns = [
    # Authentication
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),

    # Profile
    path("me/", MeView.as_view(), name="me"),
    path("profile/update/", UpdateProfileView.as_view(), name="update-profile"),

    # Users
    path("list/", UserListView.as_view(), name="user-list"),
]