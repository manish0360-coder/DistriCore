from django.urls import path

from webadmin import views

app_name = "webadmin"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard_view, name="dashboard"),
]
