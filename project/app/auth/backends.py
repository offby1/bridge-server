import logging

from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class SkeletonKeyBackend(BaseBackend):
    def get_user(self, user_id):
        return User.objects.get_by_natural_key(user_id)

    def authenticate(self, request, **credentials):
        username = credentials.get("username")
        u = self.get_user(username)
        if u is None:
            logger.warning("No user named %s; returning None", username)

        p = credentials.get("password").rstrip()
        if p != settings.API_SKELETON_KEY:
            logger.warning("Password isn't the sekret API_SKELETON_KEY; returning None")
            return None

        logger.info("Yay, logging in %s with sekret API_SKELETON_KEY", u)
        return u
