import django_eventstream
from debug_toolbar.toolbar import debug_toolbar_urls
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("app.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path("events/lobby/", include(django_eventstream.urls), {"channels": ["lobby"]}),
    path("events/player/<pk>", include(django_eventstream.urls)),
] + debug_toolbar_urls()
