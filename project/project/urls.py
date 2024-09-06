import django_eventstream  # type: ignore
from debug_toolbar.toolbar import debug_toolbar_urls  # type: ignore
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("app.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path(
        "events/lobby/",
        include(django_eventstream.urls),
        kwargs={"channels": ["lobby"]},
    ),
    path(
        "events/player/<channel>/",
        include(django_eventstream.urls),
    ),
    # This gets all events for all tables.
    path(
        "events/all-tables/",
        include(django_eventstream.urls),
        kwargs={"channels": ["all-tables"]},
    ),
    # This gets a subset of table events.
    path(
        "events/table/<channel>/",  # "channel" is an integer -- the table's primary key
        include(django_eventstream.urls),
    ),
    path(
        # public.  Messages are like {"joined": [16, 17], "split": []} or {"split": [16, 17], "joined": []}
        "events/partnerships/",
        include(django_eventstream.urls),
        kwargs={"channels": ["partnerships"]},
    ),
] + debug_toolbar_urls()
