"""
LLM 服务层
- 双模式自动切换：Ollama（本地） + OpenAI 兼容（远程 API）
- 运行时可切换模型（base_url / api_key / model_name）
- 模型状态检查、重启（卸载+预热）、切换
"""
from datetime import datetime
from threading import RLock
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests
from django.conf import settings

from hertz_studio_django_utils.ollama.ollama_client import OllamaClient

from ..utils.prompt_builder import build_messages

OLLAMA_MODEL_PREFERENCES = (
    "qwen",
    "deepseek",
    "gemma",
    "llama",
    "mistral",
)

_RUNTIME_CONFIG_LOCK = RLock()
_RUNTIME_LLM_CONFIG: Dict[str, str] = {
    "base_url": "",
    "api_key": "",
    "model_name": "",
    "updated_at": "",
}


class HealthLLMService:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        runtime_config = self.get_runtime_config()
        self.default_model_name = getattr(
            settings,
            "HEALTH_RAG_MODEL_NAME",
            getattr(settings, "AI_MODEL_NAME", "deepseek-r1:1.5b"),
        )
        default_base_url = getattr(
            settings, "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        runtime_base_url = self._normalize_base_url(runtime_config.get("base_url"))
        runtime_api_key = (runtime_config.get("api_key") or "").strip()
        runtime_model_name = (runtime_config.get("model_name") or "").strip()

        self.base_url = (
            self._normalize_base_url(base_url)
            or runtime_base_url
            or self._normalize_base_url(default_base_url)
        )
        self.api_key = (
            api_key
            or runtime_api_key
            or getattr(settings, "HEALTH_RAG_API_KEY", "")
            or ""
        ).strip()
        self.model_name = (
            model_name or runtime_model_name or self.default_model_name or ""
        ).strip()
        self.timeout = int(getattr(settings, "HEALTH_RAG_LLM_TIMEOUT", 60))
        self.client = OllamaClient(base_url=self.base_url)

    @classmethod
    def get_runtime_config(cls) -> Dict[str, str]:
        with _RUNTIME_CONFIG_LOCK:
            return dict(_RUNTIME_LLM_CONFIG)

    @classmethod
    def set_runtime_config(
        cls,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        clear_api_key: bool = False,
    ) -> Dict[str, str]:
        with _RUNTIME_CONFIG_LOCK:
            if base_url is not None:
                _RUNTIME_LLM_CONFIG["base_url"] = cls._normalize_base_url(base_url)
            if model_name is not None:
                _RUNTIME_LLM_CONFIG["model_name"] = str(model_name).strip()
            if clear_api_key:
                _RUNTIME_LLM_CONFIG["api_key"] = ""
            elif api_key is not None:
                _RUNTIME_LLM_CONFIG["api_key"] = str(api_key).strip()
            _RUNTIME_LLM_CONFIG["updated_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            return dict(_RUNTIME_LLM_CONFIG)

    def generate_answer(
        self,
        question: str,
        contexts: Iterable[dict],
        conversation_history: Optional[Iterable[dict]] = None,
    ) -> str:
        messages = build_messages(
            question=question,
            contexts=contexts,
            conversation_history=conversation_history,
        )
        prefer_openai = self._prefer_openai()
        ollama_error = None
        openai_error = None

        if prefer_openai:
            try:
                return self._generate_by_openai_compatible(messages)
            except Exception as exc:
                openai_error = str(exc)
            try:
                return self._generate_by_ollama(messages)
            except Exception as exc:
                ollama_error = str(exc)
        else:
            try:
                return self._generate_by_ollama(messages)
            except Exception as exc:
                ollama_error = str(exc)
            try:
                return self._generate_by_openai_compatible(messages)
            except Exception as exc:
                openai_error = str(exc)

        raise ValueError(
            "LLM调用失败，"
            f"Ollama: {ollama_error or '-'}，"
            f"OpenAI兼容: {openai_error or '-'}。"
            "请确认 BASE_URL/API_KEY/MODEL。"
        )

    def generate_by_messages(
        self, messages: Iterable[dict], *, force_json: bool = False
    ) -> str:
        """
        使用调用方自定义 messages 直接生成内容。
        - force_json=True 时：若走 OpenAI 兼容接口，将追加 response_format=json_object，以提高结构化输出稳定性。
        """
        prefer_openai = self._prefer_openai()
        ollama_error = None
        openai_error = None

        if prefer_openai:
            try:
                return self._generate_by_openai_compatible(
                    messages, force_json=force_json
                )
            except Exception as exc:
                openai_error = str(exc)
            try:
                return self._generate_by_ollama(messages)
            except Exception as exc:
                ollama_error = str(exc)
        else:
            try:
                return self._generate_by_ollama(messages)
            except Exception as exc:
                ollama_error = str(exc)
            try:
                return self._generate_by_openai_compatible(
                    messages, force_json=force_json
                )
            except Exception as exc:
                openai_error = str(exc)

        raise ValueError(
            "LLM调用失败，"
            f"Ollama: {ollama_error or '-'}，"
            f"OpenAI兼容: {openai_error or '-'}。"
            "请确认 BASE_URL/API_KEY/MODEL。"
        )

    @staticmethod
    def _normalize_base_url(base_url: Optional[str]) -> str:
        if not base_url:
            return ""
        return str(base_url).strip().rstrip("/")

    @staticmethod
    def _openai_chat_endpoint(base_url: str) -> str:
        normalized = HealthLLMService._normalize_base_url(base_url)
        if normalized.endswith("/v1"):
            return f"{normalized}/chat/completions"
        return f"{normalized}/v1/chat/completions"

    @staticmethod
    def _openai_models_endpoint(base_url: str) -> str:
        normalized = HealthLLMService._normalize_base_url(base_url)
        if normalized.endswith("/v1"):
            return f"{normalized}/models"
        return f"{normalized}/v1/models"

    def _prefer_openai(self) -> bool:
        path = (urlparse(self.base_url).path or "").lower()
        return "/v1" in path or bool(self.api_key)

    def _generate_by_ollama(self, messages: Iterable[dict]) -> str:
        self.model_name = self._resolve_ollama_model_name(
            base_url=self.base_url,
            model_name=self.model_name,
            api_key=self.api_key,
        )
        return self.client.chat_completion(
            model=self.model_name,
            messages=list(messages),
        )

    def _generate_by_openai_compatible(
        self,
        messages: Iterable[dict],
        *,
        temperature: float = 0.4,
        force_json: bool = False,
    ) -> str:
        endpoint = self._openai_chat_endpoint(self.base_url)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "messages": list(messages),
            "temperature": temperature,
            "stream": False,
        }
        if force_json:
            payload["response_format"] = {"type": "json_object"}
        resp = requests.post(
            endpoint, json=payload, headers=headers, timeout=self.timeout
        )
        if resp.status_code >= 400:
            raise ValueError(
                f"OpenAI兼容调用失败 {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        choices = data.get("choices", []) or []
        if not choices:
            raise ValueError("OpenAI兼容响应缺少 choices")
        message = choices[0].get("message", {}) or {}
        content = message.get("content")
        if not content:
            raise ValueError("OpenAI兼容响应缺少 message.content")
        return str(content)

    def _check_ollama_status(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str = "",
        timeout: int = 10,
    ) -> dict:
        tags_url = f"{base_url}/api/tags"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.get(tags_url, timeout=timeout, headers=headers)
        if resp.status_code != 200:
            raise ValueError(f"Ollama 服务异常: {resp.status_code}")
        data = resp.json()
        models = data.get("models", []) or []
        names: List[str] = [m.get("name", "") for m in models if m.get("name")]
        selected_model = self._select_ollama_model(names, preferred=model_name)
        if model_name:
            available = bool(selected_model)
            if model_name in names:
                message = "模型可用"
            elif selected_model:
                message = f"配置模型未安装，已自动使用本机模型：{selected_model}"
            else:
                message = "模型未安装"
        else:
            available = bool(selected_model)
            message = (
                f"服务可用，已自动使用本机模型：{selected_model}"
                if selected_model
                else "服务可用（暂无模型）"
            )
        return {
            "provider": "ollama",
            "available": available,
            "installed_models": names,
            "selected_model": selected_model,
            "auto_selected": bool(selected_model and selected_model != model_name),
            "message": message,
        }

    @classmethod
    def _select_ollama_model(
        cls,
        installed_models: Iterable[str],
        *,
        preferred: str = "",
    ) -> str:
        names = [str(name or "").strip() for name in installed_models if str(name or "").strip()]
        if not names:
            return ""
        preferred = str(preferred or "").strip()
        if preferred in names:
            return preferred

        lowered = {name.lower(): name for name in names}
        for keyword in OLLAMA_MODEL_PREFERENCES:
            for lowered_name, original_name in lowered.items():
                if keyword in lowered_name:
                    return original_name
        return names[0]

    def _resolve_ollama_model_name(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str = "",
    ) -> str:
        status = self._check_ollama_status(
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            timeout=5,
        )
        selected_model = (status.get("selected_model") or model_name or "").strip()
        if not selected_model:
            raise ValueError("Ollama 服务可访问，但没有安装可用模型")
        if selected_model != model_name:
            self.set_runtime_config(
                base_url=base_url,
                api_key=api_key,
                model_name=selected_model,
            )
        return selected_model

    def _check_openai_compatible_status(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str = "",
        timeout: int = 10,
    ) -> dict:
        endpoint = self._openai_models_endpoint(base_url)
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.get(endpoint, timeout=timeout, headers=headers)
        if resp.status_code != 200:
            raise ValueError(f"OpenAI兼容服务异常: {resp.status_code}")
        data = resp.json()
        model_data = data.get("data", []) or []
        names: List[str] = [m.get("id", "") for m in model_data if m.get("id")]
        if model_name:
            available = model_name in names
            message = "模型可用" if available else "模型不存在或无权限访问"
        else:
            available = bool(names)
            message = (
                "服务可用（未指定模型）" if available else "服务可用（未返回模型列表）"
            )
        return {
            "provider": "openai-compatible",
            "available": available,
            "installed_models": names,
            "message": message,
        }

    @staticmethod
    def _post_json(
        url: str,
        *,
        payload: dict,
        api_key: str = "",
        timeout: int = 30,
    ) -> dict:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            raise ValueError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except Exception:
            return {"raw_text": resp.text}

    def restart_model(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        warmup: bool = True,
    ) -> dict:
        resolved_base_url = self._normalize_base_url(base_url) or self.base_url
        resolved_model_name = (
            model_name or self.model_name or self.default_model_name or ""
        ).strip()
        resolved_api_key = (api_key or self.api_key or "").strip()

        if not resolved_model_name:
            raise ValueError("未指定模型名称，无法重启")

        is_openai_compatible = self._prefer_openai()
        if base_url is not None or api_key is not None:
            path = (urlparse(resolved_base_url).path or "").lower()
            is_openai_compatible = "/v1" in path or bool(resolved_api_key)

        if is_openai_compatible:
            raise ValueError(
                "当前为 OpenAI 兼容模式，无法远程重启服务。请在模型部署机器上手动重启。"
            )

        unload_url = f"{resolved_base_url}/api/generate"
        self._post_json(
            unload_url,
            payload={
                "model": resolved_model_name,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            },
            api_key=resolved_api_key,
            timeout=30,
        )

        warmup_result = None
        if warmup:
            warmup_result = self._post_json(
                unload_url,
                payload={
                    "model": resolved_model_name,
                    "prompt": "你好",
                    "stream": False,
                    "options": {"num_predict": 1},
                },
                api_key=resolved_api_key,
                timeout=max(self.timeout, 30),
            )

        status = self.get_model_status(
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            model_name=resolved_model_name,
        )
        return {
            "restarted": True,
            "message": "模型已重启（卸载并预热完成）",
            "status": status,
            "warmup": warmup_result,
        }

    def switch_model(
        self,
        *,
        model_name: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> dict:
        target_model_name = (model_name or "").strip()
        if not target_model_name:
            raise ValueError("MODEL 不能为空")

        resolved_base_url = self._normalize_base_url(base_url) or self.base_url
        resolved_api_key = (api_key or self.api_key or "").strip()

        check_status = self.get_model_status(
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            model_name=target_model_name,
        )
        if not check_status.get("available"):
            raise ValueError(
                f"目标模型不可用: {check_status.get('message') or 'unknown'}"
            )

        runtime_config = self.set_runtime_config(
            base_url=resolved_base_url,
            api_key=resolved_api_key,
            model_name=target_model_name,
        )

        effective_status = HealthLLMService().get_model_status()
        return {
            "switched": True,
            "active_model_name": runtime_config.get("model_name") or target_model_name,
            "runtime_config": {
                "base_url": runtime_config.get("base_url", ""),
                "model_name": runtime_config.get("model_name", ""),
                "api_key_configured": bool(runtime_config.get("api_key", "")),
                "updated_at": runtime_config.get("updated_at", ""),
            },
            "status": effective_status,
            "message": "模型切换成功",
        }

    def get_model_status(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> dict:
        resolved_base_url = self._normalize_base_url(base_url) or self.base_url
        resolved_model_name = (
            model_name or self.model_name or self.default_model_name or ""
        ).strip()
        resolved_api_key = (api_key or self.api_key or "").strip()
        runtime_config = self.get_runtime_config()
        path = (urlparse(resolved_base_url).path or "").lower()

        status = {
            "model_name": resolved_model_name,
            "base_url": resolved_base_url,
            "api_key_configured": bool(resolved_api_key),
            "provider": "",
            "available": False,
            "installed_models": [],
            "message": "",
            "runtime_config": {
                "base_url": runtime_config.get("base_url", ""),
                "model_name": runtime_config.get("model_name", ""),
                "api_key_configured": bool(runtime_config.get("api_key", "")),
                "updated_at": runtime_config.get("updated_at", ""),
            },
        }

        ollama_error = None
        openai_error = None

        # 优先策略：
        # 1) BASE_URL 包含 /v1 或显式传了 API_KEY，优先按 OpenAI 兼容协议检测
        # 2) 其他情况先按 Ollama 检测，再回退 OpenAI 兼容
        prefer_openai = "/v1" in path or bool(resolved_api_key)

        if prefer_openai:
            try:
                result = self._check_openai_compatible_status(
                    base_url=resolved_base_url,
                    model_name=resolved_model_name,
                    api_key=resolved_api_key,
                )
                status.update(result)
                return status
            except Exception as exc:
                openai_error = str(exc)

            try:
                result = self._check_ollama_status(
                    base_url=resolved_base_url,
                    model_name=resolved_model_name,
                    api_key=resolved_api_key,
                )
                status.update(result)
                if result.get("selected_model"):
                    status["model_name"] = result["selected_model"]
                    status["configured_model_name"] = resolved_model_name
                return status
            except Exception as exc:
                ollama_error = str(exc)
        else:
            try:
                result = self._check_ollama_status(
                    base_url=resolved_base_url,
                    model_name=resolved_model_name,
                    api_key=resolved_api_key,
                )
                status.update(result)
                if result.get("selected_model"):
                    status["model_name"] = result["selected_model"]
                    status["configured_model_name"] = resolved_model_name
                return status
            except Exception as exc:
                ollama_error = str(exc)

            try:
                result = self._check_openai_compatible_status(
                    base_url=resolved_base_url,
                    model_name=resolved_model_name,
                    api_key=resolved_api_key,
                )
                status.update(result)
                return status
            except Exception as exc:
                openai_error = str(exc)

        try:
            status["message"] = (
                "模型状态检查失败，"
                f"Ollama: {ollama_error or '-'}，"
                f"OpenAI兼容: {openai_error or '-'}。"
                "请确认 BASE_URL/API_KEY/MODEL。"
            )
            return status
        except Exception as exc:
            status["message"] = f"模型状态检查失败: {exc}"
            return status
