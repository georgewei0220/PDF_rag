import pdfplumber
import os

# 你的 PDF 資料夾路徑
folder = "/Users/weilichuan/Desktop/PDF"

files = [f for f in os.listdir(folder) if f.endswith('.pdf')] 
print(f"資料夾裡共有 {len(files)} 份 PDF")
for fname in files:
    path = os.path.join(folder, fname)
    try:
        with pdfplumber.open(path) as pdf:
           num_pages = len(pdf.pages)
           first_parg_text = pdf.pages[0].extract_text() or ""
           first_page_chars = len(first_parg_text)
           print(f"{fname}")
           print(f"  頁數: {num_pages}　第一頁字數: {first_page_chars}") 

    except Exception as e:
        print(f"無法開啟 {fname}，錯誤訊息: {e}")
        continue        