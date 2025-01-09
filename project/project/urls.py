import django_eventstream  # type: ignore [import-untyped]
from debug_toolbar.toolbar import debug_toolbar_urls  # type: ignore [import-untyped]
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("app.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/doc/", include("django.contrib.admindocs.urls")),
    path("admin/", admin.site.urls),
    path(
        "events/lobby/",
        include(django_eventstream.urls),
        kwargs={"channels": ["lobby"]},
    ),
    path(
        "events/top-sekrit-board-creation-channel/",
        include(django_eventstream.urls),
        kwargs={"channels": ["top-sekrit-board-creation-channel"]},
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
    # This gets events for one specific table.
    path(
        "events/table/<table_id>/",
        include(django_eventstream.urls),
        {"format-channels": ["table:{table_id}"]},
    ),
    path(
        "hand/<channel>/events/",  # "channel" is an integer -- the hand's primary key
        include(django_eventstream.urls),
    ),
    path(
        # public.  Messages are like {"joined": [16, 17], "split": []} or {"split": [16, 17], "joined": []}
        "events/partnerships/",
        include(django_eventstream.urls),
        kwargs={"channels": ["partnerships"]},
    ),
]

urlpatterns.extend(debug_toolbar_urls())
