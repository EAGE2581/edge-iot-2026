"""RAG 步骤 3：检索 + DeepSeek 生成（完整问答）。"""
import os
import re
import sys

import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI

CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "alarm_codes"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
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


def extract_codes(query):
    """从查询里提取 3~5 位的报警代码。"""
    return [int(n) for n in re.findall(r"\d{3,5}", query)]


def search(query, collection, model):
    """混合检索：数字精确 + 语义。"""
    hits = []
    seen = set()

    # 通道 1：精确匹配
    for code in extract_codes(query):
        exact = collection.get(ids=[str(code)])
        if exact["ids"]:
            meta = exact["metadatas"][0]
            hits.append({
                "code": meta["code"],
                "text": meta["text"],
                "severity": meta["severity"],
                "similarity": 1.0,
                "source": "精确",
            })
            seen.add(meta["code"])

    # 通道 2：语义检索
    q_vec = model.encode(query, normalize_embeddings=True)
    sem = collection.query(
        query_embeddings=[q_vec.tolist()],
        n_results=TOP_K,
    )
    for doc, meta, dist in zip(
        sem["documents"][0],
        sem["metadatas"][0],
        sem["distances"][0],
    ):
        if meta["code"] in seen:
            continue
        hits.append({
            "code": meta["code"],
            "text": meta["text"],
            "severity": meta["severity"],
            "similarity": 1 - dist,
            "source": "语义",
        })
        seen.add(meta["code"])

    return hits[:TOP_K]


def build_context(hits):
    """把检索结果拼成一段给 LLM 看的文本。"""
    lines = []
    for h in hits:
        lines.append(f"- [{h['code']}] {h['text']}（级别：{h['severity']}，相似度：{h['similarity']:.2f}）")
    return "\n".join(lines)


def ask_llm(client, question, hits):
    """调 DeepSeek 生成答案。"""
    context = build_context(hits)
    user_prompt = (
        f"用户问题：{question}\n\n"
        f"检索到的报警条目：\n{context}\n\n"
        f"请按系统提示的格式作答。"
    )

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        stream=False,
    )
    return resp.choices[0].message.content


def main():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("[!] 环境变量 DEEPSEEK_API_KEY 未设置")
        print("    请先执行：export DEEPSEEK_API_KEY=\"sk-...\"")
        sys.exit(1)

    print(f"[*] 加载向量模型 {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    print(f"[*] 连接 ChromaDB {CHROMA_DIR}")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = chroma_client.get_collection(COLLECTION_NAME)
    print(f"[*] 知识库共 {collection.count()} 条")

    print(f"[*] 连接 DeepSeek（model={DEEPSEEK_MODEL}）")
    llm = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    print("\n[*] 输入问题（输入 q 退出）\n")
    while True:
        try:
            q = input("问: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q or q.lower() == "q":
            break

        hits = search(q, collection, model)

        print(f"\n[检索到 {len(hits)} 条]")
        for i, h in enumerate(hits, 1):
            print(f"  [{i}] [{h['source']}] {h['code']} {h['text']} ({h['similarity']:.3f})")

        print("\n[DeepSeek 生成中...]\n")
        try:
            answer = ask_llm(llm, q, hits)
            print(answer)
        except Exception as e:
            print(f"[!] LLM 调用失败: {e}")

        print("\n" + "=" * 60 + "\n")

    print("[*] 已退出")


if __name__ == "__main__":
    main()
