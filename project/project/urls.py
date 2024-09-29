import django_eventstream  # type: ignore
from debug_toolbar.toolbar import debug_toolbar_urls  # type: ignore
from django.contrib import admin
from django.contrib.auth.models import User
from django.urls import include, path
from rest_framework import routers, serializers, viewsets  # type: ignore


# Serializers define the API representation.
class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ("url", "username", "email", "is_staff")


# ViewSets define the view behavior.
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


router = routers.DefaultRouter()
router.register(r"users", UserViewSet)


urlpatterns = [
    path("", include("app.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/doc/", include("django.contrib.admindocs.urls")),
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),
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
