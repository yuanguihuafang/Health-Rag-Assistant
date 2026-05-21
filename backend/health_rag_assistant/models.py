"""
数据模型
- HealthKnowledgeDocument / HealthKnowledgeChunk：知识文档与分块
- HealthQASession / HealthQARecord：问答会话与记录（含语音模式、知识卡片）
"""
from django.conf import settings
from django.db import models


class HealthKnowledgeDocument(models.Model):
    SOURCE_CHOICES = (
        ("manual", "manual"),
        ("file", "file"),
        ("url", "url"),
    )

    STATUS_CHOICES = (
        ("active", "active"),
        ("deleted", "deleted"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    source_type = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default="manual"
    )
    source_path = models.CharField(max_length=500, blank=True, default="")
    content = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "health_rag_knowledge_document"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["source_type"]),
        ]


class HealthKnowledgeChunk(models.Model):
    document = models.ForeignKey(
        HealthKnowledgeDocument, on_delete=models.CASCADE, related_name="chunks"
    )
    chunk_index = models.IntegerField(default=0)
    chunk_text = models.TextField()
    token_count = models.IntegerField(default=0)
    vector_id = models.IntegerField(null=True, blank=True)
    embedding = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "health_rag_knowledge_chunk"
        ordering = ["document_id", "chunk_index"]
        unique_together = [("document", "chunk_index")]
        indexes = [
            models.Index(fields=["document", "chunk_index"]),
        ]


class HealthQASession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, default="新会话")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "health_rag_qa_session"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "updated_at"]),
        ]


class HealthQARecord(models.Model):
    ASK_MODE_CHOICES = (
        ("text", "text"),
        ("voice", "voice"),
    )

    session = models.ForeignKey(
        HealthQASession, on_delete=models.CASCADE, related_name="records"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField(blank=True, default="")
    ask_mode = models.CharField(max_length=20, choices=ASK_MODE_CHOICES, default="text")
    source_refs = models.JSONField(default=list, blank=True)
    # 结构化知识卡片（用于快速查阅与分享；默认空对象）
    knowledge_card = models.JSONField(default=dict, blank=True)
    latency_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "health_rag_qa_record"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["session", "created_at"]),
        ]
