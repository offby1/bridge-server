from django.contrib import admin
from django.urls import include, path
from debug_toolbar.toolbar import debug_toolbar_urls

import app

urlpatterns = [
    path("", include("app.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/profile/", app.views.profile),
    path("admin/", admin.site.urls),
] + debug_toolbar_urls()
