import os
import voyageai
import chromadb
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))

chroma_client = chromadb.PersistentClient(path=os.path.join(os.path.dirname(__file__), "chroma_db"))
collection = chroma_client.get_or_create_collection(name="morning_reports")

# 這裡換成你想問的問題
query = "外資買超和賣超的股票"

# 把問題轉成向量（注意 input_type 是 query，不是 document）
query_embedding = client.embed([query], model="voyage-3", input_type="query").embeddings[0]

# 去資料庫找最相關的 3 筆
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=3
)

print(f"問題：{query}\n")
print("=== 最相關的 3 筆結果 ===\n")
for i, (doc, meta, dist) in enumerate(zip(
    results["documents"][0],
    results["metadatas"][0],
    results["distances"][0]
)):
    print(f"【第{i+1}名】來源：{meta['source_file']} 第{meta['page_number']}頁  (相似度距離: {dist:.4f})")
    print(doc[:150])
    print("---")