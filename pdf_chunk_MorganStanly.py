"""
PDF chunking 腳本 v2
用法：python chunk_pdf.py <pdf路徑>

v1 的問題：用文字規則（數字開頭、冒號結尾）猜標題，猜不準：
- 條列項目「1) 2) 3)」被誤判成三個獨立章節，切得太碎
- 後半段財務報表頁幾乎沒有符合規則的標題文字，整段 33000+ 字擠成一個 chunk

v2 改法：不猜文字規則，直接讀 PDF 裡每一行文字實際的字級（font size）。
這份報告的字級很規律：
    21pt ≈ 章節大標題（例如 "GUC: Estimate revisions summary"）
    11~15pt ≈ 小標題（例如 "TPU v10 is the project that can involve many"）
    <11pt ≈ 內文 / 表格數字
用字級當切點比猜文字規則準，因為報告排版本身就是用字級在做視覺分層。

另外加一條規則：只要一行文字是「Exhibit 數字」開頭，不管字級多小，
都強制切成新的 chunk，因為每個 Exhibit 是一個獨立的表格資訊單元，
混進前後文字段落會稀釋語意。
"""

import pdfplumber
import re
import json
import sys
from pathlib import Path
from collections import defaultdict

DISCLOSURE_MARKERS = [
    "Disclosure Section",
    "STOCK RATINGS",
    "Analyst Certification",
    "Important Regulatory Disclosures",
    "INDUSTRY COVERAGE",
]

EXHIBIT_RE = re.compile(r"^Exhibit\s+\d+")

# 「歷史報告清單」型的 chunk（例如 Key Featured Reports 頁）不含實質分析內容，
# 只是一堆過去報告標題+日期的索引，塞進向量DB只會稀釋搜尋品質，要濾掉。
# 判斷方式：內文裡出現「(日 月 年)」格式的報告日期引用次數，達到門檻就視為索引清單。
REPORT_CITATION_RE = re.compile(r"\([0-9]{1,2}\s+[A-Za-z]{3,9}\s+20[0-9]{2}\)")
REPORT_CITATION_MIN_COUNT = 3


def is_report_index_chunk(content):
    return len(REPORT_CITATION_RE.findall(content)) >= REPORT_CITATION_MIN_COUNT

# 字級門檻，可依實際 PDF 調整
LEVEL1_MIN_SIZE = 18   # 章節大標題
LEVEL2_MIN_SIZE = 11   # 小標題（body 內文大約 8~9pt）
DISCLOSURE_MIN_SIZE = 12  # 免責聲明頁標題實測是16pt，比正文章節標題(21pt)小，門檻要分開設

# 每頁角落都有的品牌 logo，字級高達42pt但不是真正的章節標題，
# 不濾掉的話會一直洗掉 current_level1，導致 context 前綴全部變成"M"
DECORATIVE_LINES = {"M"}


def extract_lines_with_font(pdf_path):
    """
    回傳 [(page_num, line_text, max_font_size), ...]

    處理左右兩欄排版的邏輯（結果證明第一版寫錯了，這裡是修正版）：
    第一步：先用 'top' 座標把同一頁的字組成一行一行（正常做法）。
    第二步：每一行整行判斷屬於左欄還右欄——用「這一行最左邊字元的
    x座標」來判斷，而不是逐字元判斷。
        （第一版的bug：逐字元判斷會把橫跨全頁寬的一般段落或表格橫列，
        從中線切成兩半，導致同一行的文字被拆到不同欄位、順序整個亂掉。
        修正後改成「整行只看行首位置」，橫跨全頁的行照樣完整保留在
        它開始的那一欄，不會被腰斬。）
    第三步：左欄的所有行按上下順序讀完，才接著讀右欄的所有行。
        這樣像封面（左邊標題+摘要、右邊分析師聯絡資訊）或 Risk Reward
        頁（左邊圖表、右邊投資論點條列）這種真正的雙欄內容，
        才不會被交錯讀亂；一般單欄頁面因為右欄幾乎沒東西，
        效果等同於原本的讀法，不受影響。
    """
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            mid_x = page.width / 2
            by_top = defaultdict(list)
            for c in page.chars:
                by_top[round(c["top"])].append(c)

            left_lines = []
            right_lines = []
            for top in sorted(by_top.keys()):
                chars = sorted(by_top[top], key=lambda c: c["x0"])
                text = "".join(c["text"] for c in chars).strip()
                if not text:
                    continue
                max_size = max(c["size"] for c in chars)
                line_start_x = chars[0]["x0"]
                entry = (top, text, max_size)
                if line_start_x < mid_x:
                    left_lines.append(entry)
                else:
                    right_lines.append(entry)

            for _, text, max_size in left_lines:
                lines.append((page_num, text, max_size))
            for _, text, max_size in right_lines:
                lines.append((page_num, text, max_size))
    return lines


def find_disclosure_start_page(lines):
    """
    免責聲明頁的標題（像 "Disclosure Section"）字級也是 21pt 的大標題，
    跟正文交叉引用句子裡出現的同樣文字（字級只有 8~9pt）不一樣，
    所以順便用字級再確認一次，避免像 v1 那樣誤判第1頁。
    """
    for page_num, text, size in lines:
        if size >= DISCLOSURE_MIN_SIZE:
            for marker in DISCLOSURE_MARKERS:
                if text == marker or text.startswith(marker):
                    return page_num
    return None


def classify_line(text, size):
    if text in DECORATIVE_LINES:
        return "decorative"
    # 純符號行（例如條列符號「▪」單獨一行，字級剛好也很大）
    # 不該被當成標題，不然會洗掉正確的章節脈絡。
    # 判斷方式：把文字裡的英數字挑出來看還剩幾個字，
    # 太少（少於3個）代表這行幾乎全是符號，不是真標題。
    alnum_count = sum(1 for ch in text if ch.isalnum())
    if alnum_count < 3:
        return "body"
    if EXHIBIT_RE.match(text):
        return "exhibit"
    if size >= LEVEL1_MIN_SIZE:
        return "level1"
    if size >= LEVEL2_MIN_SIZE:
        return "level2"
    return "body"


def chunk_by_font(lines, cutoff_page):
    chunks = []
    current_level1 = None      # 目前的大章節（21pt）
    current_level2 = None      # 目前的小節標題（11~18pt）
    current_title = "（開頭，無標題）"
    current_start_page = None
    current_lines = []
    last_heading_kind = None   # 追蹤「上一行是不是還在同一個標題裡」，
                                # 用來處理標題本身換行變兩行的狀況
                                # （例如 "Implied chip volume..." / "frequently
                                # discussed..." / "global bottleneck" 其實是
                                # 同一個副標題被排版拆成三行，不是三個新章節）

    def context_label():
        return current_level2 or current_level1

    def flush():
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content and not is_report_index_chunk(content):
                label = context_label()
                prefix = f"[章節: {label}]\n" if label else ""
                chunks.append({
                    "section": current_level1,
                    "subsection": current_level2,
                    "title": current_title,
                    "start_page": current_start_page,
                    "content": prefix + content,
                })

    for page_num, text, size in lines:
        if cutoff_page and page_num >= cutoff_page:
            break

        kind = classify_line(text, size)

        if kind == "decorative":
            continue

        if kind in ("level1", "level2") and kind == last_heading_kind:
            # 跟上一行同等級的標題文字，且中間還沒有任何內文，
            # 判斷是同一個標題被排版拆成多行，接在後面就好，不開新 chunk
            current_title = f"{current_title} {text}"
            if kind == "level1":
                current_level1 = current_title
            else:
                current_level2 = current_title
                current_lines[-1] = current_title if current_lines else current_title
            continue

        if kind == "level1":
            flush()
            current_level1 = text
            current_level2 = None
            current_title = text
            current_start_page = page_num
            current_lines = []
            last_heading_kind = "level1"
        elif kind == "level2":
            flush()
            current_level2 = text
            current_title = text
            current_start_page = page_num
            current_lines = [text]
            last_heading_kind = "level2"
        elif kind == "exhibit":
            flush()
            current_title = text
            current_start_page = page_num
            current_lines = [text]
            last_heading_kind = None
        else:
            if current_start_page is None:
                current_start_page = page_num
            current_lines.append(text)
            last_heading_kind = None

    flush()
    return chunks


def main():
    pdf_path = Path("/Users/weilichuan/Desktop/PDF/外資/260824_ms_AI-supply-chain.pdf")
    lines = extract_lines_with_font(pdf_path)

    cutoff_page = find_disclosure_start_page(lines)
    total_pages = max(p for p, _, _ in lines) if lines else 0
    print(f"總頁數：{total_pages}")
    if cutoff_page:
        print(f"偵測到免責聲明從第 {cutoff_page} 頁開始，之後的頁面會被濾掉")
    else:
        print("沒偵測到免責聲明頁面，全部頁面都會處理（可能要手動檢查）")

    chunks = chunk_by_font(lines, cutoff_page)
    print(f"共產生 {len(chunks)} 個 chunk\n")

    for idx, c in enumerate(chunks):
        preview = c["content"][:70].replace("\n", " ")
        length = len(c["content"])
        print(f"[{idx}] p.{c['start_page']} | {length:5d} 字 | {c['title'][:45]}")
        print(f"     {preview}...")

    out_path = Path("/Users/weilichuan/Desktop/PDF/") / (pdf_path.stem + ".chunks.v2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"\n已存到：{out_path}")


if __name__ == "__main__":
    main()