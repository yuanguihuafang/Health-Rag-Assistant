"""
Django Admin 后台注册
"""
from django.contrib import admin

from .models import (
    HealthKnowledgeChunk,
    HealthKnowledgeDocument,
    HealthQARecord,
    HealthQASession,
)


@admin.register(HealthKnowledgeDocument)
class HealthKnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "source_type", "status", "updated_at")
    search_fields = ("title", "source_path")
    list_filter = ("source_type", "status", "created_at")


@admin.register(HealthKnowledgeChunk)
class HealthKnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "chunk_index", "token_count", "created_at")
    search_fields = ("document__title", "chunk_text")
    list_filter = ("created_at",)


@admin.register(HealthQASession)
class HealthQASessionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "updated_at", "created_at")
    search_fields = ("title", "user__username")
    list_filter = ("created_at",)


@admin.register(HealthQARecord)
class HealthQARecordAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "user", "ask_mode", "latency_ms", "created_at")
    search_fields = ("question", "answer")
    list_filter = ("ask_mode", "created_at")
