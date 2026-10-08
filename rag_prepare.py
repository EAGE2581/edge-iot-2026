"""RAG 步骤 1：把 alarm_codes.yaml 的报警向量化，存入 ChromaDB。"""
import os
import sys

import yaml
import chromadb
from sentence_transformers import SentenceTransformer

ALARM_PATH = "alarm_codes.yaml"
CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "alarm_codes"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def load_alarms(path):
    """读 YAML，展平成列表，按 code 排序。"""
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    raw = doc.get("alarms", {})
    items = []
    for code, meta in raw.items():
        items.append({
            "code": int(code),
            "text": meta.get("text", ""),
            "severity": meta.get("severity", "warning"),
            "category": meta.get("category", "warn"),
        })
    items.sort(key=lambda x: x["code"])
    return items


def build_document(item):
    """把一条报警拼成一段自然语言，喂给 BGE。"""
    return (
        f"报警代码 {item['code']}：{item['text']}。"
        f"级别：{item['severity']}，类型：{item['category']}。"
    )


def main():
    if not os.path.exists(ALARM_PATH):
        print(f"[!] 找不到 {ALARM_PATH}")
        sys.exit(1)

    print(f"[*] 加载报警字典 {ALARM_PATH}")
    alarms = load_alarms(ALARM_PATH)
    print(f"[*] 共 {len(alarms)} 条")

    print(f"[*] 加载向量模型 {MODEL_NAME}（首次运行会下载约 100MB）")
    model = SentenceTransformer(MODEL_NAME)

    print("[*] 正在编码（向量化）...")
    docs = [build_document(a) for a in alarms]
    embeddings = model.encode(
        docs,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    print(f"[*] 连接 ChromaDB 本地库 {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    existing = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing:
        print(f"[*] 已存在 collection {COLLECTION_NAME}，删除后重建")
        client.delete_collection(COLLECTION_NAME)

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [str(a["code"]) for a in alarms]
    metadatas = [
        {"code": a["code"], "text": a["text"],
         "severity": a["severity"], "category": a["category"]}
        for a in alarms
    ]

    collection.add(
        ids=ids,
        documents=docs,
        embeddings=embeddings.tolist(),
        metadatas=metadatas,
    )

    print(f"[✓] 已写入 {collection.count()} 条到 {CHROMA_DIR}/{COLLECTION_NAME}")


if __name__ == "__main__":
    main()
