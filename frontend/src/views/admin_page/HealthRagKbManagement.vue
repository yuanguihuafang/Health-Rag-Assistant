<template>
  <div class="health-rag-kb-admin">
    <a-card :bordered="false" class="page-card">
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="kb" tab="知识库管理">
          <div class="toolbar">
            <a-space wrap>
              <a-input-search
                v-model:value="documentQuery.query"
                placeholder="按文档标题搜索"
                enter-button
                @search="loadDocuments"
              />
              <a-button type="primary" @click="openCreateModal">
                <template #icon><PlusOutlined /></template>
                新增文档
              </a-button>
              <a-button
                danger
                :disabled="selectedDocumentIds.length === 0"
                @click="deleteSelectedDocuments"
              >
                <template #icon><DeleteOutlined /></template>
                删除选中
              </a-button>
              <a-button :loading="reindexing" @click="reindexDocuments">
                <template #icon><DatabaseOutlined /></template>
                重建索引
              </a-button>
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
            :row-selection="{
              selectedRowKeys: selectedDocumentIds,
              onChange: onDocumentSelectionChange,
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
                </div>
              </template>
              <template v-else-if="column.key === 'source_type'">
                <a-tag :color="record.source_type === 'file' ? 'blue' : 'green'">
                  {{ formatSourceType(record.source_type) }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'status'">
                <a-tag color="success">{{ record.status === 'active' ? '启用' : record.status }}</a-tag>
              </template>
              <template v-else-if="column.key === 'chunk_count'">
                <span class="chunk-count">{{ record.chunk_count || 0 }} 个</span>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button type="link" size="small" @click="openEditModal(record)">
                  编辑
                </a-button>
              </template>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="model" tab="本地模型管理">
          <a-space direction="vertical" style="width: 100%">
            <div class="toolbar">
              <a-space wrap>
                <a-button :loading="modelLoading" @click="refreshModelStatus">
                  检查模型状态
                </a-button>
              </a-space>
            </div>

            <div class="model-config-form">
              <a-row :gutter="[12, 12]">
                <a-col :xs="24" :md="10">
                  <a-input
                    v-model:value="modelConfig.base_url"
                    placeholder="BASE_URL，例如：http://localhost:11434"
                  />
                </a-col>
                <a-col :xs="24" :md="8">
                  <a-input-password
                    v-model:value="modelConfig.api_key"
                    placeholder="API_KEY（可选）"
                  />
                </a-col>
                <a-col :xs="24" :md="6">
                  <a-input
                    v-model:value="modelConfig.model"
                    placeholder="MODEL，例如：deepseek-r1:1.5b"
                  />
                </a-col>
              </a-row>
              <a-space class="model-config-actions">
                <a-button type="primary" :loading="modelLoading" @click="refreshModelStatusWithCustom">
                  使用自定义参数检测
                </a-button>
                <a-button @click="resetModelConfig">清空参数</a-button>
              </a-space>
            </div>

            <div class="model-config-form">
              <a-row :gutter="[12, 12]">
                <a-col :xs="24" :md="12">
                  <a-select
                    v-model:value="targetModelName"
                    style="width: 100%"
                    placeholder="选择要切换的模型"
                    allow-clear
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
                    <a-button type="primary" :loading="modelSwitching" @click="switchModelVersion">
                      切换模型版本
                    </a-button>
                    <a-button :loading="modelRestarting" @click="restartCurrentModel">
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
              <a-descriptions-item label="是否可用">
                {{ modelInfo?.available ? "是" : "否" }}
              </a-descriptions-item>
              <a-descriptions-item label="API_KEY已配置">
                {{ modelInfo?.api_key_configured ? "是" : "否" }}
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
            </a-descriptions>
          </a-space>
        </a-tab-pane>

      </a-tabs>
    </a-card>

    <a-modal
      v-model:visible="createModalVisible"
      title="新增知识文档"
      :confirm-loading="createSubmitting"
      @ok="submitCreateDocument"
      @cancel="closeCreateModal"
      ok-text="提交"
      cancel-text="取消"
      width="700px"
    >
      <a-form layout="vertical">
        <a-form-item label="文档标题" required>
          <a-input v-model:value="createForm.title" />
        </a-form-item>
        <a-form-item label="上传文件（txt/md）" required>
          <input type="file" class="file-input" @change="onCreateFileChange" />
          <div class="file-tip">
            当前文件：{{ createFile ? createFile.name : "未选择" }}
          </div>
          <div class="field-tip">
            知识库内容通过文件导入，来源由系统按上传文件自动记录，不需要手动填写路径。
          </div>
        </a-form-item>
        <a-form-item label="切分方式">
          <a-radio-group v-model:value="createForm.split_mode">
            <a-radio-button value="fixed">固定长度切分</a-radio-button>
            <a-radio-button value="markdown_entry">按 ## 条目切分</a-radio-button>
          </a-radio-group>
          <div class="field-tip">
            结构化 Markdown 会跳过文件标题和说明，按每个“## 条目 xxx”生成独立知识条目。
          </div>
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="chunk_size">
              <a-input-number
                v-model:value="createForm.chunk_size"
                :min="100"
                :max="2000"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="chunk_overlap">
              <a-input-number
                v-model:value="createForm.chunk_overlap"
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
      v-model:visible="editModalVisible"
      title="编辑知识文档"
      :confirm-loading="editSubmitting"
      @ok="submitEditDocument"
      @cancel="closeEditModal"
      ok-text="保存"
      cancel-text="取消"
      width="700px"
    >
      <a-form layout="vertical">
        <a-form-item label="文档标题" required>
          <a-input v-model:value="editForm.title" />
        </a-form-item>
        <a-form-item label="来源路径">
          <a-input :value="editSourceLabel" disabled />
          <div class="field-tip">
            {{ editIsSeedDocument ? "系统内置语料来源由程序维护，只在详情中查看。" : "自建文档来源来自上传文件，只在详情中查看。" }}
          </div>
        </a-form-item>
        <a-form-item label="更新后重建索引">
          <a-switch v-model:checked="editForm.reindex" />
        </a-form-item>
        <a-row v-if="editForm.reindex" :gutter="12">
          <a-col :span="12">
            <a-form-item label="chunk_size">
              <a-input-number
                v-model:value="editForm.chunk_size"
                :min="100"
                :max="2000"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="chunk_overlap">
              <a-input-number
                v-model:value="editForm.chunk_overlap"
                :min="0"
                :max="300"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import { DatabaseOutlined, DeleteOutlined, PlusOutlined } from "@ant-design/icons-vue";
import { healthRagApi, type HealthKnowledgeDocument } from "@/api/health_rag";

const activeTab = ref("kb");

const documentQuery = reactive({ query: "" });
const documentLoading = ref(false);
const documentList = ref<HealthKnowledgeDocument[]>([]);
const documentPagination = reactive({ total: 0, page: 1, page_size: 10 });
const selectedDocumentIds = ref<number[]>([]);
const reindexing = ref(false);
const modelLoading = ref(false);
const modelSwitching = ref(false);
const modelRestarting = ref(false);
const modelInfo = ref<any>(null);
const modelConfig = reactive({
  base_url: "",
  api_key: "",
  model: "",
});
const targetModelName = ref("");

const createModalVisible = ref(false);
const createSubmitting = ref(false);
const createForm = reactive({
  title: "",
  split_mode: "fixed",
  chunk_size: 500,
  chunk_overlap: 80,
});
const createFile = ref<File | null>(null);

const editModalVisible = ref(false);
const editSubmitting = ref(false);
const editIsSeedDocument = ref(false);
const editSourceLabel = ref("");
const editForm = reactive({
  document_id: 0,
  title: "",
  reindex: false,
  chunk_size: 500,
  chunk_overlap: 80,
});

const documentColumns = [
  { title: "编号", dataIndex: "id", key: "id", width: 72, align: "center" },
  { title: "知识条目", dataIndex: "title", key: "title" },
  { title: "来源", dataIndex: "source_type", key: "source_type", width: 96, align: "center" },
  { title: "状态", dataIndex: "status", key: "status", width: 88, align: "center" },
  { title: "切片", dataIndex: "chunk_count", key: "chunk_count", width: 80, align: "center" },
  { title: "更新时间", dataIndex: "updated_at", key: "updated_at", width: 168 },
  { title: "操作", key: "action", width: 96, align: "center" },
];

const modelInstalledModelOptions = computed<string[]>(() => {
  const list = Array.isArray(modelInfo.value?.installed_models) ? modelInfo.value.installed_models : [];
  return list.filter((item: any) => typeof item === "string" && item.trim()).map((item: string) => item.trim());
});

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

const formatSourceLabel = (doc: HealthKnowledgeDocument) => {
  const sourcePath = (doc.source_path || "").trim();
  if (!sourcePath) return "上传文件自动记录";

  const normalizedPath = sourcePath.replace(/\\/g, "/");
  const projectRelativeMatch = normalizedPath.match(/(?:^|\/)(backend\/health_rag_assistant\/.+)$/);
  if (projectRelativeMatch) {
    return projectRelativeMatch[1];
  }
  return normalizedPath.replace(/^\/+/, "");
};

const loadDocuments = async () => {
  documentLoading.value = true;
  try {
    const res = await healthRagApi.listDocuments({
      query: documentQuery.query,
      page: documentPagination.page,
      page_size: documentPagination.page_size,
    });
    if (!res.success) {
      message.error(res.message || "加载文档失败");
      return;
    }
    documentList.value = res.data.list || [];
    documentPagination.total = res.data.total || 0;
  } catch (error: any) {
    message.error(error?.message || "加载文档失败");
  } finally {
    documentLoading.value = false;
  }
};

const resetCreateForm = () => {
  createForm.title = "";
  createForm.split_mode = "fixed";
  createForm.chunk_size = 500;
  createForm.chunk_overlap = 80;
  createFile.value = null;
};

const openCreateModal = () => {
  resetCreateForm();
  createModalVisible.value = true;
};

const closeCreateModal = () => {
  createModalVisible.value = false;
  resetCreateForm();
};

const onCreateFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  createFile.value = target.files?.[0] || null;
};

const submitCreateDocument = async () => {
  if (!createForm.title.trim()) {
    message.warning("请输入文档标题");
    return;
  }
  if (!createFile.value) {
    message.warning("请上传文件");
    return;
  }

  createSubmitting.value = true;
  try {
    const formData = new FormData();
    formData.append("title", createForm.title.trim());
    formData.append("source_type", "file");
    formData.append("split_mode", createForm.split_mode);
    formData.append("chunk_size", String(createForm.chunk_size));
    formData.append("chunk_overlap", String(createForm.chunk_overlap));
    formData.append("file", createFile.value);
    const res = await healthRagApi.createDocumentFile(formData);

    if (!res.success) {
      message.error(res.message || "文档创建失败");
      return;
    }
    const createdDocCount = Number(res.data?.created_document_count || 1);
    const createdChunkCount = Number(res.data?.created_chunk_count || 0);
    const skippedExistingCount = Number(res.data?.skipped_existing_count || 0);
    if (createForm.split_mode === "markdown_entry") {
      const skippedText = skippedExistingCount > 0 ? `，跳过重复 ${skippedExistingCount} 个` : "";
      message.success(`结构化导入完成：新增 ${createdDocCount} 个条目，${createdChunkCount} 个切片${skippedText}`);
    } else {
      message.success(`文档创建成功：${createdDocCount} 个文档，${createdChunkCount} 个切片`);
    }
    closeCreateModal();
    selectedDocumentIds.value = [];
    await loadDocuments();
  } catch (error: any) {
    message.error(error?.message || "文档创建失败");
  } finally {
    createSubmitting.value = false;
  }
};

const onDocumentSelectionChange = (keys: any[]) => {
  selectedDocumentIds.value = (keys || [])
    .map((item) => Number(item))
    .filter((n) => Number.isFinite(n));
};

const deleteSelectedDocuments = () => {
  if (selectedDocumentIds.value.length === 0) return;
  Modal.confirm({
    title: "确认删除",
    content: `确认删除选中的 ${selectedDocumentIds.value.length} 条文档吗？`,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    onOk: async () => {
      const res = await healthRagApi.deleteDocuments(selectedDocumentIds.value);
      if (!res.success) {
        message.error(res.message || "删除失败");
        return;
      }
      message.success("删除成功");
      selectedDocumentIds.value = [];
      await loadDocuments();
    },
  });
};

const reindexDocuments = async () => {
  reindexing.value = true;
  try {
    const payload =
      selectedDocumentIds.value.length > 0
        ? {
            document_ids: selectedDocumentIds.value,
            chunk_size: createForm.chunk_size,
            chunk_overlap: createForm.chunk_overlap,
          }
        : {
            chunk_size: createForm.chunk_size,
            chunk_overlap: createForm.chunk_overlap,
          };
    const res = await healthRagApi.reindex(payload);
    if (!res.success) {
      message.error(res.message || "重建失败");
      return;
    }
    const docCount = Number(res.data?.document_count || 0);
    const chunkCount = Number(res.data?.chunk_count || 0);
    if (docCount === 0) {
      message.warning(res.message || "没有可重建索引的文档，请先新增知识文档");
    } else {
      message.success(`重建完成：${docCount} 个文档，${chunkCount} 个切片`);
    }
    await loadDocuments();
  } catch (error: any) {
    message.error(error?.message || "重建失败");
  } finally {
    reindexing.value = false;
  }
};

const openEditModal = (doc: HealthKnowledgeDocument) => {
  editForm.document_id = doc.id;
  editForm.title = doc.title || "";
  editIsSeedDocument.value = doc.metadata?.seed === "default_health_rag_kb";
  editSourceLabel.value = formatSourceLabel(doc);
  editForm.reindex = false;
  editForm.chunk_size = 500;
  editForm.chunk_overlap = 80;
  editModalVisible.value = true;
};

const closeEditModal = () => {
  editModalVisible.value = false;
  editForm.document_id = 0;
  editForm.title = "";
  editIsSeedDocument.value = false;
  editSourceLabel.value = "";
  editForm.reindex = false;
  editForm.chunk_size = 500;
  editForm.chunk_overlap = 80;
};

const submitEditDocument = async () => {
  if (!editForm.document_id) {
    message.warning("缺少文档ID");
    return;
  }
  if (!editForm.title.trim()) {
    message.warning("请输入文档标题");
    return;
  }
  if (Number(editForm.chunk_overlap) >= Number(editForm.chunk_size)) {
    message.warning("chunk_overlap 必须小于 chunk_size");
    return;
  }

  editSubmitting.value = true;
  try {
    const payload: {
      document_id: number;
      title: string;
      reindex: boolean;
      chunk_size?: number;
      chunk_overlap?: number;
    } = {
      document_id: editForm.document_id,
      title: editForm.title.trim(),
      reindex: Boolean(editForm.reindex),
    };
    if (payload.reindex) {
      payload.chunk_size = Number(editForm.chunk_size);
      payload.chunk_overlap = Number(editForm.chunk_overlap);
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
    closeEditModal();
    await loadDocuments();
  } catch (error: any) {
    message.error(error?.message || "文档更新失败");
  } finally {
    editSubmitting.value = false;
  }
};

const handleDocumentTableChange = (pagination: any) => {
  documentPagination.page = pagination?.current || 1;
  documentPagination.page_size = pagination?.pageSize || 10;
  loadDocuments();
};

const refreshModelStatus = async () => {
  modelLoading.value = true;
  try {
    const res = await healthRagApi.modelStatus();
    if (!res.success) {
      message.error(res.message || "模型状态获取失败");
      return;
    }
    modelInfo.value = res.data;
    targetModelName.value = modelInfo.value?.model_name || targetModelName.value || "";
  } catch (error: any) {
    message.error(error?.message || "模型状态获取失败");
  } finally {
    modelLoading.value = false;
  }
};

const refreshModelStatusWithCustom = async () => {
  const payload: Record<string, string> = {};
  if (modelConfig.base_url.trim()) payload.BASE_URL = modelConfig.base_url.trim();
  if (modelConfig.api_key.trim()) payload.API_KEY = modelConfig.api_key.trim();
  if (modelConfig.model.trim()) payload.MODEL = modelConfig.model.trim();
  if (Object.keys(payload).length === 0) {
    message.warning("请至少填写一个参数：BASE_URL / API_KEY / MODEL");
    return;
  }

  modelLoading.value = true;
  try {
    const res = await healthRagApi.modelStatusCustom(payload);
    if (!res.success) {
      message.error(res.message || "自定义模型状态获取失败");
      return;
    }
    modelInfo.value = res.data;
    targetModelName.value = modelInfo.value?.model_name || targetModelName.value || "";
    message.success("自定义模型状态检测完成");
  } catch (error: any) {
    message.error(error?.message || "自定义模型状态获取失败");
  } finally {
    modelLoading.value = false;
  }
};

const resetModelConfig = () => {
  modelConfig.base_url = "";
  modelConfig.api_key = "";
  modelConfig.model = "";
};

const switchModelVersion = async () => {
  const targetModel = (targetModelName.value || modelConfig.model || modelInfo.value?.model_name || "").trim();
  if (!targetModel) {
    message.warning("请选择或输入目标模型");
    return;
  }

  const payload: Record<string, any> = { MODEL: targetModel };
  if (modelConfig.base_url.trim()) payload.BASE_URL = modelConfig.base_url.trim();
  if (modelConfig.api_key.trim()) payload.API_KEY = modelConfig.api_key.trim();

  modelSwitching.value = true;
  try {
    const res = await healthRagApi.switchModel(payload);
    if (!res.success) {
      message.error(res.message || "模型切换失败");
      return;
    }
    if (res.data?.status) {
      modelInfo.value = res.data.status;
    } else {
      await refreshModelStatus();
    }
    targetModelName.value = modelInfo.value?.model_name || targetModel;
    message.success("模型切换成功");
  } catch (error: any) {
    message.error(error?.message || "模型切换失败");
  } finally {
    modelSwitching.value = false;
  }
};

const restartCurrentModel = async () => {
  const modelName = (targetModelName.value || modelConfig.model || modelInfo.value?.model_name || "").trim();
  const payload: Record<string, any> = { warmup: true };
  if (modelName) payload.MODEL = modelName;
  if (modelConfig.base_url.trim()) payload.BASE_URL = modelConfig.base_url.trim();
  if (modelConfig.api_key.trim()) payload.API_KEY = modelConfig.api_key.trim();

  modelRestarting.value = true;
  try {
    const res = await healthRagApi.restartModel(payload);
    if (!res.success) {
      message.error(res.message || "模型重启失败");
      return;
    }
    if (res.data?.status) {
      modelInfo.value = res.data.status;
    } else {
      await refreshModelStatus();
    }
    targetModelName.value = modelInfo.value?.model_name || modelName;
    message.success("模型重启成功");
  } catch (error: any) {
    message.error(error?.message || "模型重启失败");
  } finally {
    modelRestarting.value = false;
  }
};

onMounted(async () => {
  await Promise.all([loadDocuments(), refreshModelStatus()]);
});
</script>

<style scoped>
.health-rag-kb-admin {
  min-height: 100%;
}

.page-card {
  border-radius: 12px;
}

.toolbar {
  margin-bottom: 14px;
}

.model-config-form {
  width: 100%;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid #e6ecf4;
  background: #fbfdff;
}

.model-config-actions {
  margin-top: 10px;
}

.file-input {
  display: block;
  width: 100%;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 6px 10px;
  background: #fff;
}

.file-tip {
  margin-top: 8px;
  color: #6b7f93;
  font-size: 12px;
}

.field-tip {
  margin-top: 6px;
  color: #7a8ba0;
  font-size: 12px;
  line-height: 1.5;
}

.doc-title-cell {
  min-width: 0;
}

.doc-title {
  color: #172033;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

</style>
