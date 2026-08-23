import pdfplumber
import os
import json

folder = "/Users/weilichuan/Desktop/PDF"

# 類型 A：晨報/快訊型，先手動列出（之後可以改成自動判斷）
type_a_files = [
    "投資策略日報-多頭力度趨弱、回檔壓力攀升-20260819.pdf",
    "凱基台股分析20260819-台股破壞8月上漲慣性        短線將回測季線支撐.pdf",
    "20260819_台新台股盤勢分析.pdf",
    "群益早安20260819.pdf",
    "2026.08.19台股_行動快訊.pdf",
    "統一每日晨會報告0819.pdf",
    "凱基期貨晨間解盤20260819.pdf",
]

all_chunks = []
for fname in type_a_files:
    path = os.path.join(folder, fname)
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and len(text)>=20:  # 跳過空白頁
                chunk = {
                    "source_file": fname,
                    "page_number": i + 1,
                    "text": text.strip()
                }
                all_chunks.append(chunk)

print(f"總共產生 {len(all_chunks)} 個 chunk")

# 存成 JSON，之後 embedding 步驟會用到這個檔案
output_path = os.path.join(os.path.expanduser("~/Desktop"), "chunks_typeA.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(all_chunks, f, ensure_ascii=False, indent=2)

print(f"已存到：{output_path}")

# 印出前兩個 chunk 看效果
print("\n=== 範例 chunk ===")
for c in all_chunks[:2]:
    print(json.dumps(c, ensure_ascii=False, indent=2))
    print("---")

