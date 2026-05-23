"""
请求/响应序列化器
- 定义所有 API 接口的请求参数校验和响应格式
- 包含健康知识文档、会话、问答记录、模型配置的序列化
"""
from rest_framework import serializers

from .models import (
    HealthKnowledgeChunk,
    HealthKnowledgeDocument,
    HealthQARecord,
    HealthQASession,
)


class HealthKnowledgeDocumentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=True)
    source_type = serializers.ChoiceField(
        choices=["manual", "file", "url"], required=False, default="manual"
    )
    source_path = serializers.CharField(required=False, allow_blank=True, default="")
    content = serializers.CharField(required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)
    split_mode = serializers.ChoiceField(
        choices=["fixed", "markdown_entry"], required=False, default="fixed"
    )
    chunk_size = serializers.IntegerField(
        required=False, default=500, min_value=100, max_value=2000
    )
    chunk_overlap = serializers.IntegerField(
        required=False, default=80, min_value=0, max_value=300
    )

    def validate(self, attrs):
        source_type = attrs.get("source_type", "manual")
        content = (attrs.get("content") or "").strip()
        chunk_size = attrs.get("chunk_size", 500)
        chunk_overlap = attrs.get("chunk_overlap", 80)

        if chunk_overlap >= chunk_size:
            raise serializers.ValidationError("chunk_overlap 必须小于 chunk_size")

        if source_type in {"manual", "url"} and not content:
            raise serializers.ValidationError(
                "source_type 为 manual/url 时 content 不能为空"
            )
        return attrs


class HealthKnowledgeDocumentDeleteSerializer(serializers.Serializer):
    document_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        required=True,
    )


class HealthKnowledgeDocumentUpdateSerializer(serializers.Serializer):
    document_id = serializers.IntegerField(min_value=1, required=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    source_path = serializers.CharField(required=False, allow_blank=True)
    content = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)
    reindex = serializers.BooleanField(required=False, default=False)
    chunk_size = serializers.IntegerField(
        required=False, default=500, min_value=100, max_value=2000
    )
    chunk_overlap = serializers.IntegerField(
        required=False, default=80, min_value=0, max_value=300
    )

    def validate(self, attrs):
        has_update_field = any(
            field in attrs for field in ("title", "source_path", "content", "metadata")
        )
        has_reindex_field = any(
            field in attrs for field in ("reindex", "chunk_size", "chunk_overlap")
        )
        if not has_update_field and not has_reindex_field:
            raise serializers.ValidationError("至少提供一个可更新字段")

        if "title" in attrs and not (attrs.get("title") or "").strip():
            raise serializers.ValidationError("标题不能为空")

        if "content" in attrs and not (attrs.get("content") or "").strip():
            raise serializers.ValidationError("内容不能为空")

        chunk_size = attrs.get("chunk_size", 500)
        chunk_overlap = attrs.get("chunk_overlap", 80)
        if chunk_overlap >= chunk_size:
            raise serializers.ValidationError("chunk_overlap 必须小于 chunk_size")

        # 只要更新内容，默认重建索引，保证检索一致性
        if "content" in attrs and "reindex" not in attrs:
            attrs["reindex"] = True
        return attrs


class HealthKnowledgeReindexSerializer(serializers.Serializer):
    document_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    chunk_size = serializers.IntegerField(
        required=False, default=500, min_value=100, max_value=2000
    )
    chunk_overlap = serializers.IntegerField(
        required=False, default=80, min_value=0, max_value=300
    )

    def validate(self, attrs):
        chunk_size = attrs.get("chunk_size", 500)
        chunk_overlap = attrs.get("chunk_overlap", 80)
        if chunk_overlap >= chunk_size:
            raise serializers.ValidationError("chunk_overlap 必须小于 chunk_size")
        return attrs


class HealthQASessionCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, default="新会话")


class HealthQASessionDeleteSerializer(serializers.Serializer):
    session_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        required=True,
    )


class HealthChatAskSerializer(serializers.Serializer):
    question = serializers.CharField(required=True)
    session_id = serializers.IntegerField(required=False, min_value=1)
    k = serializers.IntegerField(required=False, default=5, min_value=1, max_value=10)
    base_url = serializers.CharField(required=False, allow_blank=True, default="")
    api_key = serializers.CharField(required=False, allow_blank=True, default="")
    model = serializers.CharField(required=False, allow_blank=True, default="")
    ask_mode = serializers.ChoiceField(
        choices=[choice[0] for choice in HealthQARecord.ASK_MODE_CHOICES],
        required=False,
        default="text",
    )

    def validate_question(self, value):
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError("问题不能为空")
        return text


class HealthChatTranscribeSerializer(serializers.Serializer):
    language = serializers.CharField(required=False, allow_blank=True, default="")
    format = serializers.CharField(required=False, allow_blank=True, default="")
    rate = serializers.IntegerField(required=False, default=16000, min_value=8000, max_value=48000)


class HealthRecommendSerializer(serializers.Serializer):
    limit = serializers.IntegerField(
        required=False, default=8, min_value=1, max_value=20
    )
    history_days = serializers.IntegerField(
        required=False, default=90, min_value=1, max_value=365
    )
    topic_count = serializers.IntegerField(
        required=False, default=3, min_value=1, max_value=8
    )
    k_per_topic = serializers.IntegerField(
        required=False, default=3, min_value=1, max_value=10
    )
    randomize = serializers.BooleanField(required=False, default=False)


class HealthHistoryExportPdfSerializer(serializers.Serializer):
    record_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=False,
    )
    session_id = serializers.IntegerField(required=False, min_value=1)
    keyword = serializers.CharField(required=False, allow_blank=True, default="")
    start_time = serializers.CharField(required=False, allow_blank=True, default="")
    end_time = serializers.CharField(required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(
        required=False, default=100, min_value=1, max_value=500
    )


class HealthModelControlSerializer(serializers.Serializer):
    base_url = serializers.CharField(required=False, allow_blank=True, default="")
    api_key = serializers.CharField(required=False, allow_blank=True, default="")
    model = serializers.CharField(required=False, allow_blank=True, default="")
    warmup = serializers.BooleanField(required=False, default=True)


class HealthModelSwitchSerializer(HealthModelControlSerializer):
    model = serializers.CharField(required=True, allow_blank=False)


class HealthRetrievalDebugSerializer(serializers.Serializer):
    question = serializers.CharField(required=True)
    top_k = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)

    def validate_question(self, value):
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError("问题不能为空")
        return text


class HealthRagasEvalRunSerializer(serializers.Serializer):
    input = serializers.CharField(
        required=False,
        allow_blank=True,
        default="health_eval_questions_cmedqa_v1.jsonl",
    )
    top_k = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)
    limit = serializers.IntegerField(required=False, default=20, min_value=1, max_value=500)


class HealthRetrievalEvalRunSerializer(serializers.Serializer):
    input = serializers.CharField(
        required=False,
        allow_blank=True,
        default="health_eval_questions_cmedqa_v1.jsonl",
    )
    top_k = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)
    limit = serializers.IntegerField(required=False, default=20, min_value=1, max_value=500)


class HealthKnowledgeDocumentSerializer(serializers.ModelSerializer):
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = HealthKnowledgeDocument
        fields = [
            "id",
            "title",
            "source_type",
            "source_path",
            "content",
            "status",
            "metadata",
            "created_at",
            "updated_at",
            "chunk_count",
        ]

    def get_chunk_count(self, obj):
        annotated = getattr(obj, "chunk_count_annotated", None)
        if annotated is not None:
            return int(annotated)
        return obj.chunks.count()


class HealthQASessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthQASession
        fields = ["id", "title", "created_at", "updated_at"]


class HealthQARecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthQARecord
        fields = [
            "id",
            "session_id",
            "question",
            "answer",
            "ask_mode",
            "source_refs",
            "latency_ms",
            "created_at",
        ]


class HealthKnowledgeChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthKnowledgeChunk
        fields = [
            "id",
            "document_id",
            "chunk_index",
            "chunk_text",
            "token_count",
            "vector_id",
            "created_at",
        ]
