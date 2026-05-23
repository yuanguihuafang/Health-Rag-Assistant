/*
健康 RAG 前端 API
- 知识文档 CRUD、问答聊天、会话管理、历史查询、模型配置、个性化推荐
- 所有接口前缀 /api/health-rag/
*/
import { request } from "@/utils/hertz_request";

export interface ApiResponse<T> {
  success: boolean;
  code: number;
  message: string;
  data: T;
}

export interface HealthSourceRef {
  document_title: string;
  chunk_index: number;
  score: number;
  relevance_label?: string;
  low_confidence?: boolean;
}

export type HealthAskMode = "text" | "voice";

export interface HealthKnowledgeCard {
  title: string;
  core_points: string[];
  cautions: string[];
  references: string[];
  generated_at?: string;
  engine?: string;
  // 允许后端扩展字段
  [key: string]: any;
}

export interface HealthKnowledgeDocument {
  id: number;
  title: string;
  source_type: "manual" | "file" | "url" | string;
  source_path: string;
  content?: string;
  status: "active" | "deleted" | string;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  chunk_count: number;
}

export interface HealthSessionItem {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  latest_question?: string;
}

export interface HealthHistorySessionItem {
  id: number;
  title: string;
  latest_question?: string;
  record_count: number;
  created_at: string;
  updated_at: string;
}

export interface HealthHistoryItem {
  id: number;
  session_id: number;
  question: string;
  answer: string;
  ask_mode: HealthAskMode | string;
  source_refs: HealthSourceRef[];
  knowledge_card?: HealthKnowledgeCard | null;
  latency_ms: number;
  created_at: string;
}

export interface HealthTopicFocus {
  topic: string;
  score: number;
  matched_keywords: string[];
}

export interface HealthRecommendationItem {
  topic: string;
  reason: string;
  document_id: number;
  document_title: string;
  source_path: string;
  chunk_id?: number | null;
  chunk_index?: number | null;
  score?: number | null;
  snippet: string;
  document_updated_at: string;
}

export interface HealthModelConfigPayload {
  BASE_URL?: string;
  API_KEY?: string;
  MODEL?: string;
  base_url?: string;
  api_key?: string;
  model?: string;
}

export interface HealthRetrievalDebugHit {
  chunk_id: number;
  score?: number;
  rrf_score?: number;
  rerank_score?: number;
  document_id?: number;
  document_title?: string;
  chunk_index?: number;
  source_path?: string;
  vector_rank?: number | null;
  sparse_rank?: number | null;
  relevance_label?: string;
}

export interface HealthRetrievalDebugContext {
  chunk_id: number;
  chunk_text: string;
  document_id: number;
  document_title: string;
  chunk_index: number;
  source_path: string;
}

export const healthRagApi = {
  health(): Promise<ApiResponse<any>> {
    return request.get("/api/health-rag/health/");
  },

  listDocuments(params?: {
    document_id?: number;
    query?: string;
    page?: number;
    page_size?: number;
  }): Promise<
    ApiResponse<{
      total: number;
      page: number;
      page_size: number;
      list: HealthKnowledgeDocument[];
    }>
  > {
    return request.get("/api/health-rag/kb/documents/", { params });
  },

  createDocumentJson(payload: {
    title: string;
    source_type?: "manual" | "url" | "file";
    source_path?: string;
    content?: string;
    metadata?: Record<string, any>;
    chunk_size?: number;
    chunk_overlap?: number;
  }): Promise<ApiResponse<any>> {
    return request.post("/api/health-rag/kb/documents/create/", payload);
  },

  createDocumentFile(formData: FormData): Promise<ApiResponse<any>> {
    return request.post("/api/health-rag/kb/documents/create/", formData, {
      timeout: 300000,
    });
  },

  updateDocument(payload: {
    document_id: number;
    title?: string;
    source_path?: string;
    content?: string;
    metadata?: Record<string, any>;
    reindex?: boolean;
    chunk_size?: number;
    chunk_overlap?: number;
  }): Promise<ApiResponse<any>> {
    return request.post("/api/health-rag/kb/documents/update/", payload);
  },

  deleteDocuments(document_ids: number[]): Promise<ApiResponse<any>> {
    return request.post("/api/health-rag/kb/documents/delete/", {
      document_ids,
    });
  },

  reindex(payload?: {
    document_ids?: number[];
    chunk_size?: number;
    chunk_overlap?: number;
  }): Promise<ApiResponse<any>> {
    return request.post("/api/health-rag/kb/reindex/", payload || {});
  },

  listSessions(params?: {
    query?: string;
    page?: number;
    page_size?: number;
  }): Promise<
    ApiResponse<{
      total: number;
      page: number;
      page_size: number;
      list: HealthSessionItem[];
    }>
  > {
    return request.get("/api/health-rag/chat/sessions/", { params });
  },

  createSession(payload?: {
    title?: string;
  }): Promise<ApiResponse<{ session_id: number; title: string }>> {
    return request.post("/api/health-rag/chat/sessions/create/", payload || {});
  },

  deleteSessions(
    session_ids: number[],
  ): Promise<ApiResponse<{ session_count: number; record_count: number }>> {
    return request.post("/api/health-rag/chat/sessions/delete/", {
      session_ids,
    });
  },

  ask(payload: {
    question: string;
    session_id?: number;
    k?: number;
    base_url?: string;
    api_key?: string;
    model?: string;
    ask_mode?: HealthAskMode;
  }): Promise<
    ApiResponse<{
      session_id: number;
      record_id: number;
      question: string;
      ask_mode: HealthAskMode;
      answer: string;
      sources: HealthSourceRef[];
      knowledge_card?: HealthKnowledgeCard;
      latency_ms: number;
    }>
  > {
    return request.post("/api/health-rag/chat/ask/", payload, {
      timeout: 120000,
    });
  },

  transcribeAudio(formData: FormData): Promise<
    ApiResponse<{
      transcript: string;
      duration_ms: number;
      utterances: Array<Record<string, any>>;
    }>
  > {
    return request.post("/api/health-rag/chat/transcribe/", formData, {
      timeout: 120000,
      showError: false,
    });
  },

  listHistory(params?: {
    keyword?: string;
    session_id?: number;
    start_time?: string;
    end_time?: string;
    page?: number;
    page_size?: number;
  }): Promise<
    ApiResponse<{
      total: number;
      page: number;
      page_size: number;
      list: HealthHistoryItem[];
    }>
  > {
    return request.get("/api/health-rag/chat/history/", { params });
  },

  listHistorySessions(params?: {
    keyword?: string;
    session_id?: number;
    start_time?: string;
    end_time?: string;
    page?: number;
    page_size?: number;
  }): Promise<
    ApiResponse<{
      total: number;
      page: number;
      page_size: number;
      list: HealthHistorySessionItem[];
    }>
  > {
    return request.get("/api/health-rag/chat/history/sessions/", { params });
  },

  exportHistoryPdf(payload: {
    record_ids?: number[];
    session_id?: number;
    keyword?: string;
    start_time?: string;
    end_time?: string;
    limit?: number;
  }): Promise<Blob> {
    return request.post(
      "/api/health-rag/chat/history/export/pdf/",
      payload || {},
      {
        responseType: "blob",
        showError: false,
      },
    );
  },

  listRecommendations(params?: {
    limit?: number;
    history_days?: number;
    topic_count?: number;
    k_per_topic?: number;
    randomize?: boolean;
  }): Promise<
    ApiResponse<{
      profile: {
        history_record_count: number;
        analysis_window_days: number;
        topic_focus: HealthTopicFocus[];
      };
      recommendations: HealthRecommendationItem[];
    }>
  > {
    return request.get("/api/health-rag/recommend/", {
      params,
      timeout: 30000,
    });
  },

  modelStatus(): Promise<ApiResponse<any>> {
    return request.get("/api/health-rag/model/status/");
  },

  modelStatusCustom(
    payload: HealthModelConfigPayload,
  ): Promise<ApiResponse<any>> {
    return request.post("/api/health-rag/model/status/custom/", payload);
  },

  switchModel(payload: HealthModelConfigPayload): Promise<ApiResponse<any>> {
    return request.post("/api/health-rag/model/switch/", payload);
  },

  restartModel(
    payload?: HealthModelConfigPayload & { warmup?: boolean },
  ): Promise<ApiResponse<any>> {
    return request.post("/api/health-rag/model/restart/", payload || {});
  },

  retrievalDebug(payload: {
    question: string;
    top_k?: number;
  }): Promise<
    ApiResponse<{
      question: string;
      rewritten_query: string;
      top_k: number;
      query_embedding_dim: number;
      vector_hits: HealthRetrievalDebugHit[];
      sparse_hits: HealthRetrievalDebugHit[];
      rrf_hits: HealthRetrievalDebugHit[];
      rerank_hits: HealthRetrievalDebugHit[];
      final_hits: HealthRetrievalDebugHit[];
      final_contexts: HealthRetrievalDebugContext[];
      rerank_error?: string;
      latency_ms: number;
    }>
  > {
    return request.post("/api/health-rag/retrieval/debug/", payload, {
      timeout: 120000,
    });
  },

  runRagasEval(payload?: {
    input?: string;
    top_k?: number;
    limit?: number;
  }): Promise<
    ApiResponse<{
      elapsed_ms: number;
      latest_result_file: string;
      stdout: string;
      stderr?: string;
    }>
  > {
    return request.post("/api/health-rag/eval/ragas/run/", payload || {}, {
      timeout: 600000,
    });
  },

  runRetrievalEval(payload?: {
    input?: string;
    top_k?: number;
    limit?: number;
  }): Promise<
    ApiResponse<{
      elapsed_ms: number;
      latest_result_file: string;
      stdout: string;
      stderr?: string;
    }>
  > {
    return request.post("/api/health-rag/eval/retrieval/run/", payload || {}, {
      timeout: 600000,
    });
  },
};
