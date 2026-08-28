import json
import sys
import time
import os
from pathlib import Path

import voyageai
import chromadb
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))

# 用法: python import_chunks_to_db.py /path/to/xxx.chunks.v2.json


#chunk_path = Path(sys.argv[1])
chunk_path = Path("/Users/weilichuan/Desktop/PDF/260824_ms_AI-supply-chain.chunks.v2.json")
source_file = chunk_path.stem.replace(".chunks.v2", "")

with open(chunk_path, "r", encoding="utf-8") as f:
    chunks = json.load(f)

print(f"共讀到 {len(chunks)} 個 chunk，開始轉向量...")

texts = [c["content"] for c in chunks]

batch_size = 8
all_embeddings = []
for i in range(0, len(texts), batch_size):
    batch = texts[i:i + batch_size]

    for attempt in range(5):
        try:
            result = client.embed(batch, model="voyage-3", input_type="document")
            all_embeddings.extend(result.embeddings)
            print(f"已完成 {min(i + batch_size, len(texts))}/{len(texts)}")
            break
        except Exception as e:
            wait = 25
            print(f"⚠️ 失敗（第{attempt+1}次嘗試），等待 {wait} 秒後重試... 錯誤: {e}")
            time.sleep(wait)
    else:
        raise RuntimeError(f"批次 {i} 重試5次仍失敗，請檢查API key或帳號狀態")

    time.sleep(60)

chroma_client = chromadb.PersistentClient(path=os.path.join(os.path.dirname(__file__), "chroma_db"))
collection = chroma_client.get_or_create_collection(name="morning_reports")

ids = [f"{source_file}_p{c['start_page']}_{idx}" for idx, c in enumerate(chunks)]
metadatas = [
    {"source_file": source_file, "page_number": c["start_page"], "title": c["title"]}
    for c in chunks
]

collection.add(
    ids=ids,
    embeddings=all_embeddings,
    documents=texts,
    metadatas=metadatas,
)

print(f"\n已存入 ChromaDB，總筆數: {collection.count()}")
