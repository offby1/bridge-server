from django.conf import settings


def stick_that_version_in_there_daddy_O(request):
    return {
        "VERSION": settings.VERSION,
        "GIT_SYMBOLIC_REF": settings.GIT_SYMBOLIC_REF,
    }


def stick_deployment_environment_in_there_daddy_O(request):
    return {"DEPLOYMENT_ENVIRONMENT": settings.DEPLOYMENT_ENVIRONMENT}
