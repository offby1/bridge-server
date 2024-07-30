from django.urls import path

from . import views

app_name = "app"

urlpatterns = [
    path("", views.duh, name="duh"),
    path("club/", views.club, name="club"),
    path("table/", views.TableListView.as_view(), name="table"),
    path("player/<pk>/", views.PlayerDetailView.as_view(), name="player"),
]
