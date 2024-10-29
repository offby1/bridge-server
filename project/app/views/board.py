from django.template.response import TemplateResponse


def board_list_view(request, *args, **kwargs):
    return TemplateResponse(request=request, template="board_list.html")
