# 本地验证码视图
import base64
import json
import random
import string
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from PIL import Image, ImageDraw, ImageFont
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from hertz_studio_django_utils.responses.HertzResponse import HertzResponse


FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Avenir.ttc",
    "/Library/Fonts/Arial.ttf",
]


def _load_font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _generate_code(length: int) -> str:
    characters = string.ascii_uppercase + string.digits
    characters = characters.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    return "".join(random.choice(characters) for _ in range(length))


def _image_to_base64(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _draw_readable_captcha(code: str) -> Image.Image:
    width = getattr(settings, "HERTZ_CAPTCHA_WIDTH", 172)
    height = getattr(settings, "HERTZ_CAPTCHA_HEIGHT", 54)
    font_size = getattr(settings, "HERTZ_CAPTCHA_FONT_SIZE", 36)
    noise_level = getattr(settings, "HERTZ_CAPTCHA_NOISE_LEVEL", 0.003)

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    font = _load_font(font_size)

    gap = 9
    boxes = [draw.textbbox((0, 0), char, font=font) for char in code]
    char_widths = [box[2] - box[0] for box in boxes]
    char_heights = [box[3] - box[1] for box in boxes]
    total_width = sum(char_widths) + gap * (len(code) - 1)
    x = max(10, (width - total_width) // 2)
    baseline_y = max(5, (height - max(char_heights)) // 2 - 3)

    palette = [(22, 78, 133), (28, 94, 118), (38, 82, 122), (55, 83, 138)]
    for index, char in enumerate(code):
        y = baseline_y + random.randint(-2, 2)
        draw.text((x, y), char, font=font, fill=palette[index % len(palette)])
        x += char_widths[index] + gap

    for _ in range(int(width * height * noise_level)):
        draw.point(
            (random.randint(0, width - 1), random.randint(0, height - 1)),
            fill=random.choice([(126, 164, 200), (148, 185, 170), (185, 160, 195)]),
        )

    if width >= 150:
        y = random.randint(height // 2 - 4, height // 2 + 4)
        draw.line([(10, y), (width - 10, y + random.randint(-4, 4))], fill=(176, 196, 216), width=1)

    return image


def _store_captcha(captcha_id: str, code: str) -> None:
    timeout = getattr(settings, "HERTZ_CAPTCHA_TIMEOUT", 300)
    redis_prefix = getattr(settings, "HERTZ_CAPTCHA_REDIS_KEY_PREFIX", "hertz_captcha:")
    captcha_data = {
        "code": code,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(seconds=timeout)).isoformat(),
    }
    cache.set(f"{redis_prefix}{captcha_id}", captcha_data, timeout)

    try:
        from hertz_studio_django_captcha.captcha_generator import HertzCaptchaGenerator

        generator = HertzCaptchaGenerator()
        if generator.redis_client:
            generator.redis_client.setex(
                f"{redis_prefix}{captcha_id}",
                timeout,
                json.dumps(captcha_data),
            )
    except Exception:
        pass


def _delete_captcha(captcha_id: str) -> None:
    if not captcha_id:
        return
    redis_prefix = getattr(settings, "HERTZ_CAPTCHA_REDIS_KEY_PREFIX", "hertz_captcha:")
    cache.delete(f"{redis_prefix}{captcha_id}")
    try:
        from hertz_studio_django_captcha.captcha_generator import HertzCaptchaGenerator

        generator = HertzCaptchaGenerator()
        if generator.redis_client:
            generator.redis_client.delete(f"{redis_prefix}{captcha_id}")
    except Exception:
        pass


def _generate_payload():
    length = getattr(settings, "HERTZ_CAPTCHA_LENGTH", 4)
    timeout = getattr(settings, "HERTZ_CAPTCHA_TIMEOUT", 300)
    code = _generate_code(length)
    captcha_id = str(uuid.uuid4())
    image = _draw_readable_captcha(code)
    _store_captcha(captcha_id, code)
    return {
        "captcha_id": captcha_id,
        "image_data": _image_to_base64(image),
        "expires_in": timeout,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def generate_captcha(request):
    return HertzResponse.success(data=_generate_payload(), message="验证码生成成功")


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_captcha(request):
    _delete_captcha(request.data.get("captcha_id", ""))
    return HertzResponse.success(data=_generate_payload(), message="验证码刷新成功")
