from django.http import JsonResponse

from hertz_studio_django_auth.utils.decorators import no_login_required


@no_login_required
def index(request):
    return JsonResponse({"message": "身体健康智慧问答助手 API 运行中", "status": "ok"})