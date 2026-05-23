<template>
  <div class="retrieval-debug-page">
    <a-card :bordered="false">
      <a-space direction="vertical" style="width: 100%">
        <a-card size="small" title="RAGAS 评估">
          <a-space wrap>
            <span class="field-label" title="评测集文件名，默认使用 datasets/eval/health_eval_questions_cmedqa_v1.jsonl">评测文件</span>
            <a-input
              v-model:value="ragasForm.input"
              placeholder="评测文件名，如 health_eval_questions_cmedqa_v1.jsonl"
              style="width: min(520px, 90vw)"
            />
            <span class="field-label" title="每题取前 K 条上下文参与评估，建议 5">TopK</span>
            <a-input-number v-model:value="ragasForm.top_k" :min="1" :max="20" />
            <span class="field-label" title="本次评估抽样题数，快速验证用 20，正式跑可用 100">样本数</span>
            <a-input-number v-model:value="ragasForm.limit" :min="1" :max="500" />
            <a-button type="primary" :loading="ragasLoading" @click="runRagasEval">
              启动 RAGAS 评估
            </a-button>
            <a-button :loading="retrievalEvalLoading" @click="runRetrievalEval">
              启动检索评估
            </a-button>
          </a-space>
          <div class="field-tip">
            建议：先用 TopK=5、样本数=20 快速验证；稳定后改为样本数=100 做正式留档。
          </div>
          <div v-if="ragasResult" class="ragas-result">
            <div>耗时：{{ ragasResult.elapsed_ms }}ms</div>
            <div>结果文件：{{ ragasResult.latest_result_file || "-" }}</div>
            <pre class="stdout">{{ ragasResult.stdout || "-" }}</pre>
          </div>
          <div v-if="retrievalEvalResult" class="ragas-result">
            <div>检索评估耗时：{{ retrievalEvalResult.elapsed_ms }}ms</div>
            <div>结果文件：{{ retrievalEvalResult.latest_result_file || "-" }}</div>
            <pre class="stdout">{{ retrievalEvalResult.stdout || "-" }}</pre>
          </div>
        </a-card>

        <a-space wrap>
          <a-input
            v-model:value="form.question"
            placeholder="输入要调试的问题，例如：长期失眠怎么调理？"
            style="width: min(760px, 90vw)"
            @pressEnter="runDebug"
          />
          <span class="field-label" title="调试页展示前 K 条召回结果，建议 5">TopK</span>
          <a-input-number v-model:value="form.top_k" :min="1" :max="20" />
          <a-button type="primary" :loading="loading" @click="runDebug">开始调试</a-button>
        </a-space>

        <a-alert
          v-if="result"
          show-icon
          type="info"
          :message="`改写查询：${result.rewritten_query || '-'} ｜耗时：${result.latency_ms}ms ｜向量维度：${result.query_embedding_dim}`"
        />
        <a-alert v-if="result?.rerank_error" show-icon type="warning" :message="`Rerank 降级：${result.rerank_error}`" />

        <a-row :gutter="[12, 12]">
          <a-col :xs="24" :xl="12">
            <a-card size="small" title="Vector TopK">
              <a-table :columns="hitColumns" :data-source="result?.vector_hits || []" :pagination="false" row-key="chunk_id" size="small" />
            </a-card>
          </a-col>
          <a-col :xs="24" :xl="12">
            <a-card size="small" title="Sparse TopK">
              <a-table :columns="hitColumns" :data-source="result?.sparse_hits || []" :pagination="false" row-key="chunk_id" size="small" />
            </a-card>
          </a-col>
          <a-col :xs="24" :xl="12">
            <a-card size="small" title="RRF TopK">
              <a-table :columns="rrfColumns" :data-source="result?.rrf_hits || []" :pagination="false" row-key="chunk_id" size="small" />
            </a-card>
          </a-col>
          <a-col :xs="24" :xl="12">
            <a-card size="small" title="Rerank / Final TopK">
              <a-table :columns="rerankColumns" :data-source="(result?.rerank_hits?.length ? result?.rerank_hits : result?.final_hits) || []" :pagination="false" row-key="chunk_id" size="small" />
            </a-card>
          </a-col>
        </a-row>

        <a-card size="small" title="最终进入 Prompt 的 Chunks">
          <a-list :data-source="result?.final_contexts || []" size="small">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta :title="`${item.document_title} #${item.chunk_index}`">
                  <template #description>
                    <div class="context-text">{{ item.chunk_text }}</div>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </a-space>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { message } from "ant-design-vue";
import { healthRagApi, type HealthRetrievalDebugHit } from "@/api/health_rag";

const loading = ref(false);
const result = ref<any>(null);
const ragasLoading = ref(false);
const ragasResult = ref<any>(null);
const retrievalEvalLoading = ref(false);
const retrievalEvalResult = ref<any>(null);
const form = reactive({
  question: "",
  top_k: 5,
});
const ragasForm = reactive({
  input: "health_eval_questions_cmedqa_v1.jsonl",
  top_k: 5,
  limit: 20,
});

const hitColumns = [
  { title: "文档", dataIndex: "document_title", key: "document_title", ellipsis: true },
  { title: "chunk", dataIndex: "chunk_index", key: "chunk_index", width: 72 },
  {
    title: "score",
    dataIndex: "score",
    key: "score",
    width: 90,
    customRender: ({ text }: { text: number }) => (Number.isFinite(text) ? Number(text).toFixed(4) : "-"),
  },
];

const rrfColumns = [
  { title: "文档", dataIndex: "document_title", key: "document_title", ellipsis: true },
  { title: "chunk", dataIndex: "chunk_index", key: "chunk_index", width: 72 },
  {
    title: "rrf",
    dataIndex: "rrf_score",
    key: "rrf_score",
    width: 90,
    customRender: ({ text }: { text: number }) => (Number.isFinite(text) ? Number(text).toFixed(4) : "-"),
  },
];

const rerankColumns = [
  { title: "文档", dataIndex: "document_title", key: "document_title", ellipsis: true },
  { title: "chunk", dataIndex: "chunk_index", key: "chunk_index", width: 72 },
  {
    title: "rerank",
    dataIndex: "rerank_score",
    key: "rerank_score",
    width: 100,
    customRender: ({ text, record }: { text: number; record: HealthRetrievalDebugHit }) => {
      const score = Number.isFinite(text) ? text : record.rrf_score;
      return Number.isFinite(score) ? Number(score).toFixed(4) : "-";
    },
  },
];

const runDebug = async () => {
  if (!form.question.trim()) {
    message.warning("请先输入问题");
    return;
  }
  loading.value = true;
  try {
    const res = await healthRagApi.retrievalDebug({
      question: form.question.trim(),
      top_k: Number(form.top_k) || 5,
    });
    if (!res.success) {
      message.error(res.message || "调试失败");
      return;
    }
    result.value = res.data;
    message.success("检索调试完成");
  } catch (error: any) {
    message.error(error?.message || "调试失败");
  } finally {
    loading.value = false;
  }
};

const runRagasEval = async () => {
  ragasLoading.value = true;
  try {
    const res = await healthRagApi.runRagasEval({
      input: ragasForm.input?.trim() || "health_eval_questions_cmedqa_v1.jsonl",
      top_k: Number(ragasForm.top_k) || 5,
      limit: Number(ragasForm.limit) || 20,
    });
    if (!res.success) {
      message.error(res.message || "RAGAS 评估失败");
      return;
    }
    ragasResult.value = res.data;
    message.success("RAGAS 评估完成");
  } catch (error: any) {
    message.error(error?.message || "RAGAS 评估失败");
  } finally {
    ragasLoading.value = false;
  }
};

const runRetrievalEval = async () => {
  retrievalEvalLoading.value = true;
  try {
    const res = await healthRagApi.runRetrievalEval({
      input: ragasForm.input?.trim() || "health_eval_questions_cmedqa_v1.jsonl",
      top_k: Number(ragasForm.top_k) || 5,
      limit: Number(ragasForm.limit) || 20,
    });
    if (!res.success) {
      message.error(res.message || "检索评估失败");
      return;
    }
    retrievalEvalResult.value = res.data;
    message.success("检索评估完成");
  } catch (error: any) {
    message.error(error?.message || "检索评估失败");
  } finally {
    retrievalEvalLoading.value = false;
  }
};
</script>

<style scoped>
.retrieval-debug-page {
  min-height: 100%;
}

.context-text {
  white-space: pre-wrap;
  line-height: 1.6;
  color: #243247;
}

.ragas-result {
  margin-top: 12px;
}

.field-label {
  color: #4b5b70;
  font-size: 13px;
}

.field-tip {
  margin-top: 8px;
  color: #5f6f85;
  font-size: 12px;
}

.stdout {
  margin-top: 8px;
  max-height: 180px;
  overflow: auto;
  background: #f7f9fc;
  padding: 8px;
  white-space: pre-wrap;
  line-height: 1.5;
  border-radius: 4px;
}
</style>
