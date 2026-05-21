import json
from unittest.mock import patch

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from hertz_studio_django_auth.utils.auth.token_utils import TokenUtils

from .models import HealthKnowledgeChunk, HealthKnowledgeDocument, HealthQARecord, HealthQASession


class HealthRagVoiceMVPTests(TestCase):
    def setUp(self):
        HertzUser = apps.get_model("hertz_studio_django_auth", "HertzUser")
        self.user = HertzUser.objects.create_user(
            username="voice_tester",
            email="voice_tester@example.com",
            password="Passw0rd!123",
            real_name="语音测试用户",
            status=1,
        )
        self.token = TokenUtils.generate_token(
            {
                "user_id": self.user.user_id,
                "username": self.user.username,
                "roles": [],
                "permissions": [],
            }
        )
        self.auth_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {self.token}",
        }

    def test_chat_transcribe_requires_file(self):
        response = self.client.post(
            "/api/health-rag/chat/transcribe/",
            data={"language": "zh-CN", "format": "wav", "rate": 16000},
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("请上传语音文件", payload["message"])

    @patch("health_rag_assistant.views.transcribe_file")
    def test_chat_transcribe_success(self, mock_transcribe_file):
        mock_transcribe_file.return_value = {
            "text": "失眠应该怎么调理？",
            "duration_ms": 5230,
            "utterances": [{"text": "失眠应该怎么调理？"}],
        }

        response = self.client.post(
            "/api/health-rag/chat/transcribe/",
            data={
                "language": "zh-CN",
                "format": "wav",
                "rate": 16000,
                "file": SimpleUploadedFile(
                    "question.wav",
                    b"RIFF\x00\x00\x00\x00WAVEfmt ",
                    content_type="audio/wav",
                ),
            },
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["transcript"], "失眠应该怎么调理？")
        self.assertEqual(payload["data"]["duration_ms"], 5230)
        self.assertEqual(len(payload["data"]["utterances"]), 1)

    @patch("health_rag_assistant.views.transcribe_file")
    def test_chat_transcribe_no_text_returns_business_error(self, mock_transcribe_file):
        from .services.asr_service import ASRServiceError

        mock_transcribe_file.side_effect = ASRServiceError("ASR 未返回可用的识别文本")

        response = self.client.post(
            "/api/health-rag/chat/transcribe/",
            data={
                "language": "zh-CN",
                "format": "wav",
                "rate": 16000,
                "file": SimpleUploadedFile(
                    "question.wav",
                    b"RIFF\x00\x00\x00\x00WAVEfmt ",
                    content_type="audio/wav",
                ),
            },
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("未识别到有效语音内容", payload["message"])

    @patch("health_rag_assistant.views.build_knowledge_card")
    @patch("health_rag_assistant.views.ask_with_rag")
    def test_chat_ask_persists_voice_mode(
        self, mock_ask_with_rag, mock_build_knowledge_card
    ):
        mock_ask_with_rag.return_value = (
            "建议保持规律作息，睡前减少咖啡因摄入。",
            [{"document_title": "睡眠健康指南", "chunk_index": 1, "score": 0.93}],
        )
        mock_build_knowledge_card.return_value = {
            "title": "睡眠调理建议",
            "core_points": ["规律作息"],
            "cautions": [],
            "references": ["睡眠健康指南 #1"],
        }

        response = self.client.post(
            "/api/health-rag/chat/ask/",
            data=json.dumps(
                {
                    "question": "失眠应该怎么调理？",
                    "ask_mode": "voice",
                    "k": 3,
                }
            ),
            content_type="application/json",
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["question"], "失眠应该怎么调理？")
        self.assertEqual(payload["data"]["ask_mode"], "voice")

        record = HealthQARecord.objects.get(id=payload["data"]["record_id"])
        self.assertEqual(record.ask_mode, "voice")
        self.assertEqual(record.question, "失眠应该怎么调理？")

    def test_llm_selects_existing_ollama_model_when_default_missing(self):
        from .services.llm_service import HealthLLMService

        selected = HealthLLMService._select_ollama_model(
            ["gemma3:4b", "qwen2.5:3b"],
            preferred="deepseek-r1:1.5b",
        )

        self.assertEqual(selected, "qwen2.5:3b")

    def test_retriever_ranks_sleep_content_above_unrelated_text(self):
        from .services.retriever_service import retrieve_top_k

        sleep_doc = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="睡眠调理资料",
            source_type="manual",
            content="长期熬夜会造成睡眠非常差、入睡困难和精神差，建议规律作息并注意休息。",
            metadata={},
        )
        hemorrhoid_doc = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="痔疮护理资料",
            source_type="manual",
            content="外痔用药需要结合疼痛、出血和局部肿胀情况，建议到肛肠科检查。",
            metadata={},
        )
        sleep_chunk = HealthKnowledgeChunk.objects.create(
            document=sleep_doc,
            chunk_index=0,
            chunk_text=sleep_doc.content,
        )
        hemorrhoid_chunk = HealthKnowledgeChunk.objects.create(
            document=hemorrhoid_doc,
            chunk_index=0,
            chunk_text=hemorrhoid_doc.content,
        )

        result = retrieve_top_k(
            "失眠怎么调理？",
            chunks=[hemorrhoid_chunk, sleep_chunk],
            k=2,
        )

        self.assertEqual(result[0][1].document.title, "睡眠调理资料")
        self.assertGreater(result[0][0], result[1][0])

    def test_retriever_uses_health_topic_boosts_for_specific_queries(self):
        from .services.retriever_service import retrieve_top_k

        def make_chunk(title, content, topic):
            document = HealthKnowledgeDocument.objects.create(
                user=self.user,
                title=title,
                source_type="manual",
                content=content,
                metadata={"topic": topic},
            )
            return HealthKnowledgeChunk.objects.create(
                document=document,
                chunk_index=0,
                chunk_text=content,
            )

        women_chunk = make_chunk(
            "女性孕产：经期腹痛调理",
            "主题：女性孕产\n\n问题：经期腹痛需要怎么调理？\n\n回答：经期腹痛常见于痛经，应注意保暖、规律休息，疼痛加重时到妇科检查。",
            "女性孕产",
        )
        cardio_chunk = make_chunk(
            "心血管：胸闷心悸",
            "主题：心血管\n\n问题：胸闷心悸怎么办？\n\n回答：胸闷心悸要观察是否伴胸痛、出汗和呼吸困难。",
            "心血管",
        )
        pediatric_chunk = make_chunk(
            "儿童母婴：宝宝积食",
            "主题：儿童母婴\n\n问题：宝宝积食不爱吃饭怎么办？\n\n回答：先减少零食，规律喂养，持续腹痛或发热应到儿科评估。",
            "儿童母婴",
        )

        women_result = retrieve_top_k(
            "经期腹痛需要怎么调理",
            chunks=[cardio_chunk, women_chunk, pediatric_chunk],
            k=2,
        )
        pediatric_result = retrieve_top_k(
            "宝宝积食不爱吃饭怎么办",
            chunks=[cardio_chunk, women_chunk, pediatric_chunk],
            k=2,
        )

        self.assertEqual(women_result[0][1].document.title, "女性孕产：经期腹痛调理")
        self.assertEqual(pediatric_result[0][1].document.title, "儿童母婴：宝宝积食")

    def test_retriever_dedupes_near_duplicate_question_variants(self):
        from .services.retriever_service import retrieve_top_k

        chunks = []
        for title, question in (
            ("发热处理 A", "宝宝发热38度多先怎么处理"),
            ("发热处理 B", "宝宝发热38度多先怎么处理怎么办"),
            ("发热处理 C", "宝宝发热38度多先怎么处理正常吗"),
            ("就医边界", "宝宝发烧精神差什么时候需要去医院"),
        ):
            document = HealthKnowledgeDocument.objects.create(
                user=self.user,
                title=title,
                source_type="manual",
                content=(
                    f"主题：儿童母婴\n\n问题：{question}\n\n"
                    "回答：宝宝发热需要测量体温、补水并观察精神状态。"
                ),
                metadata={"topic": "儿童母婴"},
            )
            chunks.append(
                HealthKnowledgeChunk.objects.create(
                    document=document,
                    chunk_index=0,
                    chunk_text=document.content,
                )
            )

        result = retrieve_top_k("宝宝发烧怎么办", chunks=chunks, k=3)
        titles = [chunk.document.title for _, chunk in result]

        self.assertIn("就医边界", titles)
        self.assertLessEqual(
            len([title for title in titles if title.startswith("发热处理")]),
            1,
        )

    def test_seed_document_source_path_cannot_be_changed(self):
        admin_headers = {
            "HTTP_AUTHORIZATION": "Bearer "
            + TokenUtils.generate_token(
                {
                    "user_id": self.user.user_id,
                    "username": self.user.username,
                    "roles": ["super_admin"],
                    "permissions": [],
                }
            )
        }
        document = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="默认健康问答样本 1",
            source_type="file",
            source_path="backend/health_rag_assistant/datasets/cMedQA/health_qa_sample_for_rag.md#sample-1",
            content="问题：测试\n\n回答：测试",
            metadata={"seed": "default_health_rag_kb", "dataset": "cMedQA sample", "sample_no": 1},
        )

        response = self.client.post(
            "/api/health-rag/kb/documents/update/",
            data=json.dumps(
                {
                    "document_id": document.id,
                    "title": document.title,
                    "source_path": "wrong/path.md#sample-1",
                }
            ),
            content_type="application/json",
            **admin_headers,
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertFalse(payload["success"])
        document.refresh_from_db()
        self.assertEqual(
            document.source_path,
            "backend/health_rag_assistant/datasets/cMedQA/health_qa_sample_for_rag.md#sample-1",
        )

    def test_kb_create_rejects_manual_text_entry(self):
        admin_headers = {
            "HTTP_AUTHORIZATION": "Bearer "
            + TokenUtils.generate_token(
                {
                    "user_id": self.user.user_id,
                    "username": self.user.username,
                    "roles": ["super_admin"],
                    "permissions": [],
                }
            )
        }

        response = self.client.post(
            "/api/health-rag/kb/documents/create/",
            data=json.dumps(
                {
                    "title": "手动录入测试",
                    "source_type": "manual",
                    "source_path": "wrong/path.md",
                    "content": "问题：测试\n\n回答：测试",
                }
            ),
            content_type="application/json",
            **admin_headers,
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("只支持上传", payload["message"])

    def test_kb_update_reindex_rebuilds_document_chunks(self):
        admin_headers = {
            "HTTP_AUTHORIZATION": "Bearer "
            + TokenUtils.generate_token(
                {
                    "user_id": self.user.user_id,
                    "username": self.user.username,
                    "roles": ["super_admin"],
                    "permissions": [],
                }
            )
        }
        document = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="重建索引测试文档",
            source_type="file",
            source_path="uploads/reindex-test.md",
            content="睡眠调理建议：" + "保持规律作息，睡前减少刺激性饮食。" * 20,
            metadata={},
        )
        HealthKnowledgeChunk.objects.create(
            document=document,
            chunk_index=0,
            chunk_text="旧切片",
        )

        response = self.client.post(
            "/api/health-rag/kb/documents/update/",
            data=json.dumps(
                {
                    "document_id": document.id,
                    "title": document.title,
                    "reindex": True,
                    "chunk_size": 100,
                    "chunk_overlap": 0,
                }
            ),
            content_type="application/json",
            **admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        rebuilt_count = HealthKnowledgeChunk.objects.filter(document=document).count()
        self.assertEqual(payload["data"]["updated_chunk_count"], rebuilt_count)
        self.assertGreater(rebuilt_count, 1)
        self.assertFalse(
            HealthKnowledgeChunk.objects.filter(
                document=document,
                chunk_text="旧切片",
            ).exists()
        )

    def test_chat_history_sessions_groups_records_by_conversation(self):
        session = HealthQASession.objects.create(user=self.user, title="连续问答")
        other_session = HealthQASession.objects.create(user=self.user, title="另一个对话")
        HealthQARecord.objects.create(
            session=session,
            user=self.user,
            question="身体冒虚汗发冷怎么办？",
            answer="注意保暖并观察症状。",
        )
        HealthQARecord.objects.create(
            session=session,
            user=self.user,
            question="女性也会这样吗？",
            answer="女性也可能出现类似表现。",
        )
        HealthQARecord.objects.create(
            session=other_session,
            user=self.user,
            question="失眠怎么调理？",
            answer="保持规律作息。",
        )

        response = self.client.get(
            "/api/health-rag/chat/history/sessions/",
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["total"], 2)
        grouped = {item["id"]: item for item in payload["data"]["list"]}
        self.assertEqual(grouped[session.id]["record_count"], 2)
        self.assertEqual(grouped[other_session.id]["record_count"], 1)

    def test_chat_session_delete_only_deletes_current_user_session(self):
        HertzUser = apps.get_model("hertz_studio_django_auth", "HertzUser")
        other_user = HertzUser.objects.create_user(
            username="other_health_user",
            email="other_health_user@example.com",
            password="Passw0rd!123",
            real_name="其他用户",
            status=1,
        )
        own_session = HealthQASession.objects.create(user=self.user, title="自己的对话")
        other_session = HealthQASession.objects.create(user=other_user, title="别人的对话")
        HealthQARecord.objects.create(
            session=own_session,
            user=self.user,
            question="失眠怎么调理？",
            answer="保持规律作息。",
        )
        HealthQARecord.objects.create(
            session=other_session,
            user=other_user,
            question="胃痛怎么办？",
            answer="建议观察并就医。",
        )

        response = self.client.post(
            "/api/health-rag/chat/sessions/delete/",
            data=json.dumps({"session_ids": [own_session.id, other_session.id]}),
            content_type="application/json",
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["session_count"], 1)
        self.assertEqual(payload["data"]["record_count"], 1)
        self.assertFalse(HealthQASession.objects.filter(id=own_session.id).exists())
        self.assertTrue(HealthQASession.objects.filter(id=other_session.id).exists())
        self.assertTrue(HealthQARecord.objects.filter(session_id=other_session.id).exists())

    def test_retriever_treats_gender_as_context_for_weight_query(self):
        from .services.retriever_service import retrieve_top_k

        chunks, weight_doc, male_doc = self._make_gender_weight_chunks()

        results = retrieve_top_k(
            "我是男性，平时久坐，想减肥，给我推荐一些合适的建议",
            chunks=chunks,
            k=2,
        )

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0][1].document_id, weight_doc.id)
        self.assertGreater(results[0][0], results[1][0])

    def test_retriever_treats_female_as_context_for_weight_query(self):
        from .services.retriever_service import retrieve_top_k

        chunks, weight_doc, _male_doc = self._make_gender_weight_chunks()
        women_doc = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="女性孕产 001：经期腹痛怎么调理",
            source_type="manual",
            content="女性孕产资料",
            metadata={"topic": "女性孕产"},
        )
        women_chunk = HealthKnowledgeChunk.objects.create(
            document=women_doc,
            chunk_index=0,
            chunk_text=(
                "主题：女性孕产\n问题：女性经期腹痛怎么调理？\n"
                "回答：注意保暖和规律休息，疼痛明显应到妇科评估。"
            ),
        )
        chunks = [*chunks, women_chunk]

        results = retrieve_top_k(
            "我是女性，平时久坐，想减肥，给我推荐一些合适的建议",
            chunks=chunks,
            k=3,
        )

        self.assertGreaterEqual(len(results), 3)
        self.assertEqual(results[0][1].document_id, weight_doc.id)
        self.assertNotEqual(results[0][1].document_id, women_doc.id)

    def test_retriever_still_uses_specific_gender_health_symptoms(self):
        from .services.retriever_service import retrieve_top_k

        chunks, _weight_doc, male_doc = self._make_gender_weight_chunks()

        results = retrieve_top_k(
            "男性前列腺不适尿频怎么办",
            chunks=chunks,
            k=2,
        )

        self.assertEqual(results[0][1].document_id, male_doc.id)

    def test_retriever_treats_age_group_as_context_for_weight_query(self):
        from .services.retriever_service import retrieve_top_k

        chunks, weight_doc, pediatric_doc, elderly_doc = self._make_age_weight_chunks()
        for question in (
            "婴儿家长久坐想减肥，给一些合适建议",
            "老人平时久坐想减肥，给一些合适建议",
        ):
            results = retrieve_top_k(question, chunks=chunks, k=3)
            self.assertGreaterEqual(len(results), 3)
            self.assertEqual(results[0][1].document_id, weight_doc.id, msg=question)
            self.assertNotEqual(results[0][1].document_id, pediatric_doc.id, msg=question)
            self.assertNotEqual(results[0][1].document_id, elderly_doc.id, msg=question)

    def test_retriever_still_uses_specific_child_and_elderly_symptoms(self):
        from .services.retriever_service import retrieve_top_k

        chunks, _weight_doc, pediatric_doc, elderly_doc = self._make_age_weight_chunks()
        child_results = retrieve_top_k("宝宝发热38度怎么处理", chunks=chunks, k=3)
        elderly_results = retrieve_top_k("老人血压偏高怎么管理", chunks=chunks, k=3)

        self.assertEqual(child_results[0][1].document_id, pediatric_doc.id)
        self.assertEqual(elderly_results[0][1].document_id, elderly_doc.id)

    def test_contextual_retrieval_keeps_previous_topic_for_short_followup(self):
        from .services.rag_service import build_contextual_retrieval_question

        query = build_contextual_retrieval_question(
            question="女性呢？",
            conversation_history=[
                {
                    "question": "我是男性，平时久坐，想减肥，给我推荐一些合适的建议",
                    "answer": "建议减少久坐并控制热量。",
                }
            ],
        )

        self.assertIn("久坐", query)
        self.assertIn("减肥", query)
        self.assertIn("女性呢？", query)

    @patch("health_rag_assistant.services.rag_service.HealthLLMService.generate_answer")
    @patch("health_rag_assistant.services.rag_service.retrieve_top_k")
    def test_ask_with_rag_uses_contextual_query_for_short_followup(
        self,
        mock_retrieve_top_k,
        mock_generate_answer,
    ):
        from .services.rag_service import ask_with_rag

        chunks, _weight_doc, _male_doc = self._make_gender_weight_chunks()
        mock_retrieve_top_k.return_value = [(0.88, chunks[0])]
        mock_generate_answer.return_value = "女性也可以按久坐减脂方向调整。"

        answer, _sources = ask_with_rag(
            user_id=self.user.user_id,
            question="女性呢？",
            conversation_history=[
                {
                    "question": "我是男性，平时久坐，想减肥，给我推荐一些合适的建议",
                    "answer": "建议减少久坐并控制热量。",
                }
            ],
        )

        self.assertIn("女性", answer)
        called_question = mock_retrieve_top_k.call_args.kwargs["question"]
        self.assertIn("久坐", called_question)
        self.assertIn("减肥", called_question)
        self.assertIn("女性呢？", called_question)

    def _make_gender_weight_chunks(self):
        weight_doc = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="运动体重 001：久坐想减肥怎么做",
            source_type="manual",
            content="久坐人群体重管理建议",
            metadata={"topic": "运动体重"},
        )
        male_doc = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="男性泌尿 001：前列腺不适怎么办",
            source_type="manual",
            content="男性泌尿专科建议",
            metadata={"topic": "男性泌尿"},
        )
        weight_chunk = HealthKnowledgeChunk.objects.create(
            document=weight_doc,
            chunk_index=0,
            chunk_text=(
                "主题：运动体重\n问题：平时久坐想减肥怎么安排？\n"
                "回答：建议控制热量摄入，增加日常步行和力量训练，减少久坐时间。"
            ),
        )
        male_chunk = HealthKnowledgeChunk.objects.create(
            document=male_doc,
            chunk_index=0,
            chunk_text=(
                "主题：男性泌尿\n问题：男性前列腺不适尿频怎么办？\n"
                "回答：建议就医检查前列腺和泌尿系统。"
            ),
        )
        return [weight_chunk, male_chunk], weight_doc, male_doc

    def _make_age_weight_chunks(self):
        weight_doc = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="运动体重 010：久坐想减肥怎么做",
            source_type="manual",
            content="久坐人群体重管理建议",
            metadata={"topic": "运动体重"},
        )
        pediatric_doc = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="儿童母婴 010：宝宝发热怎么处理",
            source_type="manual",
            content="儿童母婴发热护理",
            metadata={"topic": "儿童母婴"},
        )
        elderly_doc = HealthKnowledgeDocument.objects.create(
            user=self.user,
            title="血压与心血管 010：老人血压偏高怎么管理",
            source_type="manual",
            content="老人血压慢病管理",
            metadata={"topic": "血压与心血管"},
        )
        weight_chunk = HealthKnowledgeChunk.objects.create(
            document=weight_doc,
            chunk_index=0,
            chunk_text=(
                "主题：运动体重\n问题：平时久坐想减肥怎么安排？\n"
                "回答：建议控制热量摄入，增加日常步行和力量训练，减少久坐时间。"
            ),
        )
        pediatric_chunk = HealthKnowledgeChunk.objects.create(
            document=pediatric_doc,
            chunk_index=0,
            chunk_text=(
                "主题：儿童母婴\n问题：宝宝发热38度怎么处理？\n"
                "回答：测量体温、补水并观察精神状态，必要时到儿科就诊。"
            ),
        )
        elderly_chunk = HealthKnowledgeChunk.objects.create(
            document=elderly_doc,
            chunk_index=0,
            chunk_text=(
                "主题：血压与心血管\n问题：老人血压偏高怎么管理？\n"
                "回答：规律监测血压，低盐饮食，按医嘱用药并复诊。"
            ),
        )
        return [weight_chunk, pediatric_chunk, elderly_chunk], weight_doc, pediatric_doc, elderly_doc

    @patch("health_rag_assistant.views.build_knowledge_card")
    @patch("health_rag_assistant.views.ask_with_rag")
    def test_chat_history_returns_ask_mode(
        self, mock_ask_with_rag, mock_build_knowledge_card
    ):
        mock_ask_with_rag.return_value = (
            "建议先记录作息并观察持续时间。",
            [{"document_title": "健康问答测试文档", "chunk_index": 2, "score": 0.88}],
        )
        mock_build_knowledge_card.return_value = {}

        ask_response = self.client.post(
            "/api/health-rag/chat/ask/",
            data=json.dumps(
                {
                    "question": "最近经常失眠怎么办？",
                    "ask_mode": "voice",
                }
            ),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertTrue(ask_response.json()["success"])

        history_response = self.client.get(
            "/api/health-rag/chat/history/",
            **self.auth_headers,
        )
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertTrue(history_payload["success"])
        self.assertGreaterEqual(len(history_payload["data"]["list"]), 1)
        self.assertEqual(history_payload["data"]["list"][0]["ask_mode"], "voice")

    @patch("health_rag_assistant.views.build_knowledge_card")
    @patch("health_rag_assistant.views.ask_with_rag")
    def test_chat_ask_passes_recent_conversation_history(
        self, mock_ask_with_rag, mock_build_knowledge_card
    ):
        session = HealthQASession.objects.create(user=self.user, title="多轮测试")
        HealthQARecord.objects.create(
            session=session,
            user=self.user,
            question="我最近失眠",
            answer="先规律作息",
            ask_mode="text",
            source_refs=[],
            knowledge_card={},
            latency_ms=100,
        )
        HealthQARecord.objects.create(
            session=session,
            user=self.user,
            question="还总是头晕",
            answer="注意补水和休息",
            ask_mode="text",
            source_refs=[],
            knowledge_card={},
            latency_ms=120,
        )
        mock_ask_with_rag.return_value = ("请继续观察症状变化。", [])
        mock_build_knowledge_card.return_value = {}

        response = self.client.post(
            "/api/health-rag/chat/ask/",
            data=json.dumps(
                {
                    "question": "那我现在需要去医院吗？",
                    "session_id": session.id,
                }
            ),
            content_type="application/json",
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        kwargs = mock_ask_with_rag.call_args.kwargs
        self.assertEqual(kwargs["question"], "那我现在需要去医院吗？")
        self.assertEqual(len(kwargs["conversation_history"]), 2)
        self.assertEqual(kwargs["conversation_history"][0]["question"], "我最近失眠")
        self.assertEqual(kwargs["conversation_history"][1]["question"], "还总是头晕")
