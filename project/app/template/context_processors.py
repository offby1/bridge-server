from django.conf import settings


def stick_that_gitlab_link_in_there_daddy_O(request):
    return {
        "gitlab_homepage": settings.GITLAB_HOMEPAGE,
    }


def stick_that_version_in_there_daddy_O(request):
    return {
        "GIT_SYMBOLIC_REF": settings.GIT_SYMBOLIC_REF,
        "VERSION": settings.VERSION,
    }


def stick_deployment_environment_in_there_daddy_O(request):
    return {"DEPLOYMENT_ENVIRONMENT": settings.DEPLOYMENT_ENVIRONMENT}
