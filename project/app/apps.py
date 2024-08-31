from django.apps import AppConfig


class AppConfig(AppConfig):  # type: ignore
    default_auto_field = "django.db.models.BigAutoField"
    name = "app"
