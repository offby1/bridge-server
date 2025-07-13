# intended to be used after a call to "loaddata", in case the fixture is old and thus lacks some recently-added redundant fields.
from __future__ import annotations

from django.apps import apps
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        app_config = apps.get_app_config("app")
        for model in app_config.get_models():
            if (manager := getattr(model, "objects", None)) is None:
                self.stderr.write(f"No 'objects' attribute in {model=}; continuing")
                continue

            if (updater := getattr(manager, "_update_redundant_fields", None)) is None:
                self.stderr.write(
                    f"No '_update_redundant_fields' attribute in {manager=}; continuing"
                )
                continue

            updater()
            self.stdout.write(f"Updated {model} instances")
