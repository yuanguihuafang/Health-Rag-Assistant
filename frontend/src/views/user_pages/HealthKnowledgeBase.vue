<template>
  <div class="health-kb-page">
    <div class="page-hero">
      <div class="hero-content">
        <h1>健康知识库管理</h1>
        <p>浏览健康知识文档并查看正文内容，便于验证问答命中效果</p>
      </div>
      <a-button :loading="documentLoading" @click="loadDocuments">
        <template #icon><ReloadOutlined /></template>
        刷新列表
      </a-button>
    </div>

    <a-card :bordered="false">
      <div class="section-toolbar">
        <a-space wrap>
          <a-input-search
            v-model:value="documentQuery.query"
            placeholder="按文档标题搜索"
            enter-button
            @search="loadDocuments"
          />
        </a-space>
      </div>

      <a-table
        :loading="documentLoading"
        :columns="documentColumns"
        :data-source="documentList"
        :pagination="{
          current: documentPagination.page,
          pageSize: documentPagination.page_size,
          total: documentPagination.total,
          showSizeChanger: true,
        }"
        row-key="id"
        size="middle"
        @change="handleDocumentTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'id'">
            <span class="doc-id">#{{ getDocumentDisplayNumber(record) }}</span>
          </template>
          <template v-else-if="column.key === 'title'">
            <div class="doc-title-cell">
              <div class="doc-title">{{ record.title }}</div>
              <a-tooltip :title="record.source_path || '手动录入'">
                <div class="doc-path">{{ formatSourceLabel(record) }}</div>
              </a-tooltip>
            </div>
          </template>
          <template v-else-if="column.key === 'source_type'">
            <a-tag :color="record.source_type === 'file' ? 'blue' : 'green'">
              {{ formatSourceType(record.source_type) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'chunk_count'">
            <span class="chunk-count">{{ record.chunk_count || 0 }} 个</span>
          </template>
          <template v-else-if="column.key === 'content_preview'">
            <div class="content-preview">{{ getContentPreview(record.content) }}</div>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button type="link" size="small" @click="openDocumentDetail(record)">
              <template #icon><EyeOutlined /></template>
              查看内容
            </a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-drawer
      v-model:visible="detailVisible"
      :title="currentDocument?.title || '文档详情'"
      width="760"
      placement="right"
    >
      <a-descriptions bordered :column="1" size="small" class="detail-meta">
        <a-descriptions-item label="文档ID">
          {{ currentDocument?.id || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="来源类型">
          {{ currentDocument?.source_type || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="来源说明">
          {{ currentDocument ? formatSourceLabel(currentDocument) : '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="内部路径">
          <span class="internal-path">{{ currentDocument?.source_path || '-' }}</span>
        </a-descriptions-item>
        <a-descriptions-item label="切片数">
          {{ currentDocument?.chunk_count || 0 }}
        </a-descriptions-item>
        <a-descriptions-item label="更新时间">
          {{ currentDocument?.updated_at || '-' }}
        </a-descriptions-item>
      </a-descriptions>

      <div class="content-title">正文内容</div>
      <div class="content-panel">{{ currentDocument?.content || '暂无正文内容' }}</div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { message } from "ant-design-vue";
import { EyeOutlined, ReloadOutlined } from "@ant-design/icons-vue";
import { healthRagApi, type HealthKnowledgeDocument } from "@/api/health_rag";

const route = useRoute();
const documentQuery = reactive({ query: "" });
const documentLoading = ref(false);
const documentList = ref<HealthKnowledgeDocument[]>([]);
const documentPagination = reactive({ total: 0, page: 1, page_size: 10 });

const detailVisible = ref(false);
const currentDocument = ref<HealthKnowledgeDocument | null>(null);

const documentColumns = [
  { title: "编号", dataIndex: "id", key: "id", width: 72, align: "center" },
  { title: "知识条目", dataIndex: "title", key: "title", width: 360 },
  { title: "来源", dataIndex: "source_type", key: "source_type", width: 96, align: "center" },
  { title: "切片", dataIndex: "chunk_count", key: "chunk_count", width: 80, align: "center" },
  { title: "内容预览", dataIndex: "content", key: "content_preview" },
  { title: "更新时间", dataIndex: "updated_at", key: "updated_at", width: 168 },
  { title: "操作", key: "action", width: 112, align: "center" },
];

const getContentPreview = (content?: string) => {
  const text = (content || "").replace(/\s+/g, " ").trim();
  if (!text) return "暂无内容";
  return text.length > 120 ? `${text.slice(0, 120)}...` : text;
};

const formatSourceType = (sourceType?: string) => {
  const sourceTypeMap: Record<string, string> = {
    file: "文件",
    manual: "手动",
    url: "链接",
  };
  return sourceTypeMap[sourceType || ""] || sourceType || "-";
};

const getDocumentDisplayNumber = (doc: HealthKnowledgeDocument) => {
  const sampleNo = Number(doc.metadata?.sample_no || 0);
  return Number.isFinite(sampleNo) && sampleNo > 0 ? sampleNo : doc.id;
};

const padEntryNo = (value: number) => String(value).padStart(3, "0");

const formatSourceLabel = (doc: HealthKnowledgeDocument) => {
  const metadata = doc.metadata || {};
  const dataset = String(metadata.dataset || "");
  const sampleNo = Number(metadata.sample_no || 0);
  const curatedNo = Number(metadata.curated_no || 0);

  if (dataset === "cMedQA sample" && sampleNo > 0) {
    return `默认健康问答语料 · 样本 ${sampleNo}`;
  }

  const curatedMap: Record<string, string> = {
    health_curated_lifestyle: "健康生活方式语料",
    health_curated_body_systems: "身体系统健康语料",
    health_curated_population_risk: "人群与风险识别语料",
  };
  if (curatedMap[dataset] && curatedNo > 0) {
    const topic = metadata.topic ? ` · ${metadata.topic}` : "";
    return `${curatedMap[dataset]}${topic} · 条目 ${padEntryNo(curatedNo)}`;
  }

  const sourcePath = (doc.source_path || "").trim();
  if (!sourcePath) return "手动录入";

  const sampleMatch = sourcePath.match(/#sample-(\d+)$/);
  if (sampleMatch) return `默认健康问答语料 · 样本 ${sampleMatch[1]}`;

  const entryMatch = sourcePath.match(/#entry-(\d+)$/);
  if (entryMatch) return `健康知识扩展语料 · 条目 ${padEntryNo(Number(entryMatch[1]))}`;

  const pathWithoutHash = sourcePath.split("#")[0] || sourcePath;
  const fileName = pathWithoutHash.split(/[\\/]/).filter(Boolean).pop();
  return fileName || sourcePath;
};

const getRouteDocumentId = () => {
  const raw = route.query.document_id;
  const value = Array.isArray(raw) ? raw[0] : raw;
  const documentId = Number(value || 0);
  return Number.isFinite(documentId) && documentId > 0 ? documentId : 0;
};

const loadDocuments = async (options: { openRouteDocument?: boolean } = {}) => {
  documentLoading.value = true;
  const routeDocumentId = getRouteDocumentId();
  try {
    const res = await healthRagApi.listDocuments({
      document_id: routeDocumentId || undefined,
      query: documentQuery.query,
      page: documentPagination.page,
      page_size: documentPagination.page_size,
    });
    if (!res.success) {
      message.error(res.message || "加载知识库失败");
      return;
    }
    documentList.value = res.data.list || [];
    documentPagination.total = res.data.total || 0;
    if (options.openRouteDocument && routeDocumentId) {
      const target = documentList.value.find((item) => item.id === routeDocumentId);
      if (target) {
        openDocumentDetail(target);
      } else {
        detailVisible.value = false;
        currentDocument.value = null;
        message.warning("未找到对应知识库原文，可能已被删除或暂无权限查看");
      }
    }
  } catch (error: any) {
    message.error(error?.message || "加载知识库失败");
  } finally {
    documentLoading.value = false;
  }
};

const handleDocumentTableChange = (pagination: any) => {
  documentPagination.page = pagination?.current || 1;
  documentPagination.page_size = pagination?.pageSize || 10;
  loadDocuments();
};

const openDocumentDetail = (doc: HealthKnowledgeDocument) => {
  currentDocument.value = doc;
  detailVisible.value = true;
};

onMounted(() => {
  loadDocuments({ openRouteDocument: true });
});

watch(
  () => route.query.document_id,
  () => {
    documentPagination.page = 1;
    loadDocuments({ openRouteDocument: true });
  },
);
</script>

<style scoped>
.health-kb-page {
  min-height: 100%;
  padding: 8px;
  background: var(--theme-page-bg, #f6f9fc);
  color: var(--theme-text-primary, #111827);
}

.page-hero {
  border-radius: 14px;
  padding: 18px 20px;
  margin-bottom: 14px;
  background: linear-gradient(
    135deg,
    var(--theme-content-bg, #ffffff) 0%,
    var(--theme-card-bg, #ffffff) 100%
  );
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-left: 4px solid var(--theme-primary, #2563eb);
  color: var(--theme-text-primary, #111827);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.08);
}

.hero-content h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.hero-content p {
  margin: 8px 0 0;
  color: var(--theme-text-secondary, #6b7280);
}

.section-toolbar {
  width: 100%;
  margin-bottom: 16px;
}

.doc-id {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  height: 26px;
  border-radius: 6px;
  background: var(--theme-content-bg, #f8fafc);
  color: var(--theme-text-secondary, #6b7280);
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.doc-title-cell {
  min-width: 0;
}

.doc-title {
  color: var(--theme-text-primary, #111827);
  font-size: 15px;
  font-weight: 650;
  line-height: 1.45;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.doc-path {
  display: inline-flex;
  max-width: 100%;
  margin-top: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f1f6ff;
  color: var(--theme-text-secondary, #6b7280);
  font-size: 12px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: top;
}

.chunk-count {
  color: var(--theme-text-secondary, #6b7280);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.content-preview {
  color: var(--theme-text-secondary, #6b7280);
  line-height: 1.65;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.detail-meta {
  margin-bottom: 14px;
}

.internal-path {
  color: var(--theme-text-secondary, #6b7280);
  font-size: 12px;
  word-break: break-all;
}

.content-title {
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--theme-text-primary, #111827);
}

.content-panel {
  white-space: pre-wrap;
  line-height: 1.75;
  color: var(--theme-text-primary, #111827);
  background: var(--theme-content-bg, #ffffff);
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-radius: 10px;
  padding: 12px;
}

.health-kb-page :deep(.ant-card) {
  background: var(--theme-content-bg, #ffffff);
  border: 1px solid var(--theme-card-border, #e5e7eb);
}

.health-kb-page :deep(.ant-btn-default) {
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
  border-color: var(--theme-card-border, #e5e7eb);
}

.health-kb-page :deep(.ant-btn-default:hover),
.health-kb-page :deep(.ant-btn-default:focus) {
  color: var(--theme-primary, #2563eb);
  border-color: var(--theme-primary, #2563eb);
  background: var(--theme-card-bg, #ffffff);
}

.health-kb-page :deep(.ant-btn-link) {
  color: var(--theme-primary, #2563eb);
}

.health-kb-page :deep(.ant-input),
.health-kb-page :deep(.ant-input-group-addon),
.health-kb-page :deep(.ant-input-search-button) {
  background: var(--theme-card-bg, #ffffff);
  border-color: var(--theme-card-border, #e5e7eb);
  color: var(--theme-text-primary, #111827);
}

.health-kb-page :deep(.ant-table-wrapper) {
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-radius: 10px;
  overflow: hidden;
  background: var(--theme-card-bg, #ffffff);
}

.health-kb-page :deep(.ant-table) {
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
}

.health-kb-page :deep(.ant-table-thead > tr > th) {
  background: var(--theme-content-bg, #f8fafc);
  color: var(--theme-text-primary, #111827);
  border-bottom: 1px solid var(--theme-card-border, #e5e7eb);
}

.health-kb-page :deep(.ant-table-tbody > tr > td) {
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
  border-bottom: 1px solid var(--theme-card-border, #e5e7eb);
  vertical-align: top;
}

.health-kb-page :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--theme-content-bg, #f8fafc);
}

.health-kb-page :deep(.ant-drawer-content),
.health-kb-page :deep(.ant-drawer-header),
.health-kb-page :deep(.ant-drawer-body) {
  background: var(--theme-content-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
}

.health-kb-page :deep(.ant-drawer-header) {
  border-bottom: 1px solid var(--theme-card-border, #e5e7eb);
}

.health-kb-page :deep(.ant-descriptions-bordered .ant-descriptions-item-label),
.health-kb-page :deep(.ant-descriptions-bordered .ant-descriptions-item-content) {
  border-color: var(--theme-card-border, #e5e7eb);
  color: var(--theme-text-primary, #111827);
  background: var(--theme-card-bg, #ffffff);
}

@media (max-width: 768px) {
  .page-hero {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
