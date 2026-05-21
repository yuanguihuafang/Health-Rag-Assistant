"""
WSGI 入口（HTTP 部署入口）
- 加载 Django WSGI 应用，供 Gunicorn / uWSGI 等服务器调用
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hertz_server_django.settings')

application = get_wsgi_application()
