from django.http import HttpRequest, HttpResponse


def hand_list_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("whatchoo lookin' at")
