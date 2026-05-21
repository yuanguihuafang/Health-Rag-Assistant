"""
Django 全局配置
- 数据库、中间件、INSTALLED_APPS
- LLM 模型配置（Ollama / OpenAI 兼容）
- ASR 语音识别配置、Redis 缓存
"""
import os
from pathlib import Path

from decouple import Config, RepositoryEnv, config


# 修复DRF的ip_address_validators函数
def fix_drf_ip_validators():
    """
    修复DRF的ip_address_validators函数返回值问题
    """
    try:
        from rest_framework import fields

        # 保存原始函数
        original_ip_address_validators = fields.ip_address_validators

        def fixed_ip_address_validators(protocol, unpack_ipv4):
            """
            修复后的ip_address_validators函数，确保返回两个值
            """
            validators = original_ip_address_validators(protocol, unpack_ipv4)
            # 如果只返回了validators，添加默认的error_message
            if isinstance(validators, list):
                return validators, "Enter a valid IP address."
            else:
                # 如果已经返回了两个值，直接返回
                return validators

        # 应用猴子补丁
        fields.ip_address_validators = fixed_ip_address_validators

    except ImportError:
        # 如果DRF未安装，忽略错误
        pass


# 应用修复
fix_drf_ip_validators()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_ENV_CONFIG = Config(RepositoryEnv(str(BASE_DIR / ".env")))


# 快速开发配置 - 生产环境需调整
# 参考：https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# 安全警告：生产环境请替换 SECRET_KEY！
SECRET_KEY = config(
    "SECRET_KEY",
    default="django-insecure-0a1bx*8!97l^4z#ml#ufn_*9ut*)zlso$*k-g^h&(2=p@^51md",
)

# 安全警告：生产环境不要开启 DEBUG！
DEBUG = config("DEBUG", default=True, cast=bool)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

# 数据库引擎：sqlite / mysql
# 优先用 DB_ENGINE 环境变量，向后兼容 USE_REDIS_AS_DB
DB_ENGINE = config("DB_ENGINE", default=None)
USE_REDIS_AS_DB = config("USE_REDIS_AS_DB", default=True, cast=bool)
if DB_ENGINE is None:
    DB_ENGINE = "sqlite" if USE_REDIS_AS_DB else "mysql"

# 应用定义

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party apps
    "rest_framework",
    "corsheaders",
    "channels",
    "drf_spectacular",
    # 必备注册的app，不要删
    "hertz_demo",  # 初始化演示模块
    "hertz_studio_django_captcha",  # 验证码模块
    "hertz_studio_django_auth",  # 权限模块
    "hertz_studio_django_system_monitor",  # 系统监测模块
    "hertz_studio_django_log",  # 日志管理模块
    "hertz_studio_django_notice",  # 通知模块
    # ======在下面导入你需要的app======
    "health_rag_assistant",  # 健康RAG问答助手（本地app）
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "hertz_studio_django_auth.utils.middleware.AuthMiddleware",  # 权限认证中间件
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hertz_server_django.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "hertz_server_django.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "data/db.sqlite3",
        }
    }
    # Use Redis-backed sessions when on SQLite (optional, keeps prior behavior)
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"
elif DB_ENGINE == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": config("DB_NAME", default="hertz_server"),
            "USER": config("DB_USER", default="root"),
            "PASSWORD": config("DB_PASSWORD", default="root"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }
else:
    # Fallback to SQLite for unexpected values
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "data/db.sqlite3",
        }
    }

# Redis
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "zh-hans"

TIME_ZONE = "Asia/Shanghai"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Media files (User uploaded files)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework configuration
# 使用自定义AuthMiddleware进行认证，不使用DRF的认证和权限系统
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [],  # 不使用DRF认证类
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",  # 所有接口默认允许访问，由AuthMiddleware控制权限
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M:%S",
}

# Spectacular (OpenAPI 3.0) configuration
SPECTACULAR_SETTINGS = {
    "TITLE": "Hertz Server API",
    "DESCRIPTION": "API documentation for Hertz Server Django project",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/",
}

# CORS configuration
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=False, cast=bool)

# Captcha settings
HERTZ_CAPTCHA_LENGTH = config("HERTZ_CAPTCHA_LENGTH", default=4, cast=int)
HERTZ_CAPTCHA_WIDTH = config("HERTZ_CAPTCHA_WIDTH", default=172, cast=int)
HERTZ_CAPTCHA_HEIGHT = config("HERTZ_CAPTCHA_HEIGHT", default=54, cast=int)
HERTZ_CAPTCHA_FONT_SIZE = config("HERTZ_CAPTCHA_FONT_SIZE", default=36, cast=int)
HERTZ_CAPTCHA_TIMEOUT = config("HERTZ_CAPTCHA_TIMEOUT", default=300, cast=int)
HERTZ_CAPTCHA_BACKGROUND_COLOR = config(
    "HERTZ_CAPTCHA_BACKGROUND_COLOR", default="#ffffff"
)
HERTZ_CAPTCHA_FOREGROUND_COLOR = config(
    "HERTZ_CAPTCHA_FOREGROUND_COLOR", default="#000000"
)
HERTZ_CAPTCHA_NOISE_LEVEL = config(
    "HERTZ_CAPTCHA_NOISE_LEVEL", default=0.003, cast=float
)
HERTZ_CAPTCHA_REDIS_KEY_PREFIX = config(
    "HERTZ_CAPTCHA_REDIS_KEY_PREFIX", default="hertz_captcha:"
)

CAPTCHA_IMAGE_SIZE = (
    config("CAPTCHA_IMAGE_SIZE_WIDTH", default=120, cast=int),
    config("CAPTCHA_IMAGE_SIZE_HEIGHT", default=50, cast=int),
)
CAPTCHA_LENGTH = config("CAPTCHA_LENGTH", default=4, cast=int)
CAPTCHA_TIMEOUT = config("CAPTCHA_TIMEOUT", default=5, cast=int)  # minutes
CAPTCHA_FONT_SIZE = config("CAPTCHA_FONT_SIZE", default=40, cast=int)
CAPTCHA_BACKGROUND_COLOR = config("CAPTCHA_BACKGROUND_COLOR", default="#ffffff")
CAPTCHA_FOREGROUND_COLOR = config("CAPTCHA_FOREGROUND_COLOR", default="#000000")
# 验证码词典文件路径
CAPTCHA_WORDS_DICTIONARY = str(BASE_DIR / "captcha_words.txt")
# 验证码挑战函数配置
CAPTCHA_CHALLENGE_FUNCT = "captcha.helpers.random_char_challenge"  # 默认使用随机字符
# 数学验证码配置
CAPTCHA_MATH_CHALLENGE_OPERATOR = "+-*"
# 验证码噪声和过滤器
CAPTCHA_NOISE_FUNCTIONS = (
    "captcha.helpers.noise_arcs",
    "captcha.helpers.noise_dots",
)
CAPTCHA_FILTER_FUNCTIONS = ("captcha.helpers.post_smooth",)

# Email configuration
EMAIL_BACKEND = ROOT_ENV_CONFIG(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = ROOT_ENV_CONFIG("EMAIL_HOST", default="smtp.qq.com")
EMAIL_PORT = ROOT_ENV_CONFIG("EMAIL_PORT", default=465, cast=int)
EMAIL_USE_SSL = ROOT_ENV_CONFIG("EMAIL_USE_SSL", default=True, cast=bool)
EMAIL_USE_TLS = ROOT_ENV_CONFIG("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_HOST_USER = ROOT_ENV_CONFIG("EMAIL_HOST_USER", default="563161210@qq.com")
EMAIL_HOST_PASSWORD = ROOT_ENV_CONFIG("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = ROOT_ENV_CONFIG("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER)

# 注册邮箱验证码开关（0=关闭，1=开启）
REGISTER_EMAIL_VERIFICATION = config("REGISTER_EMAIL_VERIFICATION", default=0, cast=int)

# Channels configuration for WebSocket support
ASGI_APPLICATION = "hertz_server_django.asgi.application"

# Channel layers configuration
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config("REDIS_URL", default="redis://127.0.0.1:6379/2")],
        },
    },
}

# 自定义用户模型
AUTH_USER_MODEL = "hertz_studio_django_auth.HertzUser"

# JWT配置
JWT_SECRET_KEY = config("JWT_SECRET_KEY", default=SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_LIFETIME = config(
    "JWT_ACCESS_TOKEN_LIFETIME", default=60 * 60 * 24, cast=int
)  # 24小时
JWT_REFRESH_TOKEN_LIFETIME = config(
    "JWT_REFRESH_TOKEN_LIFETIME", default=60 * 60 * 24 * 7, cast=int
)  # 7天

# 权限系统配置
HERTZ_AUTH_SETTINGS = {
    "SUPER_ADMIN_PERMISSIONS": ["*"],  # 超级管理员拥有所有权限
    "DEFAULT_PERMISSIONS": [],  # 默认权限
}

# AuthMiddleware配置 - 不需要登录验证的URL模式（支持正则表达式）
NO_AUTH_PATTERNS = config(
    "NO_AUTH_PATTERNS",
    default=r"^/api/auth/login/?$,^/api/auth/register/?$,^/api/auth/email/code/?$,^/api/auth/send-email-code/?$,^/api/auth/password/reset/?$,^/api/auth/password/reset/email/?$,^/api/auth/password/reset/code/?$,^/api/captcha/.*$,^/api/docs/.*$,^/api/redoc/.*$,^/api/schema/.*$,^/admin/.*$,^/static/.*$,^/media/.*$,^/demo/.*$,^/websocket/.*$,^/api/system/.*$,^/api/health-rag/health/?$",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

# 密码加密配置
PASSWORD_HASHERS = [
    "hertz_studio_django_utils.crypto.MD5PasswordHasher",  # 使用MD5加密
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# Health RAG 语音识别（ASR）配置
HEALTH_RAG_ASR_WS_URL = config(
    "HEALTH_RAG_ASR_WS_URL",
    default="wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
)
HEALTH_RAG_ASR_APP_KEY = config(
    "HEALTH_RAG_ASR_APP_KEY",
    default="",
)
HEALTH_RAG_ASR_ACCESS_KEY = config(
    "HEALTH_RAG_ASR_ACCESS_KEY",
    default="",
)
HEALTH_RAG_ASR_RESOURCE_ID = config(
    "HEALTH_RAG_ASR_RESOURCE_ID",
    default="volc.bigasr.sauc.duration",
)
HEALTH_RAG_ASR_DEFAULT_LANGUAGE = config(
    "HEALTH_RAG_ASR_DEFAULT_LANGUAGE",
    default="zh-CN",
)
HEALTH_RAG_ASR_TIMEOUT = config(
    "HEALTH_RAG_ASR_TIMEOUT",
    default=30,
    cast=int,
)

# 健康 RAG LLM 配置
# 使用显式 .env 仓库读取，避免从其他工作目录启动时回落到 llm_service.py 的本地 Ollama 默认值。
OLLAMA_BASE_URL = ROOT_ENV_CONFIG("OLLAMA_BASE_URL", default="http://localhost:11434")
HEALTH_RAG_API_KEY = ROOT_ENV_CONFIG("HEALTH_RAG_API_KEY", default="")
HEALTH_RAG_MODEL_NAME = ROOT_ENV_CONFIG(
    "HEALTH_RAG_MODEL_NAME",
    default=ROOT_ENV_CONFIG("AI_MODEL_NAME", default="deepseek-r1:1.5b"),
)
HEALTH_RAG_LLM_TIMEOUT = ROOT_ENV_CONFIG(
    "HEALTH_RAG_LLM_TIMEOUT",
    default=60,
    cast=int,
)
HEALTH_RAG_RECOMMEND_MAX_CHUNKS = ROOT_ENV_CONFIG(
    "HEALTH_RAG_RECOMMEND_MAX_CHUNKS",
    default=600,
    cast=int,
)
