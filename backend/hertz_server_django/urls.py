"""
Hertz Server Django 主路由
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from . import local_auth_views, local_captcha_views, views

urlpatterns = [
    # API documentation routes
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # 首页路由
    path("", views.index, name="index"),
    # 本项目覆盖官方验证码图片生成，保持验证缓存兼容，但提升登录页可读性
    path(
        "api/captcha/generate/",
        local_captcha_views.generate_captcha,
        name="local_captcha_generate",
    ),
    path(
        "api/captcha/refresh/",
        local_captcha_views.refresh_captcha,
        name="local_captcha_refresh",
    ),
    # Hertz Captcha routes
    path("api/captcha/", include("hertz_studio_django_captcha.urls")),
    # 本项目覆盖官方重置密码接口，避免官方 serializer 漏字段导致 500
    path(
        "api/auth/password/reset/email/",
        local_auth_views.reset_password_email,
        name="local_reset_password_email",
    ),
    path(
        "api/auth/password/reset/code/",
        local_auth_views.send_reset_password_code,
        name="local_send_reset_password_code",
    ),
    path(
        "api/auth/password/reset/",
        local_auth_views.reset_password,
        name="local_reset_password",
    ),
    # Hertz Auth routes
    path("api/", include("hertz_studio_django_auth.urls")),
    # Demo app routes
    path("", include("hertz_demo.urls")),
    # Hertz System Monitor routes
    path("api/system/", include("hertz_studio_django_system_monitor.urls")),
    # Hertz Log routes
    path("api/log/", include("hertz_studio_django_log.urls")),
    # Hertz Notice routes
    path("api/notice/", include("hertz_studio_django_notice.urls")),
    # ===========在下面添加你需要的路由===========
    # 健康RAG问答助手（本地 app）
    path("api/health-rag/", include("health_rag_assistant.urls")),
]

# 在开发环境下提供媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(
        settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0]
    )
