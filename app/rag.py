"""RAG 引擎：混合检索 + DeepSeek 生成，供命令行 / FastAPI / 报警分析共用。"""
import os
import re

import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI

CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "alarm_codes"
EMBED_MODEL = "BAAI/bge-small-zh-v1.5"
TOP_K = 5

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

SYSTEM_PROMPT = """你是一名西门子 G120C 变频器故障诊断专家，服务对象是现场电气工程师。
你会收到用户的问题，以及从报警代码库中检索出的相关报警条目。
请严格基于检索到的报警条目作答，不要编造不存在的报警代码。

回答格式：
1. **报警解读**：用户问的报警代码是什么含义（如果没有匹配的代码，直接说明"知识库中未找到该代码"）
2. **可能原因**：列出 2~4 条最常见的成因（结合变频器原理和现场经验）
3. **处理步骤**：按优先级给出排查步骤，能落地的动作
4. **注意事项**：安全提醒或易踩的坑

用简洁的工程师语言，不要客套话。"""


class RagEngine:
    """把 BGE 模型、ChromaDB、DeepSeek 客户端打包成一个对象，只加载一次。"""

    def __init__(self):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("环境变量 DEEPSEEK_API_KEY 未设置")

        print(f"[rag] 加载向量模型 {EMBED_MODEL}")
        self.model = SentenceTransformer(EMBED_MODEL)

        print(f"[rag] 连接 ChromaDB {CHROMA_DIR}")
        self.chroma = chromadb.PersistentClient(path=CHROMA_DIR)
        self.collection = self.chroma.get_collection(COLLECTION_NAME)

        print(f"[rag] 连接 DeepSeek（model={DEEPSEEK_MODEL}）")
        self.llm = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

        print(f"[rag] 就绪，知识库 {self.collection.count()} 条")

    def _extract_codes(self, query):
        return [int(n) for n in re.findall(r"\d{3,5}", query)]

    def _search(self, query):
        """混合检索：数字精确匹配优先，语义检索补充。"""
        hits = []
        seen = set()

        for code in self._extract_codes(query):
            exact = self.collection.get(ids=[str(code)])
            if exact["ids"]:
                meta = exact["metadatas"][0]
                hits.append({
                    "code": meta["code"], "text": meta["text"],
                    "severity": meta["severity"],
                    "similarity": 1.0, "source": "精确",
                })
                seen.add(meta["code"])

        q_vec = self.model.encode(query, normalize_embeddings=True)
        sem = self.collection.query(
            query_embeddings=[q_vec.tolist()],
            n_results=TOP_K,
        )
        for meta, dist in zip(sem["metadatas"][0], sem["distances"][0]):
            if meta["code"] in seen:
                continue
            hits.append({
                "code": meta["code"], "text": meta["text"],
                "severity": meta["severity"],
                "similarity": 1 - dist, "source": "语义",
            })
            seen.add(meta["code"])

        return hits[:TOP_K]

    def _build_context(self, hits):
        lines = []
        for h in hits:
            lines.append(
                f"- [{h['code']}] {h['text']}"
                f"（级别：{h['severity']}，相似度：{h['similarity']:.2f}）"
            )
        return "\n".join(lines)

    def _call_llm(self, question, hits):
        context = self._build_context(hits)
        user_prompt = (
            f"用户问题：{question}\n\n"
            f"检索到的报警条目：\n{context}\n\n"
            f"请按系统提示的格式作答。"
        )
        resp = self.llm.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            stream=False,
        )
        return resp.choices[0].message.content

    def ask(self, question):
        """一次完整问答：检索 → 生成。"""
        hits = self._search(question)
        answer = self._call_llm(question, hits)
        return {"question": question, "hits": hits, "answer": answer}
