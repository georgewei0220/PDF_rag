import json
import os 
import voyageai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
client = voyageai.Client(api_key=os.getenv("VOYAGEAI_API_KEY"))

with open("/Users/weilichuan/Desktop/chunks_typeA.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

print(f"總共 {len(chunks)} 個 chunk")

test_chunks = chunks[:3]  # 只取前3個 chunk 做測試
texts = [c["text"] for c in test_chunks]

result = client.embed(texts, model="voyage-3" ,input_type="document")
for i, (chunk, embedding) in enumerate(zip(test_chunks, result.embeddings)):
    print(f"\n=== Chunk {i+1}: {chunk['source_file']} 第{chunk['page_number']}頁 ===")
    print(f"原文前50字: {chunk['text'][:50]}...")
    print(f"向量維度: {len(embedding)}")
    print(f"向量前5個數字: {embedding[:5]}")