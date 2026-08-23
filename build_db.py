import json
import time
import os
import voyageai
import chromadb
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))

# 讀取全部 chunks
with open("/Users/weilichuan/Desktop/chunks_typeA.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

print(f"共讀到 {len(chunks)} 個 chunk，開始轉向量...")

texts = [c["text"] for c in chunks]

# VoyageAI 一次最多處理一定數量，分批送（每批 20 個，保守一點避免超過限制）
# 帳號限制 3 RPM，所以每批之間要等超過 20 秒才安全
batch_size = 20
all_embeddings = []
for i in range(0, len(texts), batch_size):
    batch = texts[i:i+batch_size]

    # 失敗自動重試，最多試 5 次
    for attempt in range(5):
        try:
            result = client.embed(batch, model="voyage-3", input_type="document")
            all_embeddings.extend(result.embeddings)
            print(f"已完成 {min(i+batch_size, len(texts))}/{len(texts)}")
            break
        except Exception as e:
            wait = 25  # 超過 20 秒的安全緩衝
            print(f"⚠️ 失敗（第{attempt+1}次嘗試），等待 {wait} 秒後重試... 錯誤: {e}")
            time.sleep(wait)
    else:
        raise RuntimeError(f"批次 {i} 重試5次仍失敗，請檢查API key或帳號狀態")

    # 每批之間固定等待，避免再次超過 3RPM
    time.sleep(22)



# 建立本機 ChromaDB（存在這個資料夾裡的 chroma_db 子目錄）
chroma_client = chromadb.PersistentClient(path=os.path.join(os.path.dirname(__file__), "chroma_db"))
collection = chroma_client.get_or_create_collection(name="morning_reports")

# 準備存入的資料：id、向量、文字、metadata
ids = [f"{c['source_file']}_p{c['page_number']}" for c in chunks]
metadatas = [{"source_file": c["source_file"], "page_number": c["page_number"]} for c in chunks]

collection.add(
    ids=ids,
    embeddings=all_embeddings,
    documents=texts,
    metadatas=metadatas
)

print(f"\n已存入 ChromaDB，總筆數: {collection.count()}")