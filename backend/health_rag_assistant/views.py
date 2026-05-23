"""
API 视图层
- 知识文档 CRUD + 索引重建（管理员）
- 问答聊天（文字/语音）+ 会话管理
- 历史查询 + PDF 导出
- 模型状态/切换/重启
- 个性化推荐
"""
import json
import time
from io import StringIO
from pathlib import Path
import re

from django.conf import settings
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from hertz_studio_django_auth.utils.decorators import login_required
from rest_framework.decorators import api_view

from hertz_studio_django_utils.responses.HertzResponse import HertzResponse

from .models import (
    HealthKnowledgeDocument,
    HealthQARecord,
    HealthQASession,
)
from .serializers import (
    HealthChatAskSerializer,
    HealthChatTranscribeSerializer,
    HealthHistoryExportPdfSerializer,
    HealthKnowledgeDocumentCreateSerializer,
    HealthKnowledgeDocumentDeleteSerializer,
    HealthKnowledgeDocumentSerializer,
    HealthKnowledgeDocumentUpdateSerializer,
    HealthKnowledgeReindexSerializer,
    HealthModelControlSerializer,
    HealthModelSwitchSerializer,
    HealthRetrievalDebugSerializer,
    HealthRagasEvalRunSerializer,
    HealthRetrievalEvalRunSerializer,
    HealthQASessionCreateSerializer,
    HealthQASessionDeleteSerializer,
    HealthRecommendSerializer,
)
from .services.embedding_service import EmbeddingService
from .services.asr_service import ASRServiceError, transcribe_file
from .services.kb_service import (
    create_document_and_index,
    create_structured_markdown_documents_and_index,
    rebuild_index_for_documents,
    sync_vector_index,
    update_document_and_index,
)
from .services.knowledge_card_service import build_knowledge_card
from .services.llm_service import HealthLLMService
from .services.pdf_export_service import build_qa_records_pdf
from .services.rag_service import ask_with_rag, retrieve_hybrid
from .services.recommend_service import build_personal_recommendations
from .services.vector_store import QdrantVectorStore

ADMIN_ROLE_CODES = {"admin", "system_admin", "super_admin"}
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _get_request_data(request):
    content_type = request.META.get("CONTENT_TYPE", "")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if "application/json" in content_type:
            try:
                return json.loads(request.body)
            except Exception:
                return {}
        data = request.POST.dict()
        if not data:
            data = request.GET.dict()
        return data
    return request.GET.dict()


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", str(text or ""))


def _format_asr_error(exc):
    message = str(exc or "").strip()
    if "未返回可用的识别文本" in message:
        return "未识别到有效语音内容，请靠近麦克风重新录音，或直接输入文字问题"
    if "配置不完整" in message:
        return "语音转写服务未配置完整，请检查 ASR 应用密钥配置"
    if "握手失败" in message or "WebSocket" in message:
        return f"语音转写服务连接失败：{message}"
    if message:
        return f"语音转写失败：{message}"
    return "语音转写失败，请重新录音后再试"


def _safe_int(raw, default, min_value=None, max_value=None):
    try:
        value = int(raw)
    except Exception:
        return default
    if min_value is not None and value < min_value:
        return default
    if max_value is not None and value > max_value:
        return default
    return value


def _format_dt(value):
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")


def _get_recent_conversation_history(session: HealthQASession, limit: int = 3):
    records = list(
        HealthQARecord.objects.filter(session=session)
        .order_by("-created_at")[: max(int(limit), 0)]
    )
    records.reverse()
    return [
        {
            "question": record.question,
            "answer": record.answer,
            "ask_mode": record.ask_mode,
            "created_at": _format_dt(record.created_at),
        }
        for record in records
    ]


def _extract_role_codes(raw_roles):
    role_codes = []
    if not isinstance(raw_roles, (list, tuple)):
        return role_codes

    for role in raw_roles:
        if isinstance(role, str):
            role_codes.append(role)
            continue
        if isinstance(role, dict):
            code = role.get("role_code") or role.get("code")
            if code:
                role_codes.append(str(code))
    return role_codes


def _is_admin_user(request):
    user = getattr(request, "user", None)
    if user is not None:
        if bool(
            getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)
        ):
            return True
        try:
            role_codes = set(
                user.roles.filter(status=1).values_list("role_code", flat=True)
            )
            if role_codes & ADMIN_ROLE_CODES:
                return True
        except Exception:
            pass

    token_role_codes = set(_extract_role_codes(getattr(request, "user_roles", [])))
    return bool(token_role_codes & ADMIN_ROLE_CODES)


def _require_kb_admin(request):
    if _is_admin_user(request):
        return None
    return HertzResponse.forbidden("仅管理员可管理知识库")


@api_view(["GET"])
def health_check(_request):
    return HertzResponse.success(
        data={"service": "health_rag_assistant", "status": "ok"},
        message="服务可用",
    )


@api_view(["GET"])
@login_required
def kb_document_list(request):
    query = (request.GET.get("query") or "").strip()
    document_id = _safe_int(request.GET.get("document_id"), 0, min_value=0)
    page = _safe_int(request.GET.get("page"), 1, min_value=1)
    page_size = _safe_int(request.GET.get("page_size"), 10, min_value=1, max_value=100)

    q = Q(status="active")
    if document_id:
        q &= Q(id=document_id)
    if query:
        q &= Q(title__icontains=query)

    order_by = "id" if not query and not document_id else "-updated_at"
    documents = (
        HealthKnowledgeDocument.objects.filter(q)
        .annotate(chunk_count_annotated=Count("chunks"))
        .defer("content")
        .order_by(order_by)
    )
    paginator = Paginator(documents, page_size)
    page_obj = paginator.get_page(page)

    return HertzResponse.success(
        data={
            "total": paginator.count,
            "page": page,
            "page_size": page_size,
            "list": HealthKnowledgeDocumentSerializer(page_obj, many=True).data,
        }
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def kb_document_create(request):
    deny_response = _require_kb_admin(request)
    if deny_response:
        return deny_response

    data = _get_request_data(request)
    serializer = HealthKnowledgeDocumentCreateSerializer(data=data)
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    validated = serializer.validated_data
    uploaded_file = request.FILES.get("file")

    source_type = validated.get("source_type", "manual")
    if source_type != "file":
        return HertzResponse.validation_error(
            message="知识库新增只支持上传 txt/md 文件，不支持手动填写路径或正文"
        )
    if (
        source_type == "file"
        and not uploaded_file
        and not (validated.get("content") or "").strip()
    ):
        return HertzResponse.validation_error(
            message="source_type=file 时必须上传文件或提供 content"
        )

    source_path = validated.get("source_path", "")
    if uploaded_file and not source_path:
        source_path = uploaded_file.name

    try:
        split_mode = validated.get("split_mode", "fixed")
        if split_mode == "markdown_entry":
            (
                document,
                created_documents,
                created_chunks,
                skipped_existing,
            ) = create_structured_markdown_documents_and_index(
                user_id=request.user_id,
                title=validated.get("title", ""),
                source_path=source_path,
                content=validated.get("content", ""),
                metadata=validated.get("metadata", {}),
                uploaded_file=uploaded_file,
            )
            payload = HealthKnowledgeDocumentSerializer(document).data
            payload["split_mode"] = split_mode
            payload["created_document_count"] = created_documents
            payload["created_chunk_count"] = created_chunks
            payload["skipped_existing_count"] = skipped_existing
            return HertzResponse.success(
                data=payload,
                message=(
                    f"结构化 Markdown 导入成功：新增 {created_documents} 个条目，"
                    f"{created_chunks} 个切片，跳过重复 {skipped_existing} 个"
                ),
            )
        else:
            document, created_chunks = create_document_and_index(
                user_id=request.user_id,
                title=validated.get("title", ""),
                source_type=source_type,
                source_path=source_path,
                content=validated.get("content", ""),
                metadata=validated.get("metadata", {}),
                uploaded_file=uploaded_file,
                chunk_size=validated.get("chunk_size", 500),
                chunk_overlap=validated.get("chunk_overlap", 80),
            )
            payload = HealthKnowledgeDocumentSerializer(document).data
            payload["split_mode"] = split_mode
            payload["created_document_count"] = 1
            payload["created_chunk_count"] = created_chunks
            return HertzResponse.success(data=payload, message="知识文档创建成功")
    except Exception as exc:
        return HertzResponse.error(message=f"知识文档创建失败: {exc}")


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def kb_document_update(request):
    deny_response = _require_kb_admin(request)
    if deny_response:
        return deny_response

    serializer = HealthKnowledgeDocumentUpdateSerializer(
        data=_get_request_data(request)
    )
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    validated = serializer.validated_data
    document = HealthKnowledgeDocument.objects.filter(
        id=validated["document_id"],
        status="active",
    ).first()
    if not document:
        return HertzResponse.not_found("文档不存在或无权编辑")

    if (
        document.metadata
        and document.metadata.get("seed") == "default_health_rag_kb"
        and "source_path" in validated
        and (validated.get("source_path") or "").strip() != (document.source_path or "")
    ):
        return HertzResponse.validation_error(
            message="系统内置语料的来源路径由程序维护，不允许手动修改"
        )

    try:
        updated_document, updated_chunks = update_document_and_index(
            document=document,
            title=validated.get("title"),
            source_path=validated.get("source_path"),
            content=validated.get("content"),
            metadata=validated.get("metadata"),
            reindex=validated.get("reindex", False),
            chunk_size=validated.get("chunk_size", 500),
            chunk_overlap=validated.get("chunk_overlap", 80),
        )
        payload = HealthKnowledgeDocumentSerializer(updated_document).data
        payload["updated_chunk_count"] = updated_chunks
        return HertzResponse.success(data=payload, message="知识文档更新成功")
    except Exception as exc:
        return HertzResponse.error(message=f"知识文档更新失败: {exc}")


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def kb_document_delete(request):
    deny_response = _require_kb_admin(request)
    if deny_response:
        return deny_response

    serializer = HealthKnowledgeDocumentDeleteSerializer(
        data=_get_request_data(request)
    )
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    doc_ids = serializer.validated_data["document_ids"]
    docs = list(HealthKnowledgeDocument.objects.filter(id__in=doc_ids, status="active"))
    if not docs:
        return HertzResponse.not_found("文档不存在或无权删除")

    # 软删除文档 + 清理索引分块
    document_count = len(docs)
    doc_id_list = [doc.id for doc in docs]
    HealthKnowledgeDocument.objects.filter(id__in=doc_id_list).update(
        status="deleted",
        updated_at=timezone.now(),
    )
    chunk_deleted = 0
    deleted_chunk_ids = []
    for doc in docs:
        deleted_chunk_ids.extend(list(doc.chunks.values_list("id", flat=True)))
        deleted_count, _ = doc.chunks.all().delete()
        chunk_deleted += deleted_count

    # 增量删除 Qdrant 中对应的 points，避免批量删除时重建整库。
    QdrantVectorStore().delete_chunks(deleted_chunk_ids)

    return HertzResponse.success(
        data={"document_count": document_count, "chunk_deleted": chunk_deleted},
        message="文档删除成功",
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def kb_reindex(request):
    deny_response = _require_kb_admin(request)
    if deny_response:
        return deny_response

    serializer = HealthKnowledgeReindexSerializer(data=_get_request_data(request))
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    payload = serializer.validated_data
    doc_ids = payload.get("document_ids") or []
    chunk_size = payload.get("chunk_size", 500)
    chunk_overlap = payload.get("chunk_overlap", 80)

    docs_qs = HealthKnowledgeDocument.objects.filter(
        status="active",
    )
    if doc_ids:
        docs_qs = docs_qs.filter(id__in=doc_ids)

    docs = list(docs_qs)
    if not docs:
        # 没有文档时返回 200，避免前端按 HTTP 错误处理
        vector_ok, vector_message = sync_vector_index(request.user_id)
        return HertzResponse.success(
            data={
                "document_count": 0,
                "chunk_count": 0,
                "vector_synced": vector_ok,
                "vector_message": vector_message,
            },
            message="没有可重建索引的文档，请先新增知识文档",
        )

    try:
        total_chunks = rebuild_index_for_documents(
            documents=docs,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        return HertzResponse.success(
            data={"document_count": len(docs), "chunk_count": total_chunks},
            message="索引重建完成",
        )
    except Exception as exc:
        return HertzResponse.error(message=f"索引重建失败: {exc}")


@api_view(["GET"])
@login_required
def chat_session_list(request):
    query = (request.GET.get("query") or "").strip()
    page = _safe_int(request.GET.get("page"), 1, min_value=1)
    page_size = _safe_int(request.GET.get("page_size"), 10, min_value=1, max_value=100)

    q = Q(user_id=request.user_id)
    if query:
        q &= Q(title__icontains=query)

    sessions = HealthQASession.objects.filter(q).order_by("-updated_at")
    paginator = Paginator(sessions, page_size)
    page_obj = paginator.get_page(page)

    data_list = []
    for session in page_obj:
        first_record = (
            HealthQARecord.objects.filter(session=session)
            .order_by("created_at")
            .first()
        )
        latest = (
            HealthQARecord.objects.filter(session=session)
            .order_by("-created_at")
            .first()
        )
        display_title = (
            (first_record.question[:60] if first_record and first_record.question else "")
            or session.title
        )
        data_list.append(
            {
                "id": session.id,
                "title": display_title,
                "created_at": _format_dt(session.created_at),
                "updated_at": _format_dt(session.updated_at),
                "latest_question": latest.question[:60] if latest else "",
            }
        )

    return HertzResponse.success(
        data={
            "total": paginator.count,
            "page": page,
            "page_size": page_size,
            "list": data_list,
        }
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def chat_session_create(request):
    serializer = HealthQASessionCreateSerializer(data=_get_request_data(request))
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    title = (serializer.validated_data.get("title") or "新会话").strip() or "新会话"
    session = HealthQASession.objects.create(user_id=request.user_id, title=title)
    return HertzResponse.success(
        data={"session_id": session.id, "title": session.title},
        message="会话创建成功",
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def chat_session_delete(request):
    serializer = HealthQASessionDeleteSerializer(data=_get_request_data(request))
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    session_ids = serializer.validated_data["session_ids"]
    sessions = HealthQASession.objects.filter(
        id__in=session_ids, user_id=request.user_id
    )
    if not sessions.exists():
        return HertzResponse.not_found("会话不存在或无权删除")

    record_count = HealthQARecord.objects.filter(
        session_id__in=list(sessions.values_list("id", flat=True))
    ).count()
    session_count = sessions.count()
    sessions.delete()

    return HertzResponse.success(
        data={"session_count": session_count, "record_count": record_count},
        message="会话删除成功",
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def chat_transcribe(request):
    payload = _get_request_data(request)
    serializer = HealthChatTranscribeSerializer(data=payload)
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return HertzResponse.validation_error(message="请上传语音文件")

    try:
        result = transcribe_file(
            uploaded_file,
            language=serializer.validated_data.get("language"),
            audio_meta={
                "format": serializer.validated_data.get("format"),
                "rate": serializer.validated_data.get("rate"),
            },
            user_id=request.user_id,
        )
    except ASRServiceError as exc:
        return HertzResponse.fail(message=_format_asr_error(exc), code=422)
    except Exception as exc:
        return HertzResponse.error(message=_format_asr_error(exc))

    return HertzResponse.success(
        data={
            "transcript": result.get("text") or "",
            "duration_ms": int(result.get("duration_ms") or 0),
            "utterances": result.get("utterances") or [],
        },
        message="语音转写成功",
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def chat_ask(request):
    payload = _get_request_data(request)
    # 兼容前端大小写字段
    if payload.get("BASE_URL") and not payload.get("base_url"):
        payload["base_url"] = payload.get("BASE_URL")
    if payload.get("API_KEY") and not payload.get("api_key"):
        payload["api_key"] = payload.get("API_KEY")
    if payload.get("MODEL") and not payload.get("model"):
        payload["model"] = payload.get("MODEL")

    serializer = HealthChatAskSerializer(data=payload)
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    question = serializer.validated_data["question"]
    k = serializer.validated_data.get("k", int(getattr(settings, "RAG_TOP_K", 5)))
    session_id = serializer.validated_data.get("session_id")
    ask_mode = serializer.validated_data.get("ask_mode", "text")
    llm_config = {}
    if (serializer.validated_data.get("base_url") or "").strip():
        llm_config["base_url"] = serializer.validated_data.get("base_url").strip()
    if (serializer.validated_data.get("api_key") or "").strip():
        llm_config["api_key"] = serializer.validated_data.get("api_key").strip()
    if (serializer.validated_data.get("model") or "").strip():
        llm_config["model_name"] = serializer.validated_data.get("model").strip()

    if session_id:
        try:
            session = HealthQASession.objects.get(
                id=session_id, user_id=request.user_id
            )
        except HealthQASession.DoesNotExist:
            return HertzResponse.not_found("会话不存在或无权访问")
    else:
        title = question[:20] + ("..." if len(question) > 20 else "")
        session = HealthQASession.objects.create(user_id=request.user_id, title=title)

    conversation_history = _get_recent_conversation_history(session=session, limit=3)
    start = time.perf_counter()
    try:
        answer, sources = ask_with_rag(
            user_id=request.user_id,
            question=question,
            k=k,
            llm_config=llm_config,
            conversation_history=conversation_history,
        )
    except Exception as exc:
        return HertzResponse.error(message=f"问答失败: {exc}")

    latency_ms = int((time.perf_counter() - start) * 1000)
    knowledge_card = build_knowledge_card(
        question=question,
        answer=answer,
        sources=sources,
        llm_config=llm_config,
    )
    if session.title in {"", "新会话"}:
        session.title = question[:20] + ("..." if len(question) > 20 else "")
    record = HealthQARecord.objects.create(
        session=session,
        user_id=request.user_id,
        question=question,
        answer=answer,
        ask_mode=ask_mode,
        source_refs=sources,
        knowledge_card=knowledge_card,
        latency_ms=latency_ms,
    )
    session.save()  # 触发 updated_at

    return HertzResponse.success(
        data={
            "session_id": session.id,
            "record_id": record.id,
            "question": question,
            "ask_mode": ask_mode,
            "answer": answer,
            "sources": sources,
            "knowledge_card": knowledge_card,
            "latency_ms": latency_ms,
        }
    )


@api_view(["GET"])
@login_required
def chat_history(request):
    keyword = (request.GET.get("keyword") or "").strip()
    session_id = request.GET.get("session_id")
    start_time = (request.GET.get("start_time") or "").strip()
    end_time = (request.GET.get("end_time") or "").strip()
    page = _safe_int(request.GET.get("page"), 1, min_value=1)
    page_size = _safe_int(request.GET.get("page_size"), 10, min_value=1, max_value=100)

    q = Q(user_id=request.user_id)
    if session_id:
        q &= Q(session_id=_safe_int(session_id, -1))
    if keyword:
        keyword_q = Q(question__icontains=keyword) | Q(answer__icontains=keyword)
        q &= keyword_q

    records = HealthQARecord.objects.filter(q).order_by("-created_at")

    if start_time:
        dt = parse_datetime(start_time)
        if dt is None:
            d = parse_date(start_time)
            if d:
                dt = parse_datetime(f"{d} 00:00:00")
        if dt:
            records = records.filter(created_at__gte=dt)

    if end_time:
        dt = parse_datetime(end_time)
        if dt is None:
            d = parse_date(end_time)
            if d:
                dt = parse_datetime(f"{d} 23:59:59")
        if dt:
            records = records.filter(created_at__lte=dt)

    paginator = Paginator(records, page_size)
    page_obj = paginator.get_page(page)

    data_list = []
    for record in page_obj:
        data_list.append(
            {
                "id": record.id,
                "session_id": record.session_id,
                "question": record.question,
                "answer": record.answer,
                "ask_mode": record.ask_mode,
                "source_refs": record.source_refs,
                "knowledge_card": getattr(record, "knowledge_card", {}) or {},
                "latency_ms": record.latency_ms,
                "created_at": _format_dt(record.created_at),
            }
        )

    return HertzResponse.success(
        data={
            "total": paginator.count,
            "page": page,
            "page_size": page_size,
            "list": data_list,
        }
    )


@api_view(["GET"])
@login_required
def chat_history_sessions(request):
    keyword = (request.GET.get("keyword") or "").strip()
    session_id = request.GET.get("session_id")
    start_time = (request.GET.get("start_time") or "").strip()
    end_time = (request.GET.get("end_time") or "").strip()
    page = _safe_int(request.GET.get("page"), 1, min_value=1)
    page_size = _safe_int(request.GET.get("page_size"), 10, min_value=1, max_value=100)

    q = Q(user_id=request.user_id)
    if session_id:
        q &= Q(session_id=_safe_int(session_id, -1))
    if keyword:
        q &= Q(question__icontains=keyword) | Q(answer__icontains=keyword)

    records = HealthQARecord.objects.filter(q).select_related("session").order_by("-created_at")

    if start_time:
        dt = parse_datetime(start_time)
        if dt is None:
            d = parse_date(start_time)
            if d:
                dt = parse_datetime(f"{d} 00:00:00")
        if dt:
            records = records.filter(created_at__gte=dt)

    if end_time:
        dt = parse_datetime(end_time)
        if dt is None:
            d = parse_date(end_time)
            if d:
                dt = parse_datetime(f"{d} 23:59:59")
        if dt:
            records = records.filter(created_at__lte=dt)

    ordered_session_ids = []
    seen_session_ids = set()
    for record in records:
        if record.session_id in seen_session_ids:
            continue
        seen_session_ids.add(record.session_id)
        ordered_session_ids.append(record.session_id)

    paginator = Paginator(ordered_session_ids, page_size)
    page_obj = paginator.get_page(page)

    data_list = []
    for sid in page_obj.object_list:
        session = HealthQASession.objects.filter(id=sid, user_id=request.user_id).first()
        if not session:
            continue
        session_records = HealthQARecord.objects.filter(
            session_id=sid,
            user_id=request.user_id,
        ).order_by("created_at")
        first_record = session_records.first()
        latest_record = session_records.order_by("-created_at").first()
        record_count = session_records.count()
        title = (
            (first_record.question[:60] if first_record and first_record.question else "")
            or session.title
        )
        data_list.append(
            {
                "id": session.id,
                "title": title,
                "latest_question": latest_record.question[:80] if latest_record else "",
                "record_count": record_count,
                "created_at": _format_dt(session.created_at),
                "updated_at": _format_dt(latest_record.created_at if latest_record else session.updated_at),
            }
        )

    return HertzResponse.success(
        data={
            "total": paginator.count,
            "page": page,
            "page_size": page_size,
            "list": data_list,
        }
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def chat_history_export_pdf(request):
    serializer = HealthHistoryExportPdfSerializer(data=_get_request_data(request))
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    payload = serializer.validated_data
    record_ids = payload.get("record_ids") or []
    session_id = payload.get("session_id")
    keyword = (payload.get("keyword") or "").strip()
    start_time = (payload.get("start_time") or "").strip()
    end_time = (payload.get("end_time") or "").strip()
    limit = payload.get("limit", 100)

    q = Q(user_id=request.user_id)
    if record_ids:
        q &= Q(id__in=record_ids)
    if session_id:
        q &= Q(session_id=session_id)
    if keyword:
        keyword_q = Q(question__icontains=keyword) | Q(answer__icontains=keyword)
        q &= keyword_q

    records = HealthQARecord.objects.filter(q).order_by("created_at")

    if start_time:
        dt = parse_datetime(start_time)
        if dt is None:
            d = parse_date(start_time)
            if d:
                dt = parse_datetime(f"{d} 00:00:00")
        if dt:
            records = records.filter(created_at__gte=dt)

    if end_time:
        dt = parse_datetime(end_time)
        if dt is None:
            d = parse_date(end_time)
            if d:
                dt = parse_datetime(f"{d} 23:59:59")
        if dt:
            records = records.filter(created_at__lte=dt)

    if not record_ids:
        records = records[:limit]

    export_records = list(records)
    if not export_records:
        return HertzResponse.not_found("没有可导出的问答记录")

    owner_label = str(
        getattr(getattr(request, "user", None), "username", "")
        or getattr(getattr(request, "user", None), "real_name", "")
        or request.user_id
    )

    try:
        pdf_bytes = build_qa_records_pdf(export_records, owner_label=owner_label)
    except Exception as exc:
        return HertzResponse.error(message=f"问答记录导出 PDF 失败: {exc}")

    filename = f"health-qa-history-{timezone.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api_view(["GET"])
@login_required
def recommend_list(request):
    serializer = HealthRecommendSerializer(data=request.GET.dict())
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    payload = serializer.validated_data
    try:
        result = build_personal_recommendations(
            user_id=request.user_id,
            limit=payload.get("limit", 8),
            history_days=payload.get("history_days", 90),
            topic_count=payload.get("topic_count", 3),
            k_per_topic=payload.get("k_per_topic", 3),
            randomize=payload.get("randomize", False),
        )
        return HertzResponse.success(data=result)
    except Exception as exc:
        return HertzResponse.error(message=f"健康知识推荐失败: {exc}")


@api_view(["GET"])
@login_required
def model_status(_request):
    service = HealthLLMService()
    status = service.get_model_status()
    status["embedding"] = EmbeddingService().status()
    status["vector_store"] = QdrantVectorStore().status()
    return HertzResponse.success(data=status)


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def model_status_custom(request):
    data = _get_request_data(request)

    base_url = (data.get("BASE_URL") or data.get("base_url") or "").strip() or None
    api_key = (data.get("API_KEY") or data.get("api_key") or "").strip() or None
    model_name = (data.get("MODEL") or data.get("model") or "").strip() or None

    if not any([base_url, api_key, model_name]):
        return HertzResponse.validation_error(
            message="请至少提供一个自定义参数：BASE_URL / API_KEY / MODEL"
        )

    service = HealthLLMService()
    status = service.get_model_status(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
    )
    status["custom"] = True
    status["embedding"] = EmbeddingService().status()
    status["vector_store"] = QdrantVectorStore().status()
    return HertzResponse.success(data=status, message="自定义模型状态检测完成")


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def model_switch(request):
    deny_response = _require_kb_admin(request)
    if deny_response:
        return deny_response

    data = _get_request_data(request)
    normalized_payload = {
        "base_url": data.get("BASE_URL") or data.get("base_url") or "",
        "api_key": data.get("API_KEY") or data.get("api_key") or "",
        "model": data.get("MODEL") or data.get("model") or "",
    }
    serializer = HealthModelSwitchSerializer(data=normalized_payload)
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    validated = serializer.validated_data
    service = HealthLLMService()
    try:
        result = service.switch_model(
            model_name=(validated.get("model") or "").strip(),
            base_url=(validated.get("base_url") or "").strip() or None,
            api_key=(validated.get("api_key") or "").strip() or None,
        )
        status = result.get("status", {}) or {}
        status["embedding"] = EmbeddingService().status()
        status["vector_store"] = QdrantVectorStore().status()
        result["status"] = status
        return HertzResponse.success(data=result, message="模型切换成功")
    except Exception as exc:
        return HertzResponse.error(message=f"模型切换失败: {exc}")


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def model_restart(request):
    deny_response = _require_kb_admin(request)
    if deny_response:
        return deny_response

    data = _get_request_data(request)
    normalized_payload = {
        "base_url": data.get("BASE_URL") or data.get("base_url") or "",
        "api_key": data.get("API_KEY") or data.get("api_key") or "",
        "model": data.get("MODEL") or data.get("model") or "",
        "warmup": data.get("warmup", True),
    }
    serializer = HealthModelControlSerializer(data=normalized_payload)
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    validated = serializer.validated_data
    service = HealthLLMService()
    try:
        result = service.restart_model(
            base_url=(validated.get("base_url") or "").strip() or None,
            api_key=(validated.get("api_key") or "").strip() or None,
            model_name=(validated.get("model") or "").strip() or None,
            warmup=bool(validated.get("warmup", True)),
        )
        status = result.get("status", {}) or {}
        status["embedding"] = EmbeddingService().status()
        status["vector_store"] = QdrantVectorStore().status()
        result["status"] = status
        return HertzResponse.success(data=result, message="模型重启成功")
    except Exception as exc:
        return HertzResponse.error(message=f"模型重启失败: {exc}")


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def retrieval_debug(request):
    serializer = HealthRetrievalDebugSerializer(data=_get_request_data(request))
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    question = serializer.validated_data["question"]
    top_k = serializer.validated_data.get("top_k", int(getattr(settings, "RAG_TOP_K", 5)))
    started = time.perf_counter()
    try:
        retrieval = retrieve_hybrid(
            question=question,
            conversation_history=None,
            vector_k=max(top_k, int(getattr(settings, "RAG_VECTOR_TOP_K", 30))),
            sparse_k=max(top_k, int(getattr(settings, "RAG_VECTOR_TOP_K", 30))),
            fused_k=max(top_k, 20),
        )
    except Exception as exc:
        return HertzResponse.error(message=f"检索调试失败: {exc}")

    return HertzResponse.success(
        data={
            "question": question,
            "rewritten_query": retrieval.get("retrieval_query", ""),
            "top_k": top_k,
            "query_embedding_dim": retrieval.get("query_embedding_dim", 0),
            "vector_hits": retrieval.get("vector_hits", [])[:top_k],
            "sparse_hits": retrieval.get("sparse_hits", [])[:top_k],
            "rrf_hits": retrieval.get("rrf_hits", [])[:top_k],
            "rerank_hits": retrieval.get("rerank_hits", [])[:top_k],
            "final_hits": retrieval.get("final_hits", [])[:top_k],
            "final_contexts": retrieval.get("contexts", []),
            "rerank_error": retrieval.get("rerank_error", ""),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        },
        message="检索调试完成",
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def ragas_eval_run(request):
    deny_response = _require_kb_admin(request)
    if deny_response:
        return deny_response

    serializer = HealthRagasEvalRunSerializer(data=_get_request_data(request))
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    payload = serializer.validated_data
    started = time.perf_counter()
    out = StringIO()
    err = StringIO()
    try:
        call_command(
            "evaluate_health_rag_ragas",
            input=(payload.get("input") or "health_eval_questions_cmedqa_v1.jsonl"),
            top_k=int(payload.get("top_k") or 5),
            limit=int(payload.get("limit") or 20),
            user_id=int(getattr(request, "user_id", 1) or 1),
            stdout=out,
            stderr=err,
        )
    except Exception as exc:
        stderr_text = err.getvalue().strip()
        detail = f"；stderr: {stderr_text}" if stderr_text else ""
        return HertzResponse.error(message=f"RAGAS 评估启动失败: {exc}{detail}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    base_dir = Path(settings.BASE_DIR) / "health_rag_assistant" / "datasets" / "eval" / "results"
    latest_result = ""
    if base_dir.exists():
        files = sorted(base_dir.glob("eval_ragas_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            latest_result = str(files[0])

    return HertzResponse.success(
        data={
            "elapsed_ms": elapsed_ms,
            "latest_result_file": latest_result,
            "stdout": _strip_ansi(out.getvalue()).strip(),
            "stderr": _strip_ansi(err.getvalue()).strip(),
        },
        message="RAGAS 评估已完成",
    )


@api_view(["POST"])
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def retrieval_eval_run(request):
    deny_response = _require_kb_admin(request)
    if deny_response:
        return deny_response

    serializer = HealthRetrievalEvalRunSerializer(data=_get_request_data(request))
    if not serializer.is_valid():
        return HertzResponse.validation_error(errors=serializer.errors)

    payload = serializer.validated_data
    started = time.perf_counter()
    out = StringIO()
    err = StringIO()
    try:
        call_command(
            "evaluate_health_rag",
            input=(payload.get("input") or "health_eval_questions_cmedqa_v1.jsonl"),
            top_k=int(payload.get("top_k") or 5),
            limit=int(payload.get("limit") or 20),
            stdout=out,
            stderr=err,
        )
    except Exception as exc:
        stderr_text = err.getvalue().strip()
        detail = f"；stderr: {stderr_text}" if stderr_text else ""
        return HertzResponse.error(message=f"检索评估启动失败: {exc}{detail}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    base_dir = Path(settings.BASE_DIR) / "health_rag_assistant" / "datasets" / "eval" / "results"
    latest_result = ""
    if base_dir.exists():
        files = sorted(base_dir.glob("eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            latest_result = str(files[0])

    return HertzResponse.success(
        data={
            "elapsed_ms": elapsed_ms,
            "latest_result_file": latest_result,
            "stdout": _strip_ansi(out.getvalue()).strip(),
            "stderr": _strip_ansi(err.getvalue()).strip(),
        },
        message="检索评估已完成",
    )
