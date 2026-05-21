<template>
  <div class="health-rag-page">
    <div class="page-hero">
      <div class="hero-content">
        <h1>身体健康智慧问答助手</h1>
        <p>基于本地模型与知识检索的毕业设计联调工作台</p>
      </div>
      <div class="hero-actions">
        <a-button :loading="modelLoading" @click="refreshModelStatus">
          <template #icon><ReloadOutlined /></template>
          检查模型状态
        </a-button>
      </div>
    </div>

    <a-row :gutter="[16, 16]" class="top-metrics">
      <a-col :xs="24" :md="8">
        <div class="metric-card">
          <div class="metric-label">知识文档数</div>
          <div class="metric-value">{{ documentPagination.total }}</div>
        </div>
      </a-col>
      <a-col :xs="24" :md="8">
        <div class="metric-card">
          <div class="metric-label">会话数</div>
          <div class="metric-value">{{ sessionPagination.total }}</div>
        </div>
      </a-col>
      <a-col :xs="24" :md="8">
        <div class="metric-card">
          <div class="metric-label">历史记录数</div>
          <div class="metric-value">{{ historyPagination.total }}</div>
        </div>
      </a-col>
    </a-row>

    <a-tabs v-model:activeKey="activeTab" class="main-tabs">
      <a-tab-pane key="chat" tab="健康问答">
        <a-card :bordered="false">
          <div class="section-toolbar">
            <a-space wrap>
              <a-select
                v-model:value="chatForm.session_id"
                style="width: 280px"
                placeholder="选择会话（可不选，自动创建）"
                allow-clear
              >
                <a-select-option
                  v-for="item in sessionOptions"
                  :key="item.id"
                  :value="item.id"
                >
                  {{ item.title }}
                </a-select-option>
              </a-select>
              <a-input-number
                v-model:value="chatForm.k"
                :min="1"
                :max="10"
                addon-before="TopK"
              />
              <a-button @click="openCreateSessionModal">
                <template #icon><PlusOutlined /></template>
                新建会话
              </a-button>
              <a-button danger :disabled="!chatForm.session_id" @click="deleteCurrentSession">
                <template #icon><DeleteOutlined /></template>
                删除会话
              </a-button>
            </a-space>
          </div>

          <a-textarea
            v-model:value="chatForm.question"
            :rows="4"
            placeholder="请输入健康问题，例如：失眠应该怎么调理？"
            class="chat-input"
            @keydown.enter.exact.prevent="submitQuestion"
          />

          <div class="voice-panel">
            <a-space wrap class="voice-toolbar">
              <a-button
                type="default"
                :disabled="!isRecordingSupported || isRequestingMicrophone || isMicrophoneBlocked || isRecording || isTranscribing || asking"
                @click="startRecording"
              >
                <template #icon><AudioOutlined /></template>
                {{ isRequestingMicrophone ? "请求麦克风..." : "开始录音" }}
              </a-button>
              <a-button
                danger
                :disabled="!isRecording"
                @click="stopRecording"
              >
                <template #icon><PauseCircleOutlined /></template>
                停止录音
              </a-button>
              <a-button
                :disabled="isRecording || (!recordedBlob && !lastTranscript)"
                @click="resetRecording"
              >
                重新录音
              </a-button>
              <a-button
                type="primary"
                class="voice-transcribe-btn"
                :loading="isTranscribing"
                :disabled="!recordedBlob || isRecording"
                @click="transcribeRecordedAudio"
              >
                <template #icon><SoundOutlined /></template>
                转写并回填
              </a-button>
              <a-space size="small">
                <span>自动播报</span>
                <a-switch v-model:checked="autoSpeak" :disabled="!isSynthesisSupported" />
              </a-space>
            </a-space>
            <div
              class="voice-status"
              :class="{ recording: isRecording, transcribing: isTranscribing, unsupported: !isRecordingSupported }"
            >
              <template v-if="!isRecordingSupported">
                当前浏览器不支持录音，请使用 Chromium / Edge 浏览器。
              </template>
              <template v-else-if="isMicrophoneBlocked">
                {{ microphoneBlockedMessage }}
              </template>
              <template v-else-if="isRequestingMicrophone">
                正在请求麦克风权限，请在浏览器权限弹窗中选择允许。
              </template>
              <template v-else-if="isRecording">
                正在录音 {{ formatRecordSeconds(recordSeconds) }}，请说出你的健康问题。
              </template>
              <template v-else-if="isTranscribing">
                正在将录音转换为文本，请稍候...
              </template>
              <template v-else-if="lastTranscript">
                最近识别结果：{{ lastTranscript }}
              </template>
              <template v-else-if="recordedBlob">
                录音已完成（{{ recordMimeType || "unknown" }}），可点击“转写并回填”。
              </template>
              <template v-else>
                点击“开始录音”即可语音提问，转写后会自动回填到问题输入框。
              </template>
            </div>
          </div>

          <a-space class="chat-actions">
            <a-button type="primary" :loading="asking" @click="submitQuestion">
              <template #icon><SendOutlined /></template>
              提交问答
            </a-button>
          </a-space>

          <div ref="conversationPanelRef" class="conversation-panel">
            <div v-if="chatLoadingHistory" class="conversation-loading">
              <a-spin />
            </div>
            <template v-else-if="chatMessages.length">
              <div
                v-for="msg in chatMessages"
                :key="msg.key"
                class="chat-message"
                :class="msg.role"
              >
                <div class="message-meta">
                  <span v-if="msg.role === 'assistant'">AI助手</span>
                  <a-tag v-if="msg.role === 'user' && msg.ask_mode === 'voice'" color="blue">
                    {{ getAskModeLabel(msg.ask_mode) }}
                  </a-tag>
                  <span>{{ msg.created_at || "-" }}</span>
                  <span v-if="msg.role === 'assistant' && msg.latency_ms">耗时 {{ msg.latency_ms }} ms</span>
                  <a-button
                    v-if="msg.role === 'assistant' && isSynthesisSupported"
                    type="link"
                    size="small"
                    class="message-speak-btn"
                    @click="toggleSpeakMessage(msg)"
                  >
                    {{ isSpeaking && speakingMessageKey === msg.key ? "停止播放" : "播放回答" }}
                  </a-button>
                </div>
                <div
                  v-if="msg.role === 'assistant'"
                  class="message-content formatted-answer"
                  v-html="formatAnswerHtml(msg.content)"
                ></div>
                <div v-else class="message-content">{{ msg.content }}</div>
                <div
                  v-if="msg.role === 'assistant' && msg.sources && msg.sources.length"
                  class="message-sources"
                >
                  <div class="sources-title">引用来源：</div>
                  <div v-if="hasLowConfidenceSources(msg.sources)" class="sources-warning">
                    当前知识库未检索到高度相关资料，以下来源仅供参考。
                  </div>
                  <div v-for="(src, idx) in msg.sources" :key="`${msg.key}-${idx}`" class="source-item">
                    {{ formatSourceReference(src) }}
                  </div>
                </div>
                <div
                  v-if="msg.role === 'assistant' && msg.knowledge_card && (msg.knowledge_card.title || (msg.knowledge_card.core_points && msg.knowledge_card.core_points.length))"
                  class="knowledge-card"
                >
                  <div class="knowledge-card-header">
                    <div class="knowledge-card-title">
                      {{ msg.knowledge_card.title || "知识卡片" }}
                    </div>
                    <a-button size="small" type="link" @click="copyKnowledgeCard(msg.knowledge_card)">
                      复制卡片
                    </a-button>
                  </div>

                  <div v-if="msg.knowledge_card.generated_at" class="knowledge-card-meta">
                    生成时间：{{ msg.knowledge_card.generated_at }}
                  </div>

                  <div v-if="msg.knowledge_card.core_points && msg.knowledge_card.core_points.length" class="knowledge-card-section">
                    <div class="knowledge-card-section-title">核心要点</div>
                    <ul class="knowledge-card-list">
                      <li v-for="(item, idx) in msg.knowledge_card.core_points" :key="`kp-${msg.key}-${idx}`">
                        {{ item }}
                      </li>
                    </ul>
                  </div>

                  <div v-if="msg.knowledge_card.cautions && msg.knowledge_card.cautions.length" class="knowledge-card-section">
                    <div class="knowledge-card-section-title">注意事项</div>
                    <ul class="knowledge-card-list caution">
                      <li v-for="(item, idx) in msg.knowledge_card.cautions" :key="`ct-${msg.key}-${idx}`">
                        {{ item }}
                      </li>
                    </ul>
                  </div>

                  <div
                    v-if="msg.knowledge_card.references && msg.knowledge_card.references.length"
                    class="knowledge-card-section"
                  >
                    <div class="knowledge-card-section-title">参考来源</div>
                    <ul class="knowledge-card-list references">
                      <li v-for="(item, idx) in msg.knowledge_card.references" :key="`ref-${msg.key}-${idx}`">
                        {{ item }}
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </template>
            <a-empty v-else description="暂无会话消息，发送第一条问题开始对话" />
          </div>

          <div v-if="chatMessages.length" class="conversation-composer">
            <a-textarea
              v-model:value="chatForm.question"
              :auto-size="{ minRows: 1, maxRows: 4 }"
              :disabled="asking"
              placeholder="继续输入问题，按 Enter 发送，Shift + Enter 换行"
              class="conversation-composer-input"
              @keydown.enter.exact.prevent="submitQuestion"
            />
            <a-button
              type="primary"
              :loading="asking"
              :disabled="!canSubmitQuestion"
              class="conversation-composer-send"
              @click="submitQuestion"
            >
              <template #icon><SendOutlined /></template>
              发送
            </a-button>
          </div>
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="history" tab="问答历史">
        <a-card :bordered="false">
          <div class="section-toolbar">
            <a-space wrap>
              <a-input
                v-model:value="historyQuery.keyword"
                placeholder="关键词（问题/回答）"
                style="width: 220px"
              />
              <a-select
                v-model:value="historyQuery.session_id"
                style="width: 240px"
                placeholder="按会话筛选"
                allow-clear
              >
                <a-select-option
                  v-for="item in sessionOptions"
                  :key="item.id"
                  :value="item.id"
                >
                  {{ item.title }}
                </a-select-option>
              </a-select>
              <a-range-picker
                v-model:value="historyDateRange"
                show-time
                format="YYYY-MM-DD HH:mm:ss"
              />
              <a-button type="primary" @click="loadHistory">查询</a-button>
              <a-button @click="resetHistoryFilters">重置</a-button>
              <a-button
                danger
                :disabled="selectedHistoryRowKeys.length === 0"
                @click="deleteHistorySession"
              >
                删除历史会话
              </a-button>
              <a-button
                :loading="historyExporting"
                :disabled="selectedHistoryRowKeys.length === 0"
                @click="exportSelectedHistoryPdf"
              >
                <template #icon><DownloadOutlined /></template>
                导出PDF（已选 {{ selectedHistoryRowKeys.length }}）
              </a-button>
            </a-space>
          </div>

          <a-table
            :loading="historyLoading"
            :columns="historyColumns"
            :data-source="historyList"
            row-key="id"
            :row-selection="{
              type: 'radio',
              selectedRowKeys: selectedHistoryRowKeys,
              onChange: onHistorySelectionChange,
            }"
            :pagination="{
              current: historyPagination.page,
              pageSize: historyPagination.page_size,
              total: historyPagination.total,
              showSizeChanger: true,
            }"
            @change="handleHistoryTableChange"
          />
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="model" tab="模型状态">
        <a-card :bordered="false">
          <a-space direction="vertical" style="width: 100%">
            <div class="model-config-form">
              <a-row :gutter="[12, 12]">
                <a-col :xs="24" :md="10">
                  <a-input
                    v-model:value="customModelConfig.base_url"
                    placeholder="BASE_URL，例如：https://api.deepseek.com"
                  />
                </a-col>
                <a-col :xs="24" :md="8">
                  <a-input-password
                    v-model:value="customModelConfig.api_key"
                    placeholder="API_KEY（可选）"
                  />
                </a-col>
                <a-col :xs="24" :md="6">
                  <a-input
                    v-model:value="customModelConfig.model"
                    placeholder="MODEL，例如：deepseek-chat"
                  />
                </a-col>
              </a-row>
              <a-space class="model-config-actions">
                <a-button type="primary" :loading="modelLoading" @click="refreshModelStatusWithCustom">
                  使用自定义参数检测
                </a-button>
                <a-button @click="resetCustomModelConfig">清空参数</a-button>
              </a-space>
            </div>

            <a-alert
              v-if="!isKbAdmin"
              show-icon
              type="warning"
              message="当前账号不是管理员，仅可查看模型状态，不可执行版本切换或重启。"
            />

            <div class="model-operation-form">
              <a-row :gutter="[12, 12]">
                <a-col :xs="24" :md="12">
                  <a-select
                    v-model:value="modelOperation.targetModel"
                    style="width: 100%"
                    placeholder="选择要切换的模型"
                    allow-clear
                    :disabled="!isKbAdmin"
                  >
                    <a-select-option
                      v-for="name in modelInstalledModelOptions"
                      :key="name"
                      :value="name"
                    >
                      {{ name }}
                    </a-select-option>
                  </a-select>
                </a-col>
                <a-col :xs="24" :md="12">
                  <a-space wrap>
                    <a-button
                      type="primary"
                      :loading="modelSwitching"
                      :disabled="!isKbAdmin"
                      @click="switchModelVersion"
                    >
                      切换模型版本
                    </a-button>
                    <a-button
                      :loading="modelRestarting"
                      :disabled="!isKbAdmin"
                      @click="restartCurrentModel"
                    >
                      重启当前模型
                    </a-button>
                  </a-space>
                </a-col>
              </a-row>
            </div>

            <a-alert
              show-icon
              :type="modelInfo?.available ? 'success' : 'warning'"
              :message="modelInfo?.message || '尚未检测模型状态'"
            />
            <a-alert
              v-if="modelOperation.lastActionMessage"
              show-icon
              type="info"
              :message="modelOperation.lastActionMessage"
            />
            <a-descriptions bordered :column="1" size="small">
              <a-descriptions-item label="模型名称">
                {{ modelInfo?.model_name || "-" }}
              </a-descriptions-item>
              <a-descriptions-item label="服务地址">
                {{ modelInfo?.base_url || "-" }}
              </a-descriptions-item>
              <a-descriptions-item label="模型提供方">
                {{ modelInfo?.provider || "-" }}
              </a-descriptions-item>
              <a-descriptions-item label="API_KEY已配置">
                {{ modelInfo?.api_key_configured ? "是" : "否" }}
              </a-descriptions-item>
              <a-descriptions-item label="是否可用">
                {{ modelInfo?.available ? "是" : "否" }}
              </a-descriptions-item>
              <a-descriptions-item label="已安装模型">
                {{ (modelInfo?.installed_models || []).join(", ") || "-" }}
              </a-descriptions-item>
              <a-descriptions-item label="运行时生效模型">
                {{ modelInfo?.runtime_config?.model_name || "-" }}
              </a-descriptions-item>
              <a-descriptions-item label="运行时生效地址">
                {{ modelInfo?.runtime_config?.base_url || "-" }}
              </a-descriptions-item>
              <a-descriptions-item label="运行时更新时间">
                {{ modelInfo?.runtime_config?.updated_at || "-" }}
              </a-descriptions-item>
              <a-descriptions-item label="检索引擎">
                {{
                  modelInfo?.retrieval?.langchain_faiss_available
                    ? "LangChain + FAISS"
                    : "SimpleEmbedder（回退）"
                }}
              </a-descriptions-item>
              <a-descriptions-item label="FAISS 索引目录">
                {{ modelInfo?.retrieval?.index_dir || "-" }}
              </a-descriptions-item>
              <a-descriptions-item label="FAISS 索引状态">
                {{ modelInfo?.retrieval?.index_exists ? "存在" : "不存在" }}
              </a-descriptions-item>
            </a-descriptions>
          </a-space>
        </a-card>
      </a-tab-pane>
    </a-tabs>

    <a-modal
      v-model:visible="createDocumentModalVisible"
      title="新增知识文档"
      :confirm-loading="createDocumentSubmitting"
      @ok="submitCreateDocument"
      @cancel="closeCreateDocumentModal"
      ok-text="提交"
      cancel-text="取消"
      width="680px"
    >
      <a-form layout="vertical">
        <a-form-item label="文档标题" required>
          <a-input v-model:value="createDocumentForm.title" />
        </a-form-item>
        <a-form-item label="来源类型">
          <a-radio-group v-model:value="createDocumentForm.source_type">
            <a-radio value="manual">手动输入</a-radio>
            <a-radio value="url">URL文本</a-radio>
            <a-radio value="file">文件上传</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="来源路径/URL（可选）">
          <a-input v-model:value="createDocumentForm.source_path" />
        </a-form-item>
        <a-form-item v-if="createDocumentForm.source_type !== 'file'" label="文档内容" required>
          <a-textarea v-model:value="createDocumentForm.content" :rows="6" />
        </a-form-item>
        <a-form-item v-else label="上传文件（txt/md）" required>
          <input type="file" class="file-input" @change="onCreateDocumentFileChange" />
          <div class="file-tip">
            当前文件：{{ createDocumentFile ? createDocumentFile.name : "未选择" }}
          </div>
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="chunk_size">
              <a-input-number
                v-model:value="createDocumentForm.chunk_size"
                :min="100"
                :max="2000"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="chunk_overlap">
              <a-input-number
                v-model:value="createDocumentForm.chunk_overlap"
                :min="0"
                :max="300"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <a-modal
      v-model:visible="editDocumentModalVisible"
      title="编辑知识文档"
      :confirm-loading="editDocumentSubmitting"
      @ok="submitEditDocument"
      @cancel="closeEditDocumentModal"
      ok-text="保存"
      cancel-text="取消"
      width="680px"
    >
      <a-form layout="vertical">
        <a-form-item label="文档标题" required>
          <a-input v-model:value="editDocumentForm.title" />
        </a-form-item>
        <a-form-item label="来源路径/URL（可选）">
          <a-input v-model:value="editDocumentForm.source_path" />
        </a-form-item>
        <a-form-item label="文档内容（可选）">
          <a-textarea
            v-model:value="editDocumentForm.content"
            :rows="6"
            placeholder="默认已加载当前内容，可直接修改后保存。"
          />
        </a-form-item>
        <a-form-item label="更新后重建索引">
          <a-switch v-model:checked="editDocumentForm.reindex" />
        </a-form-item>
        <a-row v-if="editDocumentForm.reindex" :gutter="12">
          <a-col :span="12">
            <a-form-item label="chunk_size">
              <a-input-number
                v-model:value="editDocumentForm.chunk_size"
                :min="100"
                :max="2000"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="chunk_overlap">
              <a-input-number
                v-model:value="editDocumentForm.chunk_overlap"
                :min="0"
                :max="300"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <a-modal
      v-model:visible="createSessionModalVisible"
      title="新建问答会话"
      :confirm-loading="createSessionSubmitting"
      @ok="submitCreateSession"
      ok-text="创建"
      cancel-text="取消"
      width="480px"
    >
      <a-form layout="vertical">
        <a-form-item label="会话标题">
          <a-input v-model:value="createSessionTitle" placeholder="例如：失眠调理咨询" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { message, Modal } from "ant-design-vue";
import dayjs from "dayjs";
import {
  AudioOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PauseCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
  SoundOutlined,
} from "@ant-design/icons-vue";
import {
  healthRagApi,
  type HealthAskMode,
  type HealthHistoryItem,
  type HealthHistorySessionItem,
  type HealthKnowledgeCard,
  type HealthKnowledgeDocument,
  type HealthSessionItem,
  type HealthSourceRef,
} from "@/api/health_rag";
import { useUserStore } from "@/stores/hertz_user";

const activeTab = ref("chat");
const userStore = useUserStore();
const KB_ADMIN_ROLES = ["admin", "system_admin", "super_admin"];
const isKbAdmin = computed(() => {
  const roles = userStore.userInfo?.roles || [];
  return roles.some((role) => KB_ADMIN_ROLES.includes(role.role_code));
});

const sessionOptions = ref<HealthSessionItem[]>([]);
const sessionPagination = reactive({ total: 0, page: 1, page_size: 50 });

const chatForm = reactive({
  question: "",
  session_id: undefined as number | undefined,
  k: 5,
});
const asking = ref(false);
const canSubmitQuestion = computed(() => Boolean((chatForm.question || "").trim()) && !asking.value);
const pendingAskMode = ref<HealthAskMode>("text");
const isRecording = ref(false);
const isRequestingMicrophone = ref(false);
const isMicrophoneBlocked = ref(false);
const microphoneBlockedMessage = ref("");
const isTranscribing = ref(false);
const mediaRecorder = ref<MediaRecorder | null>(null);
const mediaStream = ref<MediaStream | null>(null);
const audioChunks = ref<Blob[]>([]);
const recordedBlob = ref<Blob | null>(null);
const recordMimeType = ref("");
const lastTranscript = ref("");
const autoSpeak = ref(false);
const recordSeconds = ref(0);
const speakingMessageKey = ref("");
const isSpeaking = ref(false);
const isSynthesisSupported = ref(false);
const isStoppingSpeech = ref(false);
const discardRecordingOnStop = ref(false);
const transcriptionRequestSeq = ref(0);
const isRecordingSupported = computed(() => {
  if (typeof window === "undefined") return false;
  return Boolean(window.MediaRecorder && navigator.mediaDevices?.getUserMedia);
});

let recordTimer: number | null = null;
let speechSynthesisRef: SpeechSynthesis | null = null;
let currentUtterance: SpeechSynthesisUtterance | null = null;

interface ChatMessageItem {
  key: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  ask_mode?: HealthAskMode | string;
  latency_ms?: number;
  sources?: HealthSourceRef[];
  knowledge_card?: HealthKnowledgeCard | null;
}

const chatMessages = ref<ChatMessageItem[]>([]);
const chatLoadingHistory = ref(false);
const conversationPanelRef = ref<HTMLElement | null>(null);
const sessionMessageCache = reactive<Record<number, ChatMessageItem[]>>({});
const RECOMMEND_REFRESH_EVENT = "health-rag-recommend-refresh";

const documentQuery = reactive({ query: "" });
const documentLoading = ref(false);
const documentList = ref<HealthKnowledgeDocument[]>([]);
const documentPagination = reactive({ total: 0, page: 1, page_size: 10 });
const selectedDocumentIds = ref<number[]>([]);
const reindexing = ref(false);

const historyLoading = ref(false);
const historyList = ref<Array<HealthHistorySessionItem & { display_index?: number }>>([]);
const historyPagination = reactive({ total: 0, page: 1, page_size: 10 });
const historyQuery = reactive({
  keyword: "",
  session_id: undefined as number | undefined,
});
const historyDateRange = ref<any[]>([]);
const selectedHistoryRowKeys = ref<number[]>([]);
const historyExporting = ref(false);

const modelLoading = ref(false);
const modelSwitching = ref(false);
const modelRestarting = ref(false);
const modelInfo = ref<any>(null);
const customModelConfig = reactive({
  base_url: "",
  api_key: "",
  model: "",
});
const modelOperation = reactive({
  targetModel: "",
  lastActionMessage: "",
});

const createDocumentModalVisible = ref(false);
const createDocumentSubmitting = ref(false);
const createDocumentForm = reactive({
  title: "",
  source_type: "manual" as "manual" | "url" | "file",
  source_path: "",
  content: "",
  chunk_size: 500,
  chunk_overlap: 80,
});
const createDocumentFile = ref<File | null>(null);

const editDocumentModalVisible = ref(false);
const editDocumentSubmitting = ref(false);
const editDocumentOriginalContent = ref("");
const editDocumentForm = reactive({
  document_id: 0,
  title: "",
  source_path: "",
  content: "",
  reindex: false,
  chunk_size: 500,
  chunk_overlap: 80,
});

const createSessionModalVisible = ref(false);
const createSessionSubmitting = ref(false);
const createSessionTitle = ref("");

const documentColumns = [
  { title: "ID", dataIndex: "id", key: "id", width: 80 },
  { title: "标题", dataIndex: "title", key: "title" },
  { title: "来源类型", dataIndex: "source_type", key: "source_type", width: 120 },
  { title: "状态", dataIndex: "status", key: "status", width: 100 },
  { title: "切片数", dataIndex: "chunk_count", key: "chunk_count", width: 100 },
  { title: "更新时间", dataIndex: "updated_at", key: "updated_at", width: 180 },
  { title: "操作", key: "action", width: 100 },
];

const historyColumns = [
  { title: "序号", dataIndex: "display_index", key: "display_index", width: 80 },
  {
    title: "对话",
    dataIndex: "title",
    key: "title",
    ellipsis: true,
    customRender: ({ record }: { record: HealthHistorySessionItem }) =>
      h("a", {
        class: "history-session-link",
        title: record.title || "",
        onClick: () => {
          void openHistoryConversation(record);
        },
      }, record.title || "未命名对话"),
  },
  {
    title: "最近问题",
    dataIndex: "latest_question",
    key: "latest_question",
    ellipsis: true,
    customRender: ({ record }: { record: HealthHistorySessionItem }) =>
      h("span", { title: record.latest_question || "" }, record.latest_question || "-"),
  },
  { title: "轮数", dataIndex: "record_count", key: "record_count", width: 90 },
  {
    title: "操作",
    key: "action",
    width: 110,
    customRender: ({ record }: { record: HealthHistorySessionItem }) =>
      h("a", {
        class: "history-session-link",
        onClick: () => {
          void openHistoryConversation(record);
        },
      }, "打开对话"),
  },
  { title: "更新时间", dataIndex: "updated_at", key: "updated_at", width: 180 },
];

const documentReindexPayload = computed(() => {
  if (selectedDocumentIds.value.length > 0) {
    return {
      document_ids: selectedDocumentIds.value,
      chunk_size: createDocumentForm.chunk_size,
      chunk_overlap: createDocumentForm.chunk_overlap,
    };
  }
  return {
    chunk_size: createDocumentForm.chunk_size,
    chunk_overlap: createDocumentForm.chunk_overlap,
  };
});

const modelInstalledModelOptions = computed<string[]>(() => {
  const list = Array.isArray(modelInfo.value?.installed_models) ? modelInfo.value.installed_models : [];
  return list.filter((item: any) => typeof item === "string" && item.trim()).map((item: string) => item.trim());
});

const escapeHtml = (value: string) =>
  String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const formatAnswerHtml = (value: string) => {
  const cleaned = String(value || "")
    .replace(/<\/?think>/gi, "")
    .replace(/```(?:json|markdown|md)?/gi, "")
    .replace(/```/g, "")
    .replace(/\*{2,}/g, "")
    .replace(/['"]?point['"]?\s*[:：]\s*/gi, "")
    .trim();

  if (!cleaned) return "<p>暂无有效回答。</p>";

  return cleaned
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const lines = block.split(/\n/).map((line) => line.trim()).filter(Boolean);
      const allList = lines.length > 1 && lines.every((line) => /^(\d+[.、)]|[-*])\s*/.test(line));
      if (allList) {
        const items = lines
          .map((line) => line.replace(/^(\d+[.、)]|[-*])\s*/, ""))
          .map((line) => `<li>${escapeHtml(line)}</li>`)
          .join("");
        return `<ol>${items}</ol>`;
      }
      return `<p>${escapeHtml(lines.join(" "))}</p>`;
    })
    .join("");
};

const getSourceRelevanceLabel = (src: HealthSourceRef) => {
  if (src.relevance_label) return src.relevance_label;
  const score = Number(src.score || 0);
  if (score >= 0.7) return "高相关";
  if (score >= 0.3) return "较相关";
  return "弱相关";
};

const formatSourceScore = (score?: number) => {
  const value = Number(score || 0);
  if (!Number.isFinite(value)) return "0.0000";
  return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, ".0");
};

const formatSourceReference = (src: HealthSourceRef) => {
  const chunkNo = Number(src.chunk_index || 0) + 1;
  return `${src.document_title} 片段 ${chunkNo}（score: ${formatSourceScore(src.score)} / ${getSourceRelevanceLabel(src)}）`;
};

const hasLowConfidenceSources = (sources?: HealthSourceRef[]) => {
  if (!Array.isArray(sources) || !sources.length) return false;
  if (sources.some((src) => src.low_confidence)) return true;
  const hasBackendFlag = sources.some((src) => Object.prototype.hasOwnProperty.call(src, "low_confidence"));
  if (hasBackendFlag) return false;
  return Math.max(...sources.map((src) => Number(src.score || 0))) < 0.3;
};

const loadSessions = async () => {
  const res = await healthRagApi.listSessions({
    page: sessionPagination.page,
    page_size: sessionPagination.page_size,
  });
  if (res.success) {
    sessionOptions.value = res.data.list || [];
    sessionPagination.total = res.data.total || 0;
  } else {
    message.error(res.message || "加载会话失败");
  }
};

const loadDocuments = async () => {
  documentLoading.value = true;
  try {
    const res = await healthRagApi.listDocuments({
      query: documentQuery.query,
      page: documentPagination.page,
      page_size: documentPagination.page_size,
    });
    if (res.success) {
      documentList.value = res.data.list || [];
      documentPagination.total = res.data.total || 0;
    } else {
      message.error(res.message || "加载文档失败");
    }
  } catch (error: any) {
    message.error(error?.message || "加载文档失败");
  } finally {
    documentLoading.value = false;
  }
};

const loadHistory = async () => {
  historyLoading.value = true;
  try {
    const params: any = {
      keyword: historyQuery.keyword || undefined,
      session_id: historyQuery.session_id || undefined,
      page: historyPagination.page,
      page_size: historyPagination.page_size,
    };
    if (historyDateRange.value?.length === 2) {
      params.start_time = historyDateRange.value[0].format("YYYY-MM-DD HH:mm:ss");
      params.end_time = historyDateRange.value[1].format("YYYY-MM-DD HH:mm:ss");
    }
    const res = await healthRagApi.listHistorySessions(params);
    if (res.success) {
      historyPagination.total = res.data.total || 0;
      const page = Number(historyPagination.page || 1);
      const pageSize = Number(historyPagination.page_size || 10);
      historyList.value = (res.data.list || []).map((item, index) => ({
        ...item,
        display_index: (page - 1) * pageSize + index + 1,
      }));
      selectedHistoryRowKeys.value = [];
    } else {
      message.error(res.message || "加载历史失败");
    }
  } catch (error: any) {
    message.error(error?.message || "加载历史失败");
  } finally {
    historyLoading.value = false;
  }
};

const buildConversationFromRecords = (records: HealthHistoryItem[]): ChatMessageItem[] => {
  const ordered = [...records].sort((a, b) => {
    const ta = dayjs(a.created_at).valueOf();
    const tb = dayjs(b.created_at).valueOf();
    return ta - tb;
  });

  const messages: ChatMessageItem[] = [];
  ordered.forEach((record) => {
    const recordTime = record.created_at || dayjs().format("YYYY-MM-DD HH:mm:ss");
    messages.push({
      key: `u-${record.id}`,
      role: "user",
      content: record.question || "",
      created_at: recordTime,
      ask_mode: (record.ask_mode as HealthAskMode) || "text",
    });
    messages.push({
      key: `a-${record.id}`,
      role: "assistant",
      content: record.answer || "",
      created_at: recordTime,
      latency_ms: Number(record.latency_ms || 0),
      sources: Array.isArray(record.source_refs) ? record.source_refs : [],
      knowledge_card: (record as any)?.knowledge_card || null,
    });
  });
  return messages;
};

const formatKnowledgeCardText = (card: HealthKnowledgeCard): string => {
  const title = (card?.title || "知识卡片").trim();
  const corePoints = Array.isArray(card?.core_points) ? card.core_points : [];
  const cautions = Array.isArray(card?.cautions) ? card.cautions : [];
  const refs = Array.isArray(card?.references) ? card.references : [];
  const lines: string[] = [];
  lines.push(`【${title}】`);
  if (corePoints.length) {
    lines.push("核心要点：");
    corePoints.forEach((item, idx) => lines.push(`${idx + 1}. ${String(item).trim()}`));
  }
  if (cautions.length) {
    lines.push("");
    lines.push("注意事项：");
    cautions.forEach((item) => lines.push(`- ${String(item).trim()}`));
  }
  if (refs.length) {
    lines.push("");
    lines.push("参考来源：");
    refs.forEach((item) => lines.push(`- ${String(item).trim()}`));
  }
  if (card?.generated_at) {
    lines.push("");
    lines.push(`生成时间：${String(card.generated_at)}`);
  }
  return lines.join("\n").trim();
};

const copyKnowledgeCard = async (card: HealthKnowledgeCard) => {
  const text = formatKnowledgeCardText(card);
  if (!text) return;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      message.success("知识卡片已复制，可直接粘贴分享");
      return;
    }
  } catch {
    // ignore and fallback below
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.top = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    message.success("知识卡片已复制，可直接粘贴分享");
  } catch (error: any) {
    message.error(error?.message || "复制失败，请手动选择复制");
  }
};

const getAskModeLabel = (askMode?: string) => (askMode === "voice" ? "语音提问" : "文本提问");

const stopRecordTimer = () => {
  if (recordTimer !== null) {
    window.clearInterval(recordTimer);
    recordTimer = null;
  }
};

const stopMediaStreamTracks = () => {
  if (!mediaStream.value) return;
  mediaStream.value.getTracks().forEach((track) => track.stop());
  mediaStream.value = null;
};

const resetVoiceDraft = () => {
  audioChunks.value = [];
  recordedBlob.value = null;
  recordMimeType.value = "";
  lastTranscript.value = "";
  recordSeconds.value = 0;
};

const formatRecordSeconds = (seconds: number) => {
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
};

const getPreferredRecorderMimeType = () => {
  if (typeof window === "undefined" || typeof window.MediaRecorder === "undefined") {
    return "";
  }
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  return candidates.find((item) => MediaRecorder.isTypeSupported(item)) || "";
};

const getMicrophonePermissionMessage = (error: any) => {
  const errorName = String(error?.name || "");
  const errorMessage = String(error?.message || "");
  const normalized = `${errorName} ${errorMessage}`.toLowerCase();

  if (
    errorName === "NotAllowedError" ||
    errorName === "SecurityError" ||
    normalized.includes("permission denied") ||
    normalized.includes("denied by system")
  ) {
    return "麦克风权限被系统拒绝。请在浏览器地址栏权限设置和系统设置中允许麦克风访问，然后刷新页面再录音。";
  }

  if (errorName === "NotFoundError" || normalized.includes("requested device not found")) {
    return "未检测到可用麦克风，请确认麦克风已连接并可被系统识别。";
  }

  if (errorName === "NotReadableError" || normalized.includes("could not start")) {
    return "麦克风当前被其他程序占用，请关闭占用麦克风的软件后再试。";
  }

  if (normalized.includes("only secure origins") || normalized.includes("secure context")) {
    return "浏览器要求在 localhost 或 HTTPS 页面中使用录音功能，请通过系统启动脚本打开本地页面。";
  }

  return "无法获取麦克风权限，请检查浏览器和系统麦克风设置后重试。";
};

const startRecording = async () => {
  if (!isRecordingSupported.value) {
    message.warning("当前浏览器不支持录音功能");
    return;
  }
  if (isRecording.value || isRequestingMicrophone.value || isMicrophoneBlocked.value) {
    return;
  }

  stopSpeaking(true);
  resetVoiceDraft();
  pendingAskMode.value = "text";
  isRequestingMicrophone.value = true;
  discardRecordingOnStop.value = false;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    isMicrophoneBlocked.value = false;
    microphoneBlockedMessage.value = "";
    const mimeType = getPreferredRecorderMimeType();
    const recorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream);

    mediaStream.value = stream;
    mediaRecorder.value = recorder;
    audioChunks.value = [];
    recordMimeType.value = recorder.mimeType || mimeType || "audio/webm";

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        audioChunks.value.push(event.data);
      }
    };
    recorder.onerror = () => {
      message.error("录音过程中发生异常，请重试");
      isRecording.value = false;
      stopRecordTimer();
      stopMediaStreamTracks();
      mediaRecorder.value = null;
    };
    recorder.onstop = () => {
      isRecording.value = false;
      stopRecordTimer();
      const blob = new Blob(audioChunks.value, {
        type: recorder.mimeType || recordMimeType.value || "audio/webm",
      });
      if (discardRecordingOnStop.value) {
        discardRecordingOnStop.value = false;
        resetVoiceDraft();
      } else if (blob.size > 0) {
        recordedBlob.value = blob;
        message.success("录音完成，可点击“转写并回填”");
      } else {
        message.warning("未采集到有效语音，请重试");
      }
      stopMediaStreamTracks();
      mediaRecorder.value = null;
    };

    recorder.start(250);
    isRecording.value = true;
    recordSeconds.value = 0;
    recordTimer = window.setInterval(() => {
      recordSeconds.value += 1;
    }, 1000);
  } catch (error: any) {
    stopRecordTimer();
    stopMediaStreamTracks();
    mediaRecorder.value = null;
    isRecording.value = false;
    const permissionMessage = getMicrophonePermissionMessage(error);
    isMicrophoneBlocked.value = true;
    microphoneBlockedMessage.value = permissionMessage;
    message.error({
      key: "health-rag-microphone-permission",
      content: permissionMessage,
      duration: 6,
    });
  } finally {
    isRequestingMicrophone.value = false;
  }
};

const stopRecording = () => {
  const recorder = mediaRecorder.value;
  if (!recorder || recorder.state === "inactive") {
    return;
  }
  recorder.stop();
};

const resetRecording = () => {
  if (isRecording.value) {
    discardRecordingOnStop.value = true;
    stopRecording();
  }
  stopRecordTimer();
  stopMediaStreamTracks();
  mediaRecorder.value = null;
  resetVoiceDraft();
  pendingAskMode.value = "text";
};

const mixToMonoChannelData = (audioBuffer: AudioBuffer) => {
  if (audioBuffer.numberOfChannels === 1) {
    return audioBuffer.getChannelData(0);
  }
  const length = audioBuffer.length;
  const mono = new Float32Array(length);
  for (let channel = 0; channel < audioBuffer.numberOfChannels; channel += 1) {
    const channelData = audioBuffer.getChannelData(channel);
    for (let index = 0; index < length; index += 1) {
      mono[index] += channelData[index] / audioBuffer.numberOfChannels;
    }
  }
  return mono;
};

const encodeWavBuffer = (samples: Float32Array, sampleRate: number) => {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  }
  return buffer;
};

const convertRecordedBlobToWav = async (blob: Blob) => {
  if (blob.type === "audio/wav") {
    return blob;
  }

  const AudioContextCtor =
    window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioContextCtor) {
    throw new Error("当前浏览器不支持音频解码，无法完成转写");
  }

  const sourceContext = new AudioContextCtor();
  try {
    const arrayBuffer = await blob.arrayBuffer();
    const decodedBuffer = await sourceContext.decodeAudioData(arrayBuffer.slice(0));
    const monoData = mixToMonoChannelData(decodedBuffer);
    const monoBuffer = sourceContext.createBuffer(
      1,
      monoData.length,
      decodedBuffer.sampleRate,
    );
    monoBuffer.copyToChannel(monoData, 0);

    const targetRate = 16000;
    const targetLength = Math.ceil(monoBuffer.duration * targetRate);
    const offlineContext = new OfflineAudioContext(1, targetLength, targetRate);
    const source = offlineContext.createBufferSource();
    source.buffer = monoBuffer;
    source.connect(offlineContext.destination);
    source.start(0);
    const renderedBuffer = await offlineContext.startRendering();
    const wavBuffer = encodeWavBuffer(renderedBuffer.getChannelData(0), targetRate);
    return new Blob([wavBuffer], { type: "audio/wav" });
  } catch (error: any) {
    if (blob.type === "audio/wav") {
      return blob;
    }
    throw new Error(error?.message || "录音格式转换失败");
  } finally {
    await sourceContext.close();
  }
};

const transcribeRecordedAudio = async () => {
  if (isRecording.value) {
    message.warning("请先停止录音");
    return;
  }
  if (!recordedBlob.value) {
    message.warning("请先完成录音");
    return;
  }

  isTranscribing.value = true;
  const requestSeq = ++transcriptionRequestSeq.value;
  try {
    const wavBlob = await convertRecordedBlobToWav(recordedBlob.value);
    const wavFile = new File([wavBlob], `health-question-${Date.now()}.wav`, {
      type: "audio/wav",
    });
    const formData = new FormData();
    formData.append("file", wavFile);
    formData.append("language", "zh-CN");
    formData.append("format", "wav");
    formData.append("rate", "16000");

    const res = await healthRagApi.transcribeAudio(formData);
    if (!res.success) {
      if (requestSeq !== transcriptionRequestSeq.value) return;
      message.error(res.message || "语音转写失败");
      return;
    }

    const transcript = (res.data?.transcript || "").trim();
    if (requestSeq !== transcriptionRequestSeq.value) return;
    if (!transcript) {
      message.warning("未识别到有效语音内容，请重新录音");
      return;
    }

    lastTranscript.value = transcript;
    chatForm.question = transcript;
    pendingAskMode.value = "voice";
    message.success("语音转写成功，已回填到输入框");
  } catch (error: any) {
    if (requestSeq !== transcriptionRequestSeq.value) return;
    message.error(
      error?.response?.data?.message ||
        error?.response?.data?.error ||
        error?.message ||
        "语音转写失败"
    );
  } finally {
    isTranscribing.value = false;
  }
};

const initSpeechSynthesis = () => {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    isSynthesisSupported.value = false;
    return;
  }

  speechSynthesisRef = window.speechSynthesis;
  isSynthesisSupported.value = true;
  const loadVoices = () => {
    speechSynthesisRef?.getVoices();
  };
  speechSynthesisRef.onvoiceschanged = loadVoices;
  loadVoices();
  window.setTimeout(loadVoices, 100);
};

const stopSpeaking = (silent = false) => {
  if (!speechSynthesisRef) return;
  isStoppingSpeech.value = true;
  try {
    speechSynthesisRef.cancel();
  } catch {
    // ignore
  }
  currentUtterance = null;
  isSpeaking.value = false;
  speakingMessageKey.value = "";
  if (!silent) {
    message.info("语音播报已停止");
  }
  window.setTimeout(() => {
    isStoppingSpeech.value = false;
  }, 300);
};

const pickChineseVoice = () => {
  const voices = speechSynthesisRef?.getVoices() || [];
  return (
    voices.find((voice) => /zh|Chinese/i.test(`${voice.lang} ${voice.name}`)) ||
    voices[0] ||
    null
  );
};

const speakText = async (text: string, messageKey = "") => {
  const normalizedText = text.trim();
  if (!normalizedText) {
    message.warning("暂无可播报内容");
    return;
  }
  if (!speechSynthesisRef || !isSynthesisSupported.value) {
    message.warning("当前浏览器不支持语音播报");
    return;
  }

  stopSpeaking(true);
  const utterance = new SpeechSynthesisUtterance(normalizedText);
  utterance.lang = "zh-CN";
  utterance.rate = 1;
  utterance.pitch = 1;
  utterance.volume = 1;

  const voice = pickChineseVoice();
  if (voice) {
    utterance.voice = voice;
  }

  utterance.onstart = () => {
    isStoppingSpeech.value = false;
    isSpeaking.value = true;
    speakingMessageKey.value = messageKey;
  };
  utterance.onend = () => {
    isStoppingSpeech.value = false;
    isSpeaking.value = false;
    speakingMessageKey.value = "";
    currentUtterance = null;
  };
  utterance.onerror = (event: SpeechSynthesisErrorEvent | Event) => {
    const speechError = String((event as SpeechSynthesisErrorEvent)?.error || "").toLowerCase();
    if (
      isStoppingSpeech.value ||
      speechError === "canceled" ||
      speechError === "interrupted"
    ) {
      isStoppingSpeech.value = false;
      isSpeaking.value = false;
      speakingMessageKey.value = "";
      currentUtterance = null;
      return;
    }
    isStoppingSpeech.value = false;
    isSpeaking.value = false;
    speakingMessageKey.value = "";
    currentUtterance = null;
    message.error("语音播报失败，请刷新页面后重试");
  };

  currentUtterance = utterance;
  await new Promise((resolve) => window.setTimeout(resolve, 50));
  speechSynthesisRef.speak(utterance);
};

const toggleSpeakMessage = async (msg: ChatMessageItem) => {
  if (isSpeaking.value && speakingMessageKey.value === msg.key) {
    stopSpeaking();
    return;
  }
  await speakText(msg.content || "", msg.key);
};

const scrollConversationToBottom = async () => {
  await nextTick();
  const panel = conversationPanelRef.value;
  if (!panel) return;
  panel.scrollTop = panel.scrollHeight;
};

const loadChatConversation = async (sessionId?: number, force = false) => {
  if (!sessionId) {
    chatMessages.value = [];
    return;
  }

  const cache = sessionMessageCache[sessionId];
  if (!force && cache) {
    chatMessages.value = [...cache];
    await scrollConversationToBottom();
    return;
  }

  chatLoadingHistory.value = true;
  try {
    const res = await healthRagApi.listHistory({
      session_id: sessionId,
      page: 1,
      page_size: 200,
    });
    if (!res.success) {
      message.error(res.message || "会话历史加载失败");
      return;
    }

    const conversation = buildConversationFromRecords(res.data.list || []);
    sessionMessageCache[sessionId] = conversation;
    chatMessages.value = [...conversation];
    await scrollConversationToBottom();
  } catch (error: any) {
    message.error(error?.message || "会话历史加载失败");
  } finally {
    chatLoadingHistory.value = false;
  }
};

const openHistoryConversation = async (record: Partial<HealthHistoryItem> | Partial<HealthHistorySessionItem>) => {
  const sessionId = Number((record as any).session_id || record.id || 0);
  if (!sessionId) {
    message.warning("该历史记录缺少有效会话");
    return;
  }

  activeTab.value = "chat";
  if (chatForm.session_id !== sessionId) {
    chatForm.session_id = sessionId;
  }
  await loadChatConversation(sessionId, true);
};

const notifyRecommendationRefresh = () => {
  try {
    localStorage.setItem("health_rag_recommend_refresh_at", String(Date.now()));
  } catch {
    // ignore storage failures
  }
  window.dispatchEvent(new Event(RECOMMEND_REFRESH_EVENT));
};

const refreshModelStatus = async () => {
  modelLoading.value = true;
  try {
    const res = await healthRagApi.modelStatus();
    if (res.success) {
      modelInfo.value = res.data;
      modelOperation.targetModel = modelInfo.value?.model_name || modelOperation.targetModel || "";
    } else {
      message.error(res.message || "模型状态获取失败");
    }
  } catch (error: any) {
    message.error(error?.message || "模型状态获取失败");
  } finally {
    modelLoading.value = false;
  }
};

const refreshModelStatusWithCustom = async () => {
  const payload: Record<string, string> = {};
  if (customModelConfig.base_url.trim()) payload.BASE_URL = customModelConfig.base_url.trim();
  if (customModelConfig.api_key.trim()) payload.API_KEY = customModelConfig.api_key.trim();
  if (customModelConfig.model.trim()) payload.MODEL = customModelConfig.model.trim();

  if (Object.keys(payload).length === 0) {
    message.warning("请至少填写一个参数：BASE_URL / API_KEY / MODEL");
    return;
  }

  modelLoading.value = true;
  try {
    const res = await healthRagApi.modelStatusCustom(payload);
    if (res.success) {
      modelInfo.value = res.data;
      modelOperation.targetModel = modelInfo.value?.model_name || modelOperation.targetModel || "";
      message.success("自定义模型状态检测完成");
    } else {
      message.error(res.message || "自定义模型状态获取失败");
    }
  } catch (error: any) {
    message.error(error?.message || "自定义模型状态获取失败");
  } finally {
    modelLoading.value = false;
  }
};

const resetCustomModelConfig = () => {
  customModelConfig.base_url = "";
  customModelConfig.api_key = "";
  customModelConfig.model = "";
};

const switchModelVersion = async () => {
  if (!isKbAdmin.value) {
    message.warning("仅管理员可切换模型");
    return;
  }

  const targetModel = (modelOperation.targetModel || customModelConfig.model || modelInfo.value?.model_name || "").trim();
  if (!targetModel) {
    message.warning("请选择或输入目标模型");
    return;
  }

  const payload: Record<string, any> = { MODEL: targetModel };
  if (customModelConfig.base_url.trim()) payload.BASE_URL = customModelConfig.base_url.trim();
  if (customModelConfig.api_key.trim()) payload.API_KEY = customModelConfig.api_key.trim();

  modelSwitching.value = true;
  try {
    const res = await healthRagApi.switchModel(payload);
    if (!res.success) {
      message.error(res.message || "模型切换失败");
      return;
    }
    modelOperation.lastActionMessage = res.message || res.data?.message || "模型切换完成";
    if (res.data?.status) {
      modelInfo.value = res.data.status;
      modelOperation.targetModel = modelInfo.value?.model_name || targetModel;
    } else {
      await refreshModelStatus();
    }
    message.success("模型切换成功");
  } catch (error: any) {
    message.error(error?.message || "模型切换失败");
  } finally {
    modelSwitching.value = false;
  }
};

const restartCurrentModel = async () => {
  if (!isKbAdmin.value) {
    message.warning("仅管理员可重启模型");
    return;
  }

  const selectedModel = (modelOperation.targetModel || customModelConfig.model || modelInfo.value?.model_name || "").trim();
  const payload: Record<string, any> = {};
  if (selectedModel) payload.MODEL = selectedModel;
  if (customModelConfig.base_url.trim()) payload.BASE_URL = customModelConfig.base_url.trim();
  if (customModelConfig.api_key.trim()) payload.API_KEY = customModelConfig.api_key.trim();
  payload.warmup = true;

  modelRestarting.value = true;
  try {
    const res = await healthRagApi.restartModel(payload);
    if (!res.success) {
      message.error(res.message || "模型重启失败");
      return;
    }
    modelOperation.lastActionMessage = res.message || res.data?.message || "模型重启完成";
    if (res.data?.status) {
      modelInfo.value = res.data.status;
      modelOperation.targetModel = modelInfo.value?.model_name || selectedModel;
    } else {
      await refreshModelStatus();
    }
    message.success("模型重启成功");
  } catch (error: any) {
    message.error(error?.message || "模型重启失败");
  } finally {
    modelRestarting.value = false;
  }
};

const submitQuestion = async () => {
  const question = (chatForm.question || "").trim();
  if (!question) {
    message.warning("请输入问题");
    return;
  }
  const askMode = pendingAskMode.value;
  asking.value = true;
  try {
    const askPayload: {
      question: string;
      session_id?: number;
      k?: number;
      base_url?: string;
      api_key?: string;
      model?: string;
      ask_mode?: HealthAskMode;
    } = {
      question,
      session_id: chatForm.session_id,
      k: chatForm.k,
      ask_mode: askMode,
    };
    if (customModelConfig.base_url.trim()) askPayload.base_url = customModelConfig.base_url.trim();
    if (customModelConfig.api_key.trim()) askPayload.api_key = customModelConfig.api_key.trim();
    if (customModelConfig.model.trim()) askPayload.model = customModelConfig.model.trim();

    const res = await healthRagApi.ask(askPayload);
    if (!res.success) {
      message.error(res.message || "问答失败");
      return;
    }
    // 提交成功后清空输入框，便于用户直接进行下一次独立提问。
    chatForm.question = "";
    pendingAskMode.value = "text";

    const resolvedSessionId = Number(res.data.session_id || chatForm.session_id || 0);
    if (resolvedSessionId > 0 && !chatForm.session_id) {
      chatForm.session_id = resolvedSessionId;
    }

    const nowText = dayjs().format("YYYY-MM-DD HH:mm:ss");
    const cached = sessionMessageCache[resolvedSessionId] || [];
    const assistantMessage: ChatMessageItem = {
      key: `a-temp-${Date.now()}`,
      role: "assistant",
      content: res.data.answer || "",
      created_at: nowText,
      latency_ms: Number(res.data.latency_ms || 0),
      sources: Array.isArray(res.data.sources) ? res.data.sources : [],
      knowledge_card: (res.data as any)?.knowledge_card || null,
    };
    const nextMessages: ChatMessageItem[] = [
      ...cached,
      {
        key: `u-temp-${Date.now()}`,
        role: "user",
        content: question,
        created_at: nowText,
        ask_mode: (res.data.ask_mode as HealthAskMode) || askMode,
      },
      assistantMessage,
    ];
    sessionMessageCache[resolvedSessionId] = nextMessages;
    chatMessages.value = [...nextMessages];
    await scrollConversationToBottom();

    if (autoSpeak.value) {
      await speakText(assistantMessage.content, assistantMessage.key);
    }

    notifyRecommendationRefresh();
    await Promise.all([loadSessions(), loadHistory()]);
    message.success("问答完成");
  } catch (error: any) {
    message.error(error?.response?.data?.message || error?.message || "问答失败");
  } finally {
    asking.value = false;
  }
};

const openCreateDocumentModal = () => {
  if (!isKbAdmin.value) {
    message.warning("仅管理员可新增文档");
    return;
  }
  resetCreateDocumentForm();
  createDocumentModalVisible.value = true;
};

const closeCreateDocumentModal = () => {
  createDocumentModalVisible.value = false;
  resetCreateDocumentForm();
};

const resetCreateDocumentForm = () => {
  createDocumentForm.title = "";
  createDocumentForm.source_type = "manual";
  createDocumentForm.source_path = "";
  createDocumentForm.content = "";
  createDocumentForm.chunk_size = 500;
  createDocumentForm.chunk_overlap = 80;
  createDocumentFile.value = null;
};

const onCreateDocumentFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  createDocumentFile.value = file || null;
};

const submitCreateDocument = async () => {
  if (!isKbAdmin.value) {
    message.warning("仅管理员可新增文档");
    return;
  }

  if (!createDocumentForm.title.trim()) {
    message.warning("请输入文档标题");
    return;
  }

  if (createDocumentForm.source_type !== "file" && !createDocumentForm.content.trim()) {
    message.warning("请输入文档内容");
    return;
  }

  if (createDocumentForm.source_type === "file" && !createDocumentFile.value) {
    message.warning("请上传文件");
    return;
  }

  createDocumentSubmitting.value = true;
  try {
    let res: any;
    if (createDocumentForm.source_type === "file" && createDocumentFile.value) {
      const formData = new FormData();
      formData.append("title", createDocumentForm.title.trim());
      formData.append("source_type", "file");
      formData.append("source_path", createDocumentForm.source_path.trim());
      formData.append("chunk_size", String(createDocumentForm.chunk_size));
      formData.append("chunk_overlap", String(createDocumentForm.chunk_overlap));
      formData.append("file", createDocumentFile.value);
      res = await healthRagApi.createDocumentFile(formData);
    } else {
      res = await healthRagApi.createDocumentJson({
        title: createDocumentForm.title.trim(),
        source_type: createDocumentForm.source_type,
        source_path: createDocumentForm.source_path.trim(),
        content: createDocumentForm.content,
        chunk_size: createDocumentForm.chunk_size,
        chunk_overlap: createDocumentForm.chunk_overlap,
      });
    }

    if (res.success) {
      const createdChunkCount = Number(res.data?.created_chunk_count || 0);
      message.success(`文档创建成功（切片 ${createdChunkCount}）`);
      closeCreateDocumentModal();
      selectedDocumentIds.value = [];
      await loadDocuments();
    } else {
      message.error(res.message || "文档创建失败");
    }
  } catch (error: any) {
    message.error(error?.response?.data?.message || error?.message || "文档创建失败");
  } finally {
    createDocumentSubmitting.value = false;
  }
};

const openEditDocumentModal = (doc: HealthKnowledgeDocument) => {
  if (!isKbAdmin.value) {
    message.warning("仅管理员可编辑文档");
    return;
  }

  editDocumentForm.document_id = doc.id;
  editDocumentForm.title = doc.title || "";
  editDocumentForm.source_path = doc.source_path || "";
  editDocumentForm.content = doc.content || "";
  editDocumentOriginalContent.value = doc.content || "";
  editDocumentForm.reindex = false;
  editDocumentForm.chunk_size = createDocumentForm.chunk_size;
  editDocumentForm.chunk_overlap = createDocumentForm.chunk_overlap;
  editDocumentModalVisible.value = true;
};

const closeEditDocumentModal = () => {
  editDocumentModalVisible.value = false;
  editDocumentForm.document_id = 0;
  editDocumentForm.title = "";
  editDocumentForm.source_path = "";
  editDocumentForm.content = "";
  editDocumentOriginalContent.value = "";
  editDocumentForm.reindex = false;
  editDocumentForm.chunk_size = 500;
  editDocumentForm.chunk_overlap = 80;
};

const submitEditDocument = async () => {
  if (!isKbAdmin.value) {
    message.warning("仅管理员可编辑文档");
    return;
  }
  if (!editDocumentForm.document_id) {
    message.warning("缺少文档ID");
    return;
  }

  const title = editDocumentForm.title.trim();
  if (!title) {
    message.warning("请输入文档标题");
    return;
  }

  if (
    editDocumentForm.reindex &&
    Number(editDocumentForm.chunk_overlap) >= Number(editDocumentForm.chunk_size)
  ) {
    message.warning("chunk_overlap 必须小于 chunk_size");
    return;
  }

  editDocumentSubmitting.value = true;
  try {
    const payload: {
      document_id: number;
      title: string;
      source_path: string;
      content?: string;
      reindex: boolean;
      chunk_size?: number;
      chunk_overlap?: number;
    } = {
      document_id: editDocumentForm.document_id,
      title,
      source_path: editDocumentForm.source_path.trim(),
      reindex: Boolean(editDocumentForm.reindex),
    };

    const content = editDocumentForm.content.trim();
    const originalContent = editDocumentOriginalContent.value.trim();
    if (content && content !== originalContent) {
      payload.content = content;
      payload.reindex = true;
    }

    if (payload.reindex) {
      payload.chunk_size = Number(editDocumentForm.chunk_size);
      payload.chunk_overlap = Number(editDocumentForm.chunk_overlap);
    }

    const res = await healthRagApi.updateDocument(payload);
    if (!res.success) {
      message.error(res.message || "文档更新失败");
      return;
    }

    const updatedChunkCount = Number(res.data?.updated_chunk_count || 0);
    if (payload.reindex) {
      message.success(`文档更新成功（重建切片 ${updatedChunkCount}）`);
    } else {
      message.success("文档更新成功");
    }
    closeEditDocumentModal();
    await loadDocuments();
  } catch (error: any) {
    message.error(error?.response?.data?.message || error?.message || "文档更新失败");
  } finally {
    editDocumentSubmitting.value = false;
  }
};

const onDocumentSelectionChange = (keys: any[]) => {
  selectedDocumentIds.value = (keys || []).map((item) => Number(item)).filter((n) => Number.isFinite(n));
};

const deleteSelectedDocuments = () => {
  if (!isKbAdmin.value) {
    message.warning("仅管理员可删除文档");
    return;
  }
  if (selectedDocumentIds.value.length === 0) return;
  Modal.confirm({
    title: "确认删除",
    content: `确认删除选中的 ${selectedDocumentIds.value.length} 条文档吗？`,
    okText: "删除",
    cancelText: "取消",
    onOk: async () => {
      try {
        const res = await healthRagApi.deleteDocuments(selectedDocumentIds.value);
        if (res.success) {
        message.success("删除成功");
        selectedDocumentIds.value = [];
        await loadDocuments();
        } else {
          message.error(res.message || "删除失败");
        }
      } catch (error: any) {
        message.error(error?.response?.data?.message || error?.message || "删除失败");
      }
    },
  });
};

const reindexDocuments = async () => {
  if (!isKbAdmin.value) {
    message.warning("仅管理员可重建索引");
    return;
  }
  reindexing.value = true;
  try {
    const res = await healthRagApi.reindex(documentReindexPayload.value);
    if (res.success) {
      const docCount = Number(res.data?.document_count || 0);
      const chunkCount = Number(res.data?.chunk_count || 0);
      if (docCount === 0) {
        message.warning(res.message || "没有可重建索引的文档，请先新增知识文档");
      } else {
        message.success(`重建完成：${docCount} 个文档，${chunkCount} 个切片`);
      }
      await loadDocuments();
    } else {
      message.error(res.message || "重建失败");
    }
  } catch (error: any) {
    message.error(error?.response?.data?.message || error?.message || "重建失败");
  } finally {
    reindexing.value = false;
  }
};

const handleDocumentTableChange = (pagination: any) => {
  documentPagination.page = pagination?.current || 1;
  documentPagination.page_size = pagination?.pageSize || 10;
  loadDocuments();
};

const handleHistoryTableChange = (pagination: any) => {
  historyPagination.page = pagination?.current || 1;
  historyPagination.page_size = pagination?.pageSize || 10;
  loadHistory();
};

const resetHistoryFilters = async () => {
  historyQuery.keyword = "";
  historyQuery.session_id = undefined;
  historyDateRange.value = [];
  historyPagination.page = 1;
  selectedHistoryRowKeys.value = [];
  await loadHistory();
};

const onHistorySelectionChange = (keys: Array<string | number>) => {
  selectedHistoryRowKeys.value = (keys || [])
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item) && item > 0);
};

const exportSelectedHistoryPdf = async () => {
  if (selectedHistoryRowKeys.value.length === 0) {
    message.warning("请先勾选要导出的对话");
    return;
  }

  historyExporting.value = true;
  try {
    const blob = await healthRagApi.exportHistoryPdf({
      session_id: selectedHistoryRowKeys.value[0],
    });

    if (!blob || !(blob instanceof Blob)) {
      message.error("导出失败：后端未返回有效文件");
      return;
    }

    // 兼容后端错误响应（JSON），避免把错误文本当PDF下载
    if (blob.type.includes("application/json") || blob.type.includes("text/plain")) {
      const text = await blob.text();
      try {
        const parsed = JSON.parse(text);
        message.error(parsed?.message || "导出失败");
      } catch {
        message.error(text || "导出失败");
      }
      return;
    }

    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `health-qa-history-${dayjs().format("YYYYMMDD-HHmmss")}.pdf`;
    link.click();
    window.URL.revokeObjectURL(url);
    message.success("对话PDF导出成功");
  } catch (error: any) {
    const respData = error?.response?.data;
    if (respData instanceof Blob) {
      try {
        const text = await respData.text();
        const parsed = JSON.parse(text);
        message.error(parsed?.message || "问答记录PDF导出失败");
        return;
      } catch {
        // ignore parse error and fallback below
      }
    }
    message.error(error?.message || "问答记录PDF导出失败");
  } finally {
    historyExporting.value = false;
  }
};

const openCreateSessionModal = () => {
  createSessionTitle.value = "";
  createSessionModalVisible.value = true;
};

const submitCreateSession = async () => {
  createSessionSubmitting.value = true;
  try {
    const title = createSessionTitle.value.trim();
    const res = await healthRagApi.createSession({ title });
    if (res.success) {
      message.success("会话创建成功");
      createSessionModalVisible.value = false;
      await loadSessions();
      chatForm.session_id = res.data.session_id;
      sessionMessageCache[res.data.session_id] = [];
      chatMessages.value = [];
    } else {
      message.error(res.message || "会话创建失败");
    }
  } catch (error: any) {
    message.error(error?.message || "会话创建失败");
  } finally {
    createSessionSubmitting.value = false;
  }
};

const confirmDeleteSession = (sessionId: number, fallbackTitle = "") => {
  const target = sessionOptions.value.find((item) => item.id === sessionId);
  const historyTarget = historyList.value.find((item) => item.id === sessionId);
  const title = target?.title || historyTarget?.title || fallbackTitle || `会话 ${sessionId}`;
  Modal.confirm({
    title: "确认删除会话",
    content: `删除会话“${title}”后，关联问答记录也会一起删除，是否继续？`,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    onOk: async () => {
      try {
        const res = await healthRagApi.deleteSessions([sessionId]);
        if (!res.success) {
          message.error(res.message || "会话删除失败");
          return;
        }

        if (chatForm.session_id === sessionId) {
          chatForm.session_id = undefined;
          chatMessages.value = [];
        }
        delete sessionMessageCache[sessionId];
        if (historyQuery.session_id === sessionId) {
          historyQuery.session_id = undefined;
        }
        selectedHistoryRowKeys.value = selectedHistoryRowKeys.value.filter((id) => id !== sessionId);

        await Promise.all([loadSessions(), loadHistory()]);
        message.success("会话删除成功");
      } catch (error: any) {
        message.error(error?.response?.data?.message || error?.message || "会话删除失败");
      }
    },
  });
};

const deleteCurrentSession = () => {
  const sessionId = chatForm.session_id;
  if (!sessionId) {
    message.warning("请先选择会话");
    return;
  }
  confirmDeleteSession(sessionId);
};

const deleteHistorySession = () => {
  const sessionId = selectedHistoryRowKeys.value[0];
  if (!sessionId) {
    message.warning("请先在历史列表中选择要删除的会话");
    return;
  }
  confirmDeleteSession(sessionId);
};

watch(
  () => chatForm.session_id,
  (sessionId) => {
    void loadChatConversation(sessionId);
  },
);

onMounted(async () => {
  initSpeechSynthesis();
  const bootTasks: Array<Promise<any>> = [
    loadSessions(),
    loadHistory(),
    refreshModelStatus(),
    loadDocuments(),
  ];
  await Promise.all(bootTasks);

  // 默认设置近 7 天范围，便于首次演示
  if (!historyDateRange.value.length) {
    historyDateRange.value = [dayjs().subtract(7, "day"), dayjs()];
  }
});

onBeforeUnmount(() => {
  stopRecordTimer();
  if (mediaRecorder.value && mediaRecorder.value.state !== "inactive") {
    mediaRecorder.value.stop();
  }
  stopMediaStreamTracks();
  mediaRecorder.value = null;
  stopSpeaking(true);
});
</script>

<style scoped>
.health-rag-page {
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

.top-metrics {
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
  font-size: 26px;
  font-weight: 700;
  color: var(--theme-primary, #2563eb);
}

.main-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 10px;
}

.main-tabs :deep(.ant-tabs-nav::before) {
  border-bottom: 1px solid var(--theme-card-border, #e5e7eb);
}

.main-tabs :deep(.ant-tabs-tab) {
  color: var(--theme-text-secondary, #6b7280);
}

.main-tabs :deep(.ant-tabs-tab.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: var(--theme-primary, #2563eb);
}

.main-tabs :deep(.ant-tabs-ink-bar) {
  background: var(--theme-primary, #2563eb);
}

.section-toolbar {
  width: 100%;
  margin-bottom: 16px;
}

.section-toolbar :deep(.ant-space) {
  display: flex;
  width: 100%;
  row-gap: 10px;
}

.readonly-alert {
  margin-bottom: 12px;
}

.readonly-text {
  color: var(--theme-text-secondary, #6b7280);
}

.chat-input {
  margin-top: 2px;
  margin-bottom: 12px;
}

.chat-actions {
  margin-bottom: 14px;
}

.voice-panel {
  margin-top: 12px;
  margin-bottom: 14px;
  border: 1px dashed var(--theme-card-border, #e5e7eb);
  border-radius: 12px;
  padding: 12px;
  background: color-mix(in srgb, var(--theme-primary, #2563eb) 3%, var(--theme-card-bg, #ffffff));
}

.voice-toolbar {
  width: 100%;
}

.voice-status {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--theme-text-secondary, #6b7280);
}

.voice-status.recording {
  color: #dc2626;
  font-weight: 600;
}

.voice-status.transcribing {
  color: var(--theme-primary, #2563eb);
  font-weight: 600;
}

.voice-status.unsupported {
  color: #ef4444;
}

.voice-transcribe-btn {
  background: var(--theme-primary, #2563eb) !important;
  border-color: var(--theme-primary, #2563eb) !important;
  color: #ffffff !important;
}

.health-rag-page :deep(.voice-transcribe-btn) {
  background: var(--theme-primary, #2563eb) !important;
  border-color: var(--theme-primary, #2563eb) !important;
  color: #ffffff !important;
}

.health-rag-page :deep(.voice-transcribe-btn span) {
  color: #ffffff !important;
}

.conversation-panel {
  border: 1px solid var(--theme-card-border, #e5e7eb);
  background: var(--theme-content-bg, #ffffff);
  border-radius: 12px;
  padding: 14px;
  min-height: 180px;
  max-height: 560px;
  overflow-y: auto;
}

.conversation-composer {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin-top: 12px;
  padding: 10px;
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-radius: 12px;
  background: color-mix(in srgb, var(--theme-card-bg, #ffffff) 92%, var(--theme-primary, #2563eb));
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}

.conversation-composer-input {
  flex: 1;
}

.conversation-composer-input :deep(textarea) {
  resize: none;
}

.conversation-composer-send {
  min-width: 96px;
  height: 40px;
}

.conversation-loading {
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chat-message {
  margin-bottom: 14px;
  max-width: 86%;
}

.chat-message.user {
  margin-left: auto;
  width: fit-content;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.chat-message.assistant {
  margin-right: auto;
}

.message-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  color: var(--theme-text-secondary, #6b7280);
  font-size: 12px;
}

.chat-message.user .message-meta {
  justify-content: flex-end;
  margin-bottom: 8px;
}

.message-speak-btn {
  padding-inline: 0;
}

.message-content {
  white-space: pre-wrap;
  line-height: 1.72;
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid var(--theme-card-border, #e5e7eb);
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
}

.chat-message.user .message-content {
  display: inline-block;
  width: auto;
  background: color-mix(in srgb, var(--theme-primary, #2563eb) 14%, var(--theme-card-bg, #ffffff));
  border-color: color-mix(in srgb, var(--theme-primary, #2563eb) 42%, var(--theme-card-border, #e5e7eb));
}

.chat-message.assistant .message-content {
  background: var(--theme-content-bg, #ffffff);
}

.formatted-answer {
  white-space: normal;
}

.formatted-answer :deep(p) {
  margin: 0 0 10px;
}

.formatted-answer :deep(p:last-child) {
  margin-bottom: 0;
}

.formatted-answer :deep(ol) {
  margin: 0;
  padding-left: 20px;
}

.formatted-answer :deep(li) {
  margin: 4px 0;
  line-height: 1.72;
}

.message-sources {
  margin-top: 8px;
  border-radius: 8px;
  padding: 8px 10px;
  border: 1px dashed var(--theme-card-border, #e5e7eb);
  background: var(--theme-card-bg, #ffffff);
}

.knowledge-card {
  margin-top: 10px;
  border-radius: 12px;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--theme-primary, #2563eb) 35%, #e5e7eb);
  background: color-mix(in srgb, var(--theme-primary, #2563eb) 6%, var(--theme-card-bg, #ffffff));
}

.knowledge-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.knowledge-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--theme-text-primary, #111827);
}

.knowledge-card-meta {
  font-size: 12px;
  color: var(--theme-text-secondary, #6b7280);
  margin-bottom: 8px;
}

.knowledge-card-section {
  margin-top: 10px;
}

.knowledge-card-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--theme-text-secondary, #6b7280);
  margin-bottom: 4px;
}

.knowledge-card-list {
  margin: 0;
  padding-left: 18px;
  color: var(--theme-text-primary, #111827);
  font-size: 13px;
  line-height: 1.7;
}

.knowledge-card-list.caution {
  color: color-mix(in srgb, #ef4444 70%, var(--theme-text-primary, #111827));
}

.knowledge-card-list.references {
  color: var(--theme-text-secondary, #6b7280);
  font-size: 12px;
}

.sources-title {
  font-size: 12px;
  margin-bottom: 4px;
  color: var(--theme-text-secondary, #6b7280);
}

.sources-warning {
  margin: 4px 0 6px;
  padding: 6px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, #f59e0b 10%, var(--theme-content-bg, #ffffff));
  color: color-mix(in srgb, #b45309 82%, var(--theme-text-primary, #111827));
  font-size: 12px;
  line-height: 1.5;
}

.source-item {
  font-size: 12px;
  line-height: 1.5;
  color: var(--theme-text-secondary, #6b7280);
}

.answer-panel {
  border-radius: 12px;
  border: 1px solid var(--theme-card-border, #d8e6f4);
  background: var(--theme-content-bg, #ffffff);
  padding: 14px;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--theme-text-primary, #111827);
  margin-bottom: 8px;
}

.answer-text {
  color: var(--theme-text-primary, #111827);
  line-height: 1.75;
  white-space: pre-wrap;
  margin-bottom: 10px;
}

.answer-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: var(--theme-text-secondary, #6b7280);
  font-size: 12px;
}

.source-table {
  margin-top: 10px;
}

.model-config-form {
  width: 100%;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--theme-card-border, #e5e7eb);
  background: var(--theme-content-bg, #ffffff);
}

.model-config-actions {
  margin-top: 10px;
}

.model-operation-form {
  width: 100%;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--theme-card-border, #e5e7eb);
  background: var(--theme-card-bg, #ffffff);
}

.file-input {
  display: block;
  width: 100%;
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-radius: 8px;
  padding: 6px 10px;
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
}

.file-tip {
  margin-top: 8px;
  color: var(--theme-text-secondary, #6b7280);
  font-size: 12px;
}

.health-rag-page :deep(.ant-card) {
  background: var(--theme-content-bg, #ffffff);
  border: 1px solid var(--theme-card-border, #e5e7eb);
}

.health-rag-page :deep(.ant-card-body) {
  color: var(--theme-text-primary, #111827);
}

.health-rag-page :deep(.ant-input),
.health-rag-page :deep(.ant-input-affix-wrapper),
.health-rag-page :deep(.ant-input-number),
.health-rag-page :deep(.ant-input-number-input),
.health-rag-page :deep(.ant-select-selector),
.health-rag-page :deep(.ant-picker) {
  background: var(--theme-card-bg, #ffffff);
  border-color: var(--theme-card-border, #e5e7eb);
  color: var(--theme-text-primary, #111827);
}

.health-rag-page :deep(.ant-input::placeholder),
.health-rag-page :deep(.ant-input-number-input::placeholder),
.health-rag-page :deep(.ant-select-selection-placeholder) {
  color: var(--theme-text-secondary, #9ca3af);
}

.health-rag-page :deep(.ant-input:focus),
.health-rag-page :deep(.ant-input-affix-wrapper-focused),
.health-rag-page :deep(.ant-input-number-focused),
.health-rag-page :deep(.ant-select-focused .ant-select-selector),
.health-rag-page :deep(.ant-picker-focused) {
  border-color: var(--theme-primary, #2563eb);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--theme-primary, #2563eb) 16%, transparent);
}

.health-rag-page :deep(.ant-select-selection-item),
.health-rag-page :deep(.ant-picker-input > input) {
  color: var(--theme-text-primary, #111827);
}

.health-rag-page :deep(.ant-btn-default) {
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
  border-color: var(--theme-card-border, #e5e7eb);
}

.health-rag-page :deep(.ant-btn-default:hover),
.health-rag-page :deep(.ant-btn-default:focus) {
  color: var(--theme-primary, #2563eb);
  border-color: var(--theme-primary, #2563eb);
  background: var(--theme-card-bg, #ffffff);
}

.health-rag-page :deep(.ant-btn-primary) {
  background: var(--theme-primary, #2563eb);
  border-color: var(--theme-primary, #2563eb);
  color: #ffffff;
}

.health-rag-page :deep(.ant-btn-primary:hover),
.health-rag-page :deep(.ant-btn-primary:focus) {
  filter: brightness(0.95);
  background: var(--theme-primary, #2563eb);
  border-color: var(--theme-primary, #2563eb);
  color: #ffffff;
}

.health-rag-page :deep(.ant-btn-link) {
  color: var(--theme-primary, #2563eb);
}

.history-session-link {
  color: var(--theme-primary, #2563eb);
  cursor: pointer;
}

.health-rag-page :deep(.ant-switch-checked) {
  background: var(--theme-primary, #2563eb);
}

.health-rag-page :deep(.ant-table-wrapper) {
  border: 1px solid var(--theme-card-border, #e5e7eb);
  border-radius: 10px;
  overflow: hidden;
  background: var(--theme-card-bg, #ffffff);
}

.health-rag-page :deep(.ant-table) {
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
}

.health-rag-page :deep(.ant-table-thead > tr > th) {
  background: var(--theme-content-bg, #f8fafc);
  color: var(--theme-text-primary, #111827);
  border-bottom: 1px solid var(--theme-card-border, #e5e7eb);
}

.health-rag-page :deep(.ant-table-tbody > tr > td) {
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #111827);
  border-bottom: 1px solid var(--theme-card-border, #e5e7eb);
}

.health-rag-page :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--theme-content-bg, #f8fafc);
}

.health-rag-page :deep(.ant-empty-description) {
  color: var(--theme-text-secondary, #6b7280);
}

.health-rag-page :deep(.ant-pagination-item-active) {
  border-color: var(--theme-primary, #2563eb);
}

.health-rag-page :deep(.ant-pagination-item-active a) {
  color: var(--theme-primary, #2563eb);
}

@media (max-width: 768px) {
  .page-hero {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
