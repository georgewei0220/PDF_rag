import os
import voyageai
import chromadb
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))

chroma_client = chromadb.PersistentClient(path=os.path.join(os.path.dirname(__file__), "chroma_db"))
collection = chroma_client.get_or_create_collection(name="morning_reports")

# 這裡換成你想問的問題
query = "Broadcom in AI supply chain status"

# 混合搜尋用：問題裡的關鍵實體字（公司名等），只保留內文有出現這個字的 chunk 再做語意排序。
# 不需要關鍵字過濾（純語意搜尋）的話，把這行設成 None 就好。
keyword = "Broadcom"

# 把問題轉成向量（注意 input_type 是 query，不是 document）
query_embedding = client.embed([query], model="voyage-3", input_type="query").embeddings[0]

query_kwargs = dict(query_embeddings=[query_embedding], n_results=3)
if keyword:
    # 有關鍵字篩選時，候選集合通常已經很小，乾脆多撈一點全部看過，
    # 不要只信任向量排序的前3名（敘述型內容常常因為提到多家公司而被排到後面）。
    query_kwargs["n_results"] = 10
    query_kwargs["where_document"] = {"$contains": keyword}

results = collection.query(**query_kwargs)

print(f"問題：{query}")
if keyword:
    print(f"（已篩選內文包含關鍵字：{keyword}）")
print()

if not results["documents"][0]:
    print(f"沒有找到內文包含「{keyword}」的 chunk，改用純語意搜尋試試看（把 keyword 設成 None）")
else:
    print(f"=== 最相關的 {len(results['documents'][0])} 筆結果 ===\n")
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    )):
        print(f"【第{i+1}名】來源：{meta['source_file']} 第{meta['page_number']}頁  (相似度距離: {dist:.4f})")
        print(doc)
        print("---")
