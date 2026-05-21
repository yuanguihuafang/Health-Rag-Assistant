from django.urls import path, include

app_name = 'hertz_studio_django_auth'

urlpatterns = [
    # 认证相关API
    path('auth/', include('hertz_studio_django_auth.urls.auth_urls')),
    
    # 管理相关API
    path('', include('hertz_studio_django_auth.urls.management_urls')),
]