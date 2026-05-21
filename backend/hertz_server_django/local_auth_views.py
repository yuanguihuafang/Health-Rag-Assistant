import random

from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view

from hertz_studio_django_auth.models import HertzUser
from hertz_studio_django_utils.email import EmailService
from hertz_studio_django_utils.responses.HertzResponse import HertzResponse


RESET_CODE_TYPE = "reset_password"


def _smtp_is_configured() -> bool:
    user = str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    password = str(getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip()
    placeholders = {"", "your_email@qq.com", "your_email_password", "your_163_smtp_authorization_code"}
    return user not in placeholders and password not in placeholders


def _password_is_valid(password: str) -> tuple[bool, str]:
    if len(password) < 6:
        return False, "密码长度不能少于6位"
    if len(password) > 128:
        return False, "密码长度不能超过128位"
    return True, ""


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not local or not domain:
        return ""
    if len(local) <= 2:
        visible = local[:1]
    else:
        visible = f"{local[:2]}{local[-1:]}"
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"


def _get_active_user_by_username(username: str):
    if not username:
        return None
    return HertzUser.objects.filter(username=username, status=1).first()


@api_view(["POST"])
def reset_password_email(request):
    """按账号返回绑定邮箱脱敏值，避免忘记密码时暴露完整邮箱或允许手动换邮箱。"""
    username = str((request.data or {}).get("username") or "").strip()
    if not username:
        return HertzResponse.validation_error(message="请先输入登录账号")

    user = _get_active_user_by_username(username)
    if not user:
        return HertzResponse.not_found("账号不存在或已被禁用")
    if not user.email:
        return HertzResponse.validation_error(message="该账号未绑定邮箱，无法通过邮箱重置密码")

    return HertzResponse.success(
        data={"username": user.username, "email_masked": _mask_email(user.email)},
        message="已获取绑定邮箱",
    )


@api_view(["POST"])
def send_reset_password_code(request):
    """将重置密码验证码发送到账号绑定邮箱，不接受前端传入任意邮箱。"""
    username = str((request.data or {}).get("username") or "").strip()
    if not username:
        return HertzResponse.validation_error(message="请先输入登录账号")

    user = _get_active_user_by_username(username)
    if not user:
        return HertzResponse.not_found("账号不存在或已被禁用")
    if not user.email:
        return HertzResponse.validation_error(message="该账号未绑定邮箱，无法发送验证码")
    if not _smtp_is_configured():
        return HertzResponse.error(
            message="邮件服务未配置，请先在 backend/.env 填写真实发件邮箱和SMTP授权码"
        )

    limit_key = f"email_code_limit_{user.email}"
    if cache.get(limit_key):
        return HertzResponse.error(message="发送过于频繁，请60秒后再试", code=429)

    verification_code = f"{random.randint(0, 999999):06d}"
    code_cache_key = f"email_code_{user.email}_{RESET_CODE_TYPE}"
    cache.set(code_cache_key, verification_code, 300)
    cache.set(limit_key, True, 60)

    email_sent = EmailService.send_verification_code(
        recipient_email=user.email,
        recipient_name=user.username or user.email.split("@")[0],
        verification_code=verification_code,
        code_type=RESET_CODE_TYPE,
    )
    if not email_sent:
        cache.delete(code_cache_key)
        cache.delete(limit_key)
        return HertzResponse.error(message="邮件发送失败，请检查邮箱服务配置后重试")

    return HertzResponse.success(
        data={
            "username": user.username,
            "email_masked": _mask_email(user.email),
            "expires_in": 300,
        },
        message="验证码已发送至绑定邮箱",
    )


@api_view(["POST"])
def reset_password(request):
    """本项目覆盖官方 reset 接口，修复官方 serializer 漏接 email_code 导致的 500。"""
    data = request.data or {}
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip()
    email_code = str(data.get("email_code") or "").strip()
    new_password = str(data.get("new_password") or "")
    confirm_password = str(data.get("confirm_password") or "")

    user = None
    if username:
        user = _get_active_user_by_username(username)
        if not user:
            return HertzResponse.not_found("账号不存在或已被禁用")
        email = user.email or ""

    if not email:
        return HertzResponse.validation_error(message="账号未绑定邮箱，无法重置密码")
    if not email_code:
        return HertzResponse.validation_error(message="邮箱验证码不能为空")
    if new_password != confirm_password:
        return HertzResponse.validation_error(message="两次输入的新密码不一致")

    ok, error = _password_is_valid(new_password)
    if not ok:
        return HertzResponse.validation_error(message=error)

    cached_code = cache.get(f"email_code_{email}_reset_password")
    if not cached_code or str(cached_code) != email_code:
        return HertzResponse.error(message="邮箱验证码错误或已过期")

    if user is None:
        user = HertzUser.objects.filter(email=email, status=1).first()
    if not user:
        return HertzResponse.not_found("邮箱未注册或用户已被禁用")

    user.set_password(new_password)
    user.save(update_fields=["password"])
    cache.delete(f"email_code_{email}_reset_password")
    return HertzResponse.success(message="密码重置成功")
