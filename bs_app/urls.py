from django.urls import path

from . import views

app_name = "bs_app"

urlpatterns = [
    path("", views.homepage, name="index"),
]
