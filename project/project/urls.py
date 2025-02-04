import django_eventstream  # type: ignore [import-untyped]
from debug_toolbar.toolbar import debug_toolbar_urls  # type: ignore [import-untyped]
from django.contrib import admin
from django.http import HttpResponseServerError
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
        "events/hand/<hand_id>/",
        include(django_eventstream.urls),
        {"format-channels": ["hand:{hand_id}"]},
    ),
    path(
        # public.  Messages are like {"joined": [16, 17], "split": []} or {"split": [16, 17], "joined": []}
        "events/partnerships/",
        include(django_eventstream.urls),
        kwargs={"channels": ["partnerships"]},
    ),
]

urlpatterns.extend(debug_toolbar_urls())


def my_server_error(request, template_name="500.html"):
    return HttpResponseServerError("""
<!doctype html>
<html lang="en">
<head>
  <title>Server Error (500)</title>
</head>
<body>
  <h1>Server Error (500)</h1><p></p>
    <small>Yipe!</small>
</body>
</html>
    """)


handler500 = my_server_error
