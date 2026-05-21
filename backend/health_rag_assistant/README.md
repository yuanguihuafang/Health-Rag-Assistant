# health_rag_assistant

健康 RAG 问答助手核心模块（MVP）。

## 职责

- 知识文档管理：上传、分块、索引、检索
- 健康问答：混合检索 + LLM 生成 + 来源返回
- 会话管理：多轮对话、历史归档
- 语音支持：录音上传 → ASR 转写 → 问答
- 知识卡片：每次问答自动生成结构化摘要
- 个性化推荐：基于用户问答历史的主题推荐
- PDF 导出：问答记录导出为 PDF

## 架构

```
用户请求 → views.py → services/ 层 → models.py (SQLite)
                              │
                              ├─ rag_service.py      RAG 主流程
                              ├─ retriever_service.py 混合重排检索
                              ├─ llm_service.py      LLM（Ollama / OpenAI）
                              ├─ kb_service.py       文档 CRUD + 索引重建
                              ├─ recommend_service.py 推荐
                              ├─ knowledge_card_service.py  知识卡片
                              ├─ asr_service.py      语音识别（火山引擎）
                              ├─ seed_service.py     种子数据导入
                              └─ pdf_export_service.py  PDF 导出
```

## 路由前缀

- `/api/health-rag/`

## 检索设计要点

1. **纯本地混合重排**，无需外部 embedding API
   - char n-gram 哈希向量 + TF-IDF（char 3-gram）+ 关键词命中 + 主题加成
   - 四路加权融合 → 校准函数映射到 0~1 相关性分
2. **FAISS 仅用于索引构建和状态展示**，问答侧不走 FAISS 检索
3. **多轮对话**：短追问自动拼接上文 question 再检索
4. **查询扩展**：40+ 组症状同义词（失眠→睡不着/入睡困难...）
5. **13 个健康主题分类**：sleep / digestive / cardio / pediatric / women / men / urgent 等

## LLM 模式

- **Ollama 模式**：`OLLAMA_BASE_URL` + `/api/chat`
- **OpenAI 兼容模式**：检测到 `/v1` 路径或 API Key 时自动切换
- 双模式互备：首选失败自动尝试另一种
- 运行时可切换，无需重启服务

## 依赖的外部服务（可选）

- ASR：火山引擎语音识别（需配置 APP_KEY / ACCESS_KEY / RESOURCE_ID）
- LLM：Ollama（本地）或 OpenAI 兼容 API
- 邮件：SMTP 服务（密码重置时使用）
