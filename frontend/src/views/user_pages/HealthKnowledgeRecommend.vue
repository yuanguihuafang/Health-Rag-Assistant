<template>
  <div class="health-recommend-page">
    <div class="page-hero">
      <div class="hero-content">
        <h1>健康知识推荐</h1>
        <p>基于你的历史问答偏好，自动推荐更相关的健康知识内容</p>
      </div>
      <a-space wrap>
        <a-button @click="goKnowledgeBase()">前往知识库查看全文</a-button>
        <a-button type="primary" :loading="loading" @click="loadRecommendations({ randomize: true })">
          <template #icon><ReloadOutlined /></template>
          换一批推荐
        </a-button>
      </a-space>
    </div>

    <a-card :bordered="false" class="config-card">
      <a-space wrap>
        <a-input-number
          v-model:value="query.limit"
          :min="1"
          :max="20"
          addon-before="推荐数"
        />
        <a-input-number
          v-model:value="query.history_days"
          :min="1"
          :max="365"
          addon-before="回看天数"
        />
        <a-input-number
          v-model:value="query.topic_count"
          :min="1"
          :max="8"
          addon-before="主题数"
        />
        <a-input-number
          v-model:value="query.k_per_topic"
          :min="1"
          :max="10"
          addon-before="每主题TopK"
        />
      </a-space>
    </a-card>

    <a-row :gutter="[16, 16]" class="metrics">
      <a-col :xs="24" :md="8">
        <div class="metric-card">
          <div class="metric-label">历史问答记录</div>
          <div class="metric-value">{{ profile.history_record_count }}</div>
        </div>
      </a-col>
      <a-col :xs="24" :md="8">
        <div class="metric-card">
          <div class="metric-label">分析时间窗口</div>
          <div class="metric-value">{{ profile.analysis_window_days }} 天</div>
        </div>
      </a-col>
      <a-col :xs="24" :md="8">
        <div class="metric-card">
          <div class="metric-label">识别关注主题</div>
          <div class="metric-value">{{ profile.topic_focus.length }}</div>
        </div>
      </a-col>
    </a-row>

    <a-card :bordered="false" class="topic-card">
      <div class="section-title">你的健康关注主题</div>
      <a-empty
        v-if="!profile.topic_focus.length"
        description="历史问答较少，系统暂时无法识别明显偏好，先展示通用推荐。"
      />
      <div v-else class="topic-list">
        <div v-for="item in profile.topic_focus" :key="item.topic" class="topic-item">
          <a-tag color="processing">{{ item.topic }}</a-tag>
          <span class="topic-score">关注度 {{ item.score }}</span>
          <span class="topic-keywords">{{ item.matched_keywords.join(" / ") }}</span>
        </div>
      </div>
    </a-card>

    <a-card :bordered="false" class="recommend-card">
      <div class="recommend-section-head">
        <div class="section-title">推荐知识</div>
        <a-button
          size="small"
          :loading="loading"
          @click="loadRecommendations({ randomize: true })"
        >
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>
      <a-spin :spinning="loading">
        <a-empty
          v-if="!recommendations.length"
          description="暂无可推荐内容，请先在知识库中新增文档并提问几次。"
        />
        <a-row v-else :gutter="[16, 16]">
          <a-col
            v-for="item in recommendations"
            :key="`${item.document_id}-${item.chunk_id || 'doc'}`"
            :xs="24"
            :md="12"
            :xl="8"
          >
            <div class="recommend-item">
              <div class="item-head">
                <span class="item-topic">{{ getRecommendationTopic(item) }}</span>
                <span v-if="item.score !== null && item.score !== undefined" class="item-score">
                  相关度 {{ formatScore(item.score) }}
                </span>
              </div>
              <div class="item-title">{{ formatRecommendationTitle(item) }}</div>
              <div class="item-reason">{{ formatReason(item.reason) }}</div>
              <div class="item-snippet">{{ formatSnippet(item.snippet) }}</div>
              <div class="item-meta">
                <span>{{ formatUpdatedAt(item.document_updated_at) }}</span>
                <a-button type="link" size="small" @click="openDetail(item)">
                  查看详情
                </a-button>
              </div>
            </div>
          </a-col>
        </a-row>
      </a-spin>
    </a-card>

    <a-drawer
      v-model:visible="detailVisible"
      title="推荐详情"
      width="720"
      placement="right"
    >
      <template v-if="currentRecommendation">
        <a-descriptions bordered :column="1" size="small" class="detail-meta">
          <a-descriptions-item label="文档标题">
            {{ currentRecommendation.document_title }}
          </a-descriptions-item>
          <a-descriptions-item label="推荐主题">
            {{ currentRecommendation.topic }}
          </a-descriptions-item>
          <a-descriptions-item label="推荐原因">
            {{ currentRecommendation.reason }}
          </a-descriptions-item>
          <a-descriptions-item label="来源路径">
            {{ currentRecommendation.source_path || "-" }}
          </a-descriptions-item>
          <a-descriptions-item label="相关度">
            {{ currentRecommendation.score ?? "-" }}
          </a-descriptions-item>
          <a-descriptions-item label="更新时间">
            {{ currentRecommendation.document_updated_at || "-" }}
          </a-descriptions-item>
        </a-descriptions>
        <div class="detail-title">推荐内容片段</div>
        <div class="detail-content">{{ currentRecommendation.snippet }}</div>
        <a-button
          type="primary"
          style="margin-top: 12px"
          @click="goKnowledgeBase(currentRecommendation)"
        >
          去健康知识库查看全文
        </a-button>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { ReloadOutlined } from "@ant-design/icons-vue";
import {
  healthRagApi,
  type HealthRecommendationItem,
  type HealthTopicFocus,
} from "@/api/health_rag";

const router = useRouter();
const loading = ref(false);
const detailVisible = ref(false);
const currentRecommendation = ref<HealthRecommendationItem | null>(null);

const query = reactive({
  limit: 8,
  history_days: 90,
  topic_count: 3,
  k_per_topic: 3,
});

const profile = reactive({
  history_record_count: 0,
  analysis_window_days: 90,
  topic_focus: [] as HealthTopicFocus[],
});

const recommendations = ref<HealthRecommendationItem[]>([]);
const RECOMMEND_REFRESH_EVENT = "health-rag-recommend-refresh";

const extractDocumentTopic = (title?: string) => {
  const text = String(title || "").trim();
  const match = text.match(/^(.+?)\s*\d{1,4}\s*[:：]/);
  return match?.[1]?.trim() || "";
};

const formatRecommendationTitle = (item: HealthRecommendationItem) => {
  const title = String(item.document_title || "").trim();
  return title.replace(/^.+?\s*\d{1,4}\s*[:：]\s*/, "").trim() || title || "健康知识";
};

const getRecommendationTopic = (item: HealthRecommendationItem) => {
  const topic = extractDocumentTopic(item.document_title);
  return topic || item.topic || "健康知识";
};

const formatReason = (value?: string) => {
  const text = String(value || "").trim();
  if (!text) return "根据近期问答内容推荐";
  return text.replace(/^你最近/, "近期").replace(/先推荐/, "推荐");
};

const formatSnippet = (value?: string) => {
  let text = String(value || "").replace(/\s+/g, " ").trim();
  const answerMatch = text.match(/回答\s*[:：]\s*(.+?)(?:关键词\s*[:：]|$)/);
  if (answerMatch?.[1]) {
    text = answerMatch[1].trim();
  }
  text = text
    .replace(/^主题\s*[:：].*?问题\s*[:：]/, "")
    .replace(/关键词\s*[:：].*$/, "")
    .trim();
  return text || "暂无摘要";
};

const formatScore = (value?: number | null) => {
  const score = Number(value || 0);
  if (!Number.isFinite(score) || score <= 0) return "-";
  if (score <= 1) return `${Math.round(score * 100)}%`;
  return String(score);
};

const formatUpdatedAt = (value?: string) => {
  if (!value) return "暂无更新时间";
  return `更新于 ${value.slice(0, 16)}`;
};

const loadRecommendations = async (options?: { randomize?: boolean }) => {
  loading.value = true;
  try {
    const res = await healthRagApi.listRecommendations({
      limit: query.limit,
      history_days: query.history_days,
      topic_count: query.topic_count,
      k_per_topic: query.k_per_topic,
      randomize: Boolean(options?.randomize),
    });
    if (!res.success) {
      message.error(res.message || "加载推荐失败");
      return;
    }
    const data = (res.data || {}) as {
      profile?: {
        history_record_count?: number;
        analysis_window_days?: number;
        topic_focus?: HealthTopicFocus[];
      };
      recommendations?: HealthRecommendationItem[];
    };
    profile.history_record_count = data.profile?.history_record_count || 0;
    profile.analysis_window_days = data.profile?.analysis_window_days || query.history_days;
    profile.topic_focus = data.profile?.topic_focus || [];
    recommendations.value = data.recommendations || [];
  } catch (error: any) {
    message.error(error?.message || "加载推荐失败");
  } finally {
    loading.value = false;
  }
};

const openDetail = (item: HealthRecommendationItem) => {
  currentRecommendation.value = item;
  detailVisible.value = true;
};

const goKnowledgeBase = (item?: HealthRecommendationItem | null) => {
  const routeQuery: Record<string, string> = { menu: "health-rag-kb" };
  if (item?.document_id) {
    routeQuery.document_id = String(item.document_id);
  }
  router.push({
    path: "/dashboard",
    query: routeQuery,
  });
};

const handleRecommendRefresh = () => {
  void loadRecommendations();
};

const handleRecommendStorageRefresh = (event: StorageEvent) => {
  if (event.key === "health_rag_recommend_refresh_at") {
    void loadRecommendations();
  }
};

onMounted(() => {
  loadRecommendations();
  window.addEventListener(RECOMMEND_REFRESH_EVENT, handleRecommendRefresh);
  window.addEventListener("storage", handleRecommendStorageRefresh);
});

onBeforeUnmount(() => {
  window.removeEventListener(RECOMMEND_REFRESH_EVENT, handleRecommendRefresh);
  window.removeEventListener("storage", handleRecommendStorageRefresh);
});
</script>

<style scoped>
.health-recommend-page {
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
}

.hero-content p {
  margin: 8px 0 0;
  color: var(--theme-text-secondary, #6b7280);
}

.config-card {
  margin-bottom: 14px;
}

.metrics {
  margin-bottom: 14px;
}

.metric-card {
  background: var(--theme-card-bg, #ffffff);
  border-radius: 12px;
  padding: 14px 16px;
  border: 1px solid var(--theme-card-border, #e5e7eb);
}

.metric-label {
  color: var(--theme-text-secondary, #6b7280);
  font-size: 13px;
}

.metric-value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--theme-primary, #2563eb);
}

.topic-card {
  margin-bottom: 14px;
}

.recommend-card {
  margin-bottom: 14px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--theme-text-primary, #111827);
}

.recommend-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.topic-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.topic-item {
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--theme-card-bg, #ffffff);
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.topic-score {
  color: var(--theme-primary, #2563eb);
  font-weight: 600;
}

.topic-keywords {
  color: var(--theme-text-secondary, #6b7280);
}

.recommend-item {
  height: 100%;
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-radius: 8px;
  padding: 16px 18px;
  background: var(--theme-card-bg, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.recommend-item:hover {
  border-color: rgba(37, 99, 235, 0.28);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

.item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.item-topic {
  display: inline-flex;
  align-items: center;
  max-width: 58%;
  height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  border: 1px solid rgba(37, 99, 235, 0.18);
  background: rgba(37, 99, 235, 0.06);
  color: var(--theme-primary, #2563eb);
  font-size: 12px;
  line-height: 22px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-score {
  font-size: 12px;
  color: var(--theme-text-secondary, #6b7280);
  white-space: nowrap;
}

.item-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.45;
  color: var(--theme-text-primary, #111827);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.item-reason {
  font-size: 13px;
  color: var(--theme-primary, #2563eb);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.item-snippet {
  line-height: 1.65;
  color: var(--theme-text-primary, #111827);
  font-size: 14px;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.item-meta {
  font-size: 12px;
  color: var(--theme-text-secondary, #6b7280);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding-top: 4px;
  border-top: 1px solid var(--theme-card-border, #e5e7eb);
}

.item-meta :deep(.ant-btn-link) {
  height: auto;
  padding: 0;
}

.detail-meta {
  margin-bottom: 12px;
}

.detail-title {
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--theme-text-primary, #111827);
}

.detail-content {
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-radius: 10px;
  padding: 12px;
  line-height: 1.75;
  white-space: pre-wrap;
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
}

.health-recommend-page :deep(.ant-card) {
  background: var(--theme-content-bg, #ffffff);
  border: 1px solid var(--theme-card-border, #e5e7eb);
}

.health-recommend-page :deep(.ant-input-number),
.health-recommend-page :deep(.ant-input-number-input),
.health-recommend-page :deep(.ant-btn-default) {
  background: var(--theme-card-bg, #ffffff);
  border-color: var(--theme-card-border, #e5e7eb);
  color: var(--theme-text-primary, #111827);
}

.health-recommend-page :deep(.ant-btn-default:hover),
.health-recommend-page :deep(.ant-btn-default:focus) {
  color: var(--theme-primary, #2563eb);
  border-color: var(--theme-primary, #2563eb);
}

.health-recommend-page :deep(.ant-btn-primary) {
  background: var(--theme-primary, #2563eb);
  border-color: var(--theme-primary, #2563eb);
}

.health-recommend-page :deep(.ant-drawer-content),
.health-recommend-page :deep(.ant-drawer-header),
.health-recommend-page :deep(.ant-drawer-body) {
  background: var(--theme-content-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
}

.health-recommend-page :deep(.ant-descriptions-bordered .ant-descriptions-item-label),
.health-recommend-page :deep(.ant-descriptions-bordered .ant-descriptions-item-content) {
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
