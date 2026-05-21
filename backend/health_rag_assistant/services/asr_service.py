"""
语音识别服务（ASR）
- 对接火山引擎 WebSocket 二进制协议
- 自定义协议编解码：消息头（4字节）+ 分片 payload + gzip 压缩
- 支持流式语音识别（bigmodel 模型）
"""
import asyncio
import gzip
import json
import struct
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
from django.conf import settings

PROTOCOL_VERSION = 0x1
HEADER_SIZE_UNITS = 0x1

MESSAGE_TYPE_FULL_CLIENT_REQUEST = 0x1
MESSAGE_TYPE_AUDIO_ONLY_REQUEST = 0x2
MESSAGE_TYPE_FULL_SERVER_RESPONSE = 0x9
MESSAGE_TYPE_ERROR_RESPONSE = 0xF

MESSAGE_FLAG_NONE = 0x0
MESSAGE_FLAG_WITH_SEQUENCE = 0x1
MESSAGE_FLAG_LAST_PACKAGE = 0x2
MESSAGE_FLAG_LAST_PACKAGE_WITH_SEQUENCE = 0x3

SERIALIZATION_NONE = 0x0
SERIALIZATION_JSON = 0x1

COMPRESSION_NONE = 0x0
COMPRESSION_GZIP = 0x1

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_BITS = 16
DEFAULT_CHANNELS = 1
DEFAULT_CHUNK_MS = 160


class ASRServiceError(Exception):
    pass


def _build_header(
    *,
    message_type: int,
    message_flags: int,
    serialization: int,
    compression: int,
) -> bytes:
    return bytes(
        [
            ((PROTOCOL_VERSION & 0x0F) << 4) | (HEADER_SIZE_UNITS & 0x0F),
            ((message_type & 0x0F) << 4) | (message_flags & 0x0F),
            ((serialization & 0x0F) << 4) | (compression & 0x0F),
            0x00,
        ]
    )


def _compress_payload(raw_payload: bytes, compression: int) -> bytes:
    if compression == COMPRESSION_GZIP:
        return gzip.compress(raw_payload)
    return raw_payload


def _decode_payload(payload: bytes, *, compression: int, serialization: int) -> Any:
    raw = payload
    if compression == COMPRESSION_GZIP and payload:
        raw = gzip.decompress(payload)

    if serialization == SERIALIZATION_JSON:
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))
    return raw


def _build_full_client_request(payload: Dict[str, Any]) -> bytes:
    raw_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    compressed_payload = _compress_payload(raw_payload, COMPRESSION_GZIP)
    header = _build_header(
        message_type=MESSAGE_TYPE_FULL_CLIENT_REQUEST,
        message_flags=MESSAGE_FLAG_NONE,
        serialization=SERIALIZATION_JSON,
        compression=COMPRESSION_GZIP,
    )
    return header + struct.pack(">I", len(compressed_payload)) + compressed_payload


def _build_audio_request(audio_chunk: bytes, *, is_last: bool) -> bytes:
    compressed_payload = _compress_payload(audio_chunk, COMPRESSION_GZIP)
    header = _build_header(
        message_type=MESSAGE_TYPE_AUDIO_ONLY_REQUEST,
        message_flags=MESSAGE_FLAG_LAST_PACKAGE if is_last else MESSAGE_FLAG_NONE,
        serialization=SERIALIZATION_NONE,
        compression=COMPRESSION_GZIP,
    )
    return header + struct.pack(">I", len(compressed_payload)) + compressed_payload


def _parse_binary_response(raw_message: bytes) -> Dict[str, Any]:
    if len(raw_message) < 8:
        raise ASRServiceError("ASR 响应数据长度不合法")

    version = (raw_message[0] >> 4) & 0x0F
    header_units = raw_message[0] & 0x0F
    header_size = header_units * 4
    if version != PROTOCOL_VERSION:
        raise ASRServiceError(f"不支持的 ASR 协议版本: {version}")
    if len(raw_message) < header_size + 4:
        raise ASRServiceError("ASR 响应头长度不合法")

    message_type = (raw_message[1] >> 4) & 0x0F
    message_flags = raw_message[1] & 0x0F
    serialization = (raw_message[2] >> 4) & 0x0F
    compression = raw_message[2] & 0x0F

    offset = header_size
    sequence: Optional[int] = None

    if message_type == MESSAGE_TYPE_FULL_SERVER_RESPONSE:
        if message_flags in {
            MESSAGE_FLAG_WITH_SEQUENCE,
            MESSAGE_FLAG_LAST_PACKAGE_WITH_SEQUENCE,
        }:
            if len(raw_message) < offset + 4:
                raise ASRServiceError("ASR 响应 sequence 缺失")
            sequence = struct.unpack(">i", raw_message[offset : offset + 4])[0]
            offset += 4

        payload_size = struct.unpack(">I", raw_message[offset : offset + 4])[0]
        offset += 4
        payload = raw_message[offset : offset + payload_size]
        return {
            "message_type": message_type,
            "message_flags": message_flags,
            "sequence": sequence,
            "payload": _decode_payload(
                payload,
                compression=compression,
                serialization=serialization,
            ),
        }

    if message_type == MESSAGE_TYPE_ERROR_RESPONSE:
        error_code = struct.unpack(">I", raw_message[offset : offset + 4])[0]
        offset += 4
        payload_size = struct.unpack(">I", raw_message[offset : offset + 4])[0]
        offset += 4
        payload = raw_message[offset : offset + payload_size]
        detail = _decode_payload(
            payload,
            compression=compression,
            serialization=serialization,
        )
        raise ASRServiceError(f"ASR 服务返回错误 code={error_code}, detail={detail}")

    raise ASRServiceError(f"暂不支持的 ASR 响应类型: {message_type}")


def _build_request_payload(
    *,
    user_id: Optional[int],
    audio_format: str,
    sample_rate: int,
    bits: int,
    channels: int,
    language: str,
) -> Dict[str, Any]:
    return {
        "user": {
            "uid": str(user_id or uuid.uuid4()),
        },
        "audio": {
            "format": audio_format,
            "rate": sample_rate,
            "bits": bits,
            "channel": channels,
            "language": language,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_ddc": True,
            "enable_punc": True,
        },
    }


def _merge_transcribe_result(
    merged: Dict[str, Any],
    response_payload: Dict[str, Any],
) -> None:
    if not isinstance(response_payload, dict):
        return

    merged.setdefault("raw_response", []).append(response_payload)

    audio_info = response_payload.get("audio_info") or {}
    if audio_info.get("duration") is not None:
        try:
            merged["duration_ms"] = int(audio_info.get("duration") or 0)
        except Exception:
            merged["duration_ms"] = 0

    result = response_payload.get("result") or {}
    text = str(result.get("text") or "").strip()
    if text:
        merged["text"] = text

    utterances = result.get("utterances")
    if isinstance(utterances, list) and utterances:
        merged["utterances"] = utterances


async def _receive_ws_response(
    ws: aiohttp.ClientWebSocketResponse,
    *,
    timeout: int,
) -> Dict[str, Any]:
    message = await ws.receive(timeout=timeout)
    if message.type == aiohttp.WSMsgType.BINARY:
        return _parse_binary_response(message.data)
    if message.type == aiohttp.WSMsgType.TEXT:
        try:
            return {"payload": json.loads(message.data)}
        except Exception as exc:
            raise ASRServiceError(
                f"ASR 返回了无法解析的文本消息: {message.data}"
            ) from exc
    if message.type in {
        aiohttp.WSMsgType.CLOSE,
        aiohttp.WSMsgType.CLOSED,
        aiohttp.WSMsgType.CLOSING,
    }:
        raise ASRServiceError("ASR WebSocket 已关闭")
    if message.type == aiohttp.WSMsgType.ERROR:
        raise ASRServiceError(f"ASR WebSocket 连接异常: {ws.exception()}")
    raise ASRServiceError(f"收到未知的 ASR WebSocket 消息类型: {message.type}")


async def _transcribe_file_async(
    *,
    audio_bytes: bytes,
    user_id: Optional[int],
    audio_format: str,
    sample_rate: int,
    bits: int,
    channels: int,
    language: str,
) -> Dict[str, Any]:
    ws_url = getattr(
        settings,
        "HEALTH_RAG_ASR_WS_URL",
        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
    )
    app_key = getattr(settings, "HEALTH_RAG_ASR_APP_KEY", "")
    access_key = getattr(settings, "HEALTH_RAG_ASR_ACCESS_KEY", "")
    resource_id = getattr(settings, "HEALTH_RAG_ASR_RESOURCE_ID", "")
    timeout = int(getattr(settings, "HEALTH_RAG_ASR_TIMEOUT", 30))

    if not app_key or not access_key or not resource_id:
        raise ASRServiceError(
            "ASR 配置不完整，请检查 HEALTH_RAG_ASR_APP_KEY / ACCESS_KEY / RESOURCE_ID"
        )

    byte_rate = max(1, int(sample_rate * channels * (bits / 8)))
    chunk_size = max(1024, int(byte_rate * (DEFAULT_CHUNK_MS / 1000)))

    headers = {
        "X-Api-App-Key": str(app_key).strip(),
        "X-Api-Access-Key": str(access_key).strip(),
        "X-Api-Resource-Id": str(resource_id).strip(),
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }
    request_payload = _build_request_payload(
        user_id=user_id,
        audio_format=audio_format,
        sample_rate=sample_rate,
        bits=bits,
        channels=channels,
        language=language,
    )
    merged_result: Dict[str, Any] = {
        "text": "",
        "duration_ms": 0,
        "utterances": [],
        "raw_response": [],
    }

    client_timeout = aiohttp.ClientTimeout(
        total=None, sock_connect=timeout, sock_read=timeout
    )
    async with aiohttp.ClientSession(timeout=client_timeout) as session:
        try:
            async with session.ws_connect(
                ws_url, headers=headers, heartbeat=max(timeout, 15)
            ) as ws:
                await ws.send_bytes(_build_full_client_request(request_payload))
                init_response = await _receive_ws_response(ws, timeout=timeout)
                _merge_transcribe_result(
                    merged_result, init_response.get("payload") or {}
                )

                for offset in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[offset : offset + chunk_size]
                    is_last = offset + chunk_size >= len(audio_bytes)
                    await ws.send_bytes(_build_audio_request(chunk, is_last=is_last))
                    audio_response = await _receive_ws_response(ws, timeout=timeout)
                    _merge_transcribe_result(
                        merged_result, audio_response.get("payload") or {}
                    )
                    if not is_last:
                        await asyncio.sleep(DEFAULT_CHUNK_MS / 1000)
        except aiohttp.WSServerHandshakeError as exc:
            logid = (
                exc.headers.get("X-Tt-Logid") or exc.headers.get("x-tt-logid") or ""
            ).strip()
            api_message = (
                exc.headers.get("X-Api-Message")
                or exc.headers.get("x-api-message")
                or ""
            ).strip()
            api_status_code = (
                exc.headers.get("X-Api-Status-Code")
                or exc.headers.get("x-api-status-code")
                or ""
            ).strip()
            extra_parts = []
            if api_status_code:
                extra_parts.append(f"api_status={api_status_code}")
            if api_message:
                extra_parts.append(f"api_message={api_message}")
            if logid:
                extra_parts.append(f"logid={logid}")
            extra_text = f"（{'，'.join(extra_parts)}）" if extra_parts else ""
            raise ASRServiceError(
                f"ASR 握手失败 HTTP {exc.status}{extra_text}"
            ) from exc

    transcript = str(merged_result.get("text") or "").strip()
    if not transcript:
        utterance_texts = [
            str(item.get("text") or "").strip()
            for item in (merged_result.get("utterances") or [])
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
        transcript = "".join(utterance_texts).strip()
        merged_result["text"] = transcript

    if not transcript:
        raise ASRServiceError("ASR 未返回可用的识别文本")

    return merged_result


def transcribe_file(
    uploaded_file,
    *,
    language: Optional[str] = None,
    audio_meta: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    if uploaded_file is None:
        raise ASRServiceError("未接收到音频文件")

    file_name = str(getattr(uploaded_file, "name", "") or "")
    suffix = Path(file_name).suffix.lower().lstrip(".")
    audio_meta = audio_meta or {}

    audio_format = str(audio_meta.get("format") or suffix or "wav").strip().lower()
    sample_rate = int(audio_meta.get("rate") or DEFAULT_SAMPLE_RATE)
    bits = int(audio_meta.get("bits") or DEFAULT_BITS)
    channels = int(audio_meta.get("channel") or DEFAULT_CHANNELS)
    language = (
        str(
            language or getattr(settings, "HEALTH_RAG_ASR_DEFAULT_LANGUAGE", "zh-CN")
        ).strip()
        or "zh-CN"
    )

    try:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
    except Exception:
        pass

    audio_bytes = uploaded_file.read()
    if not audio_bytes:
        raise ASRServiceError("音频文件为空")

    return asyncio.run(
        _transcribe_file_async(
            audio_bytes=audio_bytes,
            user_id=user_id,
            audio_format=audio_format,
            sample_rate=sample_rate,
            bits=bits,
            channels=channels,
            language=language,
        )
    )
