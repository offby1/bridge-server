from django.urls import path

from . import views

app_name = "app"

urlpatterns = [
    path("", views.home, name="home"),
    path("table/", views.TableListView.as_view(), name="table"),
    path("player/<pk>/", views.PlayerDetailView.as_view(), name="player"),
]
