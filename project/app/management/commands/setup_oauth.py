"""Management command to set up Google OAuth SocialApp."""

import os

from allauth.socialaccount.models import SocialApp  # type: ignore[import-untyped]
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Set up Google OAuth SocialApp and Site configuration"

    def handle(self, *args, **options):
        # Determine the site domain based on environment
        # Note: beta uses COMPOSE_PROFILES=beta but DEPLOYMENT_ENVIRONMENT="staging"
        compose_profiles = os.environ.get("COMPOSE_PROFILES", "")
        deployment_env = os.environ.get("DEPLOYMENT_ENVIRONMENT", "development")

        if deployment_env == "production" or compose_profiles == "prod":
            domain = "bridge.offby1.info"
            site_name = "Bridge Server"
        elif deployment_env == "staging" or compose_profiles == "beta":
            domain = "beta.bridge.offby1.info"
            site_name = "Bridge Server (Beta)"
        else:
            domain = "localhost:9000"
            site_name = "Bridge Server (Development)"

        # Get or update the current site
        site = Site.objects.get_current()
        site.domain = domain
        site.name = site_name
        site.save()
        self.stdout.write(self.style.SUCCESS(f"Site configured: {site.name} at {site.domain}"))

        # Check if OAuth credentials are configured
        from project.base_settings import GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET

        if not GOOGLE_OAUTH_CLIENT_ID or not GOOGLE_OAUTH_CLIENT_SECRET:
            self.stdout.write(
                self.style.WARNING(
                    "Google OAuth credentials not configured - skipping SocialApp creation"
                )
            )
            self.stdout.write(
                "To enable OAuth, set GOOGLE_OAUTH_CLIENT_ID_FILE and "
                "GOOGLE_OAUTH_CLIENT_SECRET_FILE environment variables"
            )
            return

        # Create or update the Google OAuth SocialApp
        app, created = SocialApp.objects.get_or_create(
            provider="google",
            defaults={
                "name": "Google",
                "client_id": GOOGLE_OAUTH_CLIENT_ID.strip() if GOOGLE_OAUTH_CLIENT_ID else "",
                "secret": GOOGLE_OAUTH_CLIENT_SECRET.strip() if GOOGLE_OAUTH_CLIENT_SECRET else "",
            },
        )

        # Update existing app if credentials changed
        if not created:
            updated = False
            new_client_id = GOOGLE_OAUTH_CLIENT_ID.strip() if GOOGLE_OAUTH_CLIENT_ID else ""
            new_secret = GOOGLE_OAUTH_CLIENT_SECRET.strip() if GOOGLE_OAUTH_CLIENT_SECRET else ""

            if app.client_id != new_client_id:
                app.client_id = new_client_id
                updated = True
            if app.secret != new_secret:
                app.secret = new_secret
                updated = True

            if updated:
                app.save()
                self.stdout.write(self.style.SUCCESS(f"Updated existing SocialApp: {app.name}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"SocialApp already configured: {app.name}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Created SocialApp: {app.name}"))

        # Link to the site if not already linked
        if site not in app.sites.all():
            app.sites.add(site)
            self.stdout.write(self.style.SUCCESS(f"Linked SocialApp to site: {site.domain}"))
        else:
            self.stdout.write(f"SocialApp already linked to site: {site.domain}")

        self.stdout.write(self.style.SUCCESS("\nGoogle OAuth configuration complete!"))
        self.stdout.write(
            f"Users can now sign in with Google at https://{site.domain}/accounts/google/login/"
        )
