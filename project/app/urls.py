from django.urls import path

from . import views

app_name = "app"

urlpatterns = [
    path("", views.duh, name="duh"),
    path("club/", views.club, name="club"),
]
