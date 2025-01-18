from django.apps import AppConfig
from django.db.models.signals import pre_delete


class AppConfig(AppConfig):  # type: ignore
    default_auto_field = "django.db.models.BigAutoField"
    name = "app"

    def ready(self):
        from .models.hand import Hand

        pre_delete.connect(Hand.untaint_board, sender="app.Hand")
