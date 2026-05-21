from django.urls import path, include

urlpatterns = [
    path('', include('hertz_studio_django_log.urls.log_urls')),
]