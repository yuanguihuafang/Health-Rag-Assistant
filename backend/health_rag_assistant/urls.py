"""
健康 RAG 路由表
前缀：/api/health-rag/
"""
from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health_check, name="health_rag_health"),
    path("kb/documents/", views.kb_document_list, name="health_rag_kb_document_list"),
    path(
        "kb/documents/create/",
        views.kb_document_create,
        name="health_rag_kb_document_create",
    ),
    path(
        "kb/documents/update/",
        views.kb_document_update,
        name="health_rag_kb_document_update",
    ),
    path(
        "kb/documents/delete/",
        views.kb_document_delete,
        name="health_rag_kb_document_delete",
    ),
    path("kb/reindex/", views.kb_reindex, name="health_rag_kb_reindex"),
    path(
        "chat/sessions/", views.chat_session_list, name="health_rag_chat_session_list"
    ),
    path(
        "chat/sessions/create/",
        views.chat_session_create,
        name="health_rag_chat_session_create",
    ),
    path(
        "chat/sessions/delete/",
        views.chat_session_delete,
        name="health_rag_chat_session_delete",
    ),
    path(
        "chat/transcribe/",
        views.chat_transcribe,
        name="health_rag_chat_transcribe",
    ),
    path("chat/ask/", views.chat_ask, name="health_rag_chat_ask"),
    path("chat/history/", views.chat_history, name="health_rag_chat_history"),
    path(
        "chat/history/sessions/",
        views.chat_history_sessions,
        name="health_rag_chat_history_sessions",
    ),
    path(
        "chat/history/export/pdf/",
        views.chat_history_export_pdf,
        name="health_rag_chat_history_export_pdf",
    ),
    path("recommend/", views.recommend_list, name="health_rag_recommend_list"),
    path("model/status/", views.model_status, name="health_rag_model_status"),
    path(
        "model/status/custom/",
        views.model_status_custom,
        name="health_rag_model_status_custom",
    ),
    path(
        "model/switch/",
        views.model_switch,
        name="health_rag_model_switch",
    ),
    path(
        "model/restart/",
        views.model_restart,
        name="health_rag_model_restart",
    ),
]
