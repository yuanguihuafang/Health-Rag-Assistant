"""
ASGI 入口（WebSocket + HTTP）
- 加载 Django ASGI 应用
- 注册 WebSocket 路由（hertz_demo 的 ChatConsumer / EchoConsumer）
"""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hertz_server_django.settings')

# 先导入 Django 以确保正确初始化，避免 AppRegistryNotReady 错误
from django.core.asgi import get_asgi_application

# 确保在导入其他模块之前初始化 Django ASGI 应用，避免 AppRegistryNotReady 错误
# 这也是 Django 官方推荐的做法
django_asgi_app = get_asgi_application()

# 导入其他模块，确保在 Django 初始化完成后加载 WebSocket 路由
from django.conf import settings
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# 这里导入 websocket 路由，确保在 Django 初始化完成后加载 WebSocket 路由，避免 AppRegistryNotReady 错误
from hertz_demo import routing as demo_routing

websocket_urlpatterns = demo_routing.websocket_urlpatterns

# 在开发环境下放宽Origin校验，便于第三方客户端（如 Apifox、wscat）调试
websocket_app = AuthMiddlewareStack(
    URLRouter(
        websocket_urlpatterns
    )
)

if getattr(settings, 'DEBUG', False):
    application = ProtocolTypeRouter({
        "http": django_asgi_app,
        "websocket": websocket_app,
    })
else:
    application = ProtocolTypeRouter({
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(websocket_app),
    })
