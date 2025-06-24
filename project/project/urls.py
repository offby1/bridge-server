import json
import pathlib

import django_eventstream  # type: ignore [import-untyped]
from debug_toolbar.toolbar import debug_toolbar_urls  # type: ignore [import-untyped]
from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, HttpResponseServerError
from django.urls import include, path


# https://chromium.googlesource.com/devtools/devtools-frontend/+/main/docs/ecosystem/automatic_workspace_folders.md
def automatic_workspace_folders_view(request: HttpRequest) -> HttpResponse:
    if not settings.DEBUG:
        return HttpResponseNotFound()

    return HttpResponse(
        json.dumps(
            {
                "workspace": {
                    "root": str(pathlib.Path(__name__).parent.resolve()),
                    # I just made this UUID up.
                    "uuid": "2d970d3e-495a-4aeb-8298-b5f5529885ed",
                }
            }
        ),
        headers={"Content-Type": "text/json"},
    )


urlpatterns = [
    path("", include("app.urls")),
    path("", include("django_prometheus.urls")),
    path(".well-known/appspecific/com.chrome.devtools.json", automatic_workspace_folders_view),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/doc/", include("django.contrib.admindocs.urls")),
    path("admin/", admin.site.urls),
    path(
        "events/lobby/",
        include(django_eventstream.urls),
        kwargs={"channels": ["lobby"]},
    ),
    path(
        "events/chat/player-to-player/<channel>/",
        include(django_eventstream.urls),
    ),
    path(
        "events/player/html/hand/<player_id>/",
        include(django_eventstream.urls),
        {"format-channels": ["player:html:hand:{player_id}"]},
    ),
    path(
        "events/player/json/<player_id>/",
        include(django_eventstream.urls),
        {"format-channels": ["player:json:{player_id}"]},
    ),
    # This gets events for one specific table.
    path(
        "events/table/html/<hand_id>/",
        include(django_eventstream.urls),
        {"format-channels": ["table:html:{hand_id}"]},
    ),
    # This gets all events for all tables.
    path(
        "events/all-tables/",
        include(django_eventstream.urls),
        kwargs={"channels": ["all-tables"]},
    ),
    path("tz_detect/", include("tz_detect.urls")),
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
