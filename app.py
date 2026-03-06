import streamlit as st
import requests
import time
import re
import io
import os
import base64
import json
import zipfile

# ── Page Config ──
st.set_page_config(
    page_title="美國專利工具箱",
    page_icon="🧰",
    layout="centered",
)

# ── Custom CSS ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');

.stApp { font-family: 'Noto Sans TC', sans-serif; }

.hero { text-align: center; padding: 1.5rem 0 0.8rem; }
.hero h1 {
    font-size: 2rem; font-weight: 700;
    background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
}
.hero p { color: #6b7280; font-size: 0.95rem; }

.stats-row { display: flex; gap: 1rem; margin: 1rem 0; }
.stat-card {
    flex: 1; background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 12px; padding: 1rem 1.2rem; text-align: center;
}
.stat-card .num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.8rem; font-weight: 700; color: #0f3460;
}
.stat-card .label { font-size: 0.8rem; color: #94a3b8; margin-top: 0.2rem; }

.result-item {
    display: flex; align-items: center; padding: 0.6rem 1rem;
    border-radius: 8px; margin-bottom: 0.4rem;
    font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
}
.result-ok { background: #f0fdf4; border-left: 3px solid #22c55e; color: #166534; }
.result-fail { background: #fef2f2; border-left: 3px solid #ef4444; color: #991b1b; }

.step-badge {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 50%;
    background: #0f3460; color: white; font-weight: 700; font-size: 0.85rem;
    margin-right: 0.5rem;
}
.step-header {
    display: flex; align-items: center; font-size: 1.15rem;
    font-weight: 600; color: #1a1a2e; margin: 1.5rem 0 0.8rem;
}

.footer {
    text-align: center; color: #94a3b8; font-size: 0.75rem;
    margin-top: 3rem; padding-bottom: 2rem;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════
# Shared Utility Functions
# ══════════════════════════════════════════════

def get_api_key() -> str | None:
    """Read API key from Secrets or env var."""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", None)
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", None)


def pdf_to_base64_pages(pdf_bytes: bytes, only_pto892: bool = True) -> list[str]:
    """Convert PDF pages to base64-encoded PNG images for Vision OCR."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pto892_page_indices = []
    if only_pto892:
        for i, page in enumerate(doc):
            text = page.get_text().upper()
            if any(kw in text for kw in [
                "NOTICE OF REFERENCES CITED", "PTO-892", "PTO 892",
                "U.S. PATENT DOCUMENTS", "FOREIGN PATENT DOCUMENTS",
                "NON-PATENT DOCUMENTS", "REFERENCES CITED"
            ]):
                pto892_page_indices.append(i)
    if not pto892_page_indices:
        pto892_page_indices = list(range(len(doc)))
    pages_b64 = []
    for i in pto892_page_indices:
        page = doc[i]
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        pages_b64.append(base64.b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return pages_b64


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Try to extract embedded text from PDF."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_text = ""
    for page in doc:
        all_text += page.get_text() + "\n"
    doc.close()
    return all_text.strip()


def has_meaningful_text(text: str) -> bool:
    if not text or len(text.strip()) < 50:
        return False
    keywords = ["892", "references cited", "notice of references",
                "U.S. PATENT DOCUMENTS", "PTO-892", "Patent Number",
                "Document Number", "NOTICE OF REFERENCES CITED"]
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def has_pto892_us_format(text: str) -> bool:
    return bool(re.search(r'US-[A-Z]{0,2}[\d,/\s]+-.', text, re.IGNORECASE))


def extract_patents_by_regex(text: str) -> list[str]:
    pattern = r'US-((?:[A-Z]{0,2})[\d,\s/]+)-[A-Z]\d?'
    matches = re.findall(pattern, text.upper())
    results = []
    for match in matches:
        cleaned = match.replace(',', '').replace(' ', '').replace('/', '')
        if re.match(r'^(D|RE|PP|H)?\d{4,12}$', cleaned):
            results.append(cleaned)
    return results


def _filter_pto892_only(text: str) -> str:
    text_upper = text.upper()
    pto892_starts = []
    for keyword in ["NOTICE OF REFERENCES CITED", "PTO-892", "PTO 892"]:
        for m in re.finditer(re.escape(keyword), text_upper):
            pto892_starts.append(m.start())
    if not pto892_starts:
        return text
    ids_starts = []
    for keyword in ["INFORMATION DISCLOSURE STATEMENT", "PTO/SB/08", "PTO-1449"]:
        for m in re.finditer(re.escape(keyword), text_upper):
            ids_starts.append(m.start())
    sections = []
    for start in sorted(pto892_starts):
        end = len(text)
        for ids_start in ids_starts:
            if ids_start > start:
                end = min(end, ids_start)
                break
        sections.append(text[start:end])
    return "\n".join(sections) if sections else text


VISION_EXTRACTION_PROMPT = """You are a patent document parser with OCR capability. Look at these pages from a USPTO Office Action PDF.

Extract ALL U.S. patent numbers from the PTO-892 (Notice of References Cited) form ONLY.

In PTO-892, each U.S. patent number is written in the format: US-XXXXXXX-YY
where XXXXXXX is the patent number (between the two dashes) and YY is the kind code.

YOUR TASK: For each entry, extract ONLY the middle part (between "US-" and the second "-").

EXAMPLES of correct extraction:
- "US-D1,039,987-S" → extract "D1039987" (Design patent, KEEP the letter D)
- "US-D1,015,895-S" → extract "D1015895" (Design patent)
- "US-7,654,321-B2" → extract "7654321" (Utility patent, pure digits)
- "US-20220242717-A1" → extract "20220242717" (Published application, 11 digits)
- "US-20190046781-A1" → extract "20190046781" (Published application, note the double 0)
- "US-RE45,678-E" → extract "RE45678" (Reissue, KEEP the letters RE)
- "US-PP12,345-P3" → extract "PP12345" (Plant patent, KEEP the letters PP)

CRITICAL RULES:
1. ONLY extract from PTO-892, NOT from IDS (PTO/SB/08).
2. The letter "D" in design patents is NOT the digit "9". Keep it as "D".
3. Remove commas and spaces from the number, but KEEP prefix letters (D, RE, PP, H).
4. Handle multi-page PTO-892 (Page 1 of 2, etc.).

5. DIGIT COUNT VERIFICATION — this is extremely important:
   - Published application numbers (kind code A1) MUST have exactly 11 digits (e.g. 20220242717). They always start with "20" followed by 9 more digits. If you get 10 or fewer digits, you have DROPPED a digit — go back and re-read.
   - Utility patent numbers have 5 to 8 digits.
   - Design patent numbers have "D" + 5 to 7 digits.
   After extracting each number, COUNT the digits and verify they match the expected length.

6. NEVER DROP OR MERGE DIGITS:
   - "00" is two zeros, not one. "004" is three characters, not "04".
   - "11" is two ones, not one. Read every single digit individually.
   - Do NOT skip any digit, even if consecutive digits look similar.
   - Read the number character by character from left to right.

7. READ EACH DIGIT VERY CAREFULLY. Patent numbers must be exact — a single wrong digit means a completely different patent. Pay close attention to these commonly confused digit pairs:
   - "6" vs "8": 6 is open at the top, 8 has both top and bottom loops closed
   - "6" vs "9": 6 has the loop at the BOTTOM, 9 has the loop at the TOP — they are mirror images
   - "6" vs "0": 6 has a tail/stroke entering from the top, 0 is a smooth oval
   - "6" vs "5": 6 has a round bottom loop, 5 has a flat top and curved bottom
   - "8" vs "0": 8 has a pinched middle, 0 does not
   - "1" vs "7": 7 has a horizontal stroke at the top
   - "3" vs "8": 3 is open on the left side, 8 is fully closed
   When in doubt, look at the overall shape very carefully before deciding.

Return ONLY a JSON array of strings. No explanation, no markdown, no code blocks.
Example: ["1078112","20220242717","20190046781","D707355","D794165","6893000"]
If no PTO-892 is found, return: []"""


def call_claude_vision(pages_b64: list[str], api_key: str) -> list[str]:
    content = []
    for b64 in pages_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
    content.append({"type": "text", "text": VISION_EXTRACTION_PROMPT})
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": content}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return _parse_patent_json(resp.json()["content"][0]["text"])


def _normalize_patent_number(raw: str) -> str | None:
    s = raw.strip().upper()
    s = re.sub(r'^US[-\s]*', '', s)
    s = re.sub(r'[-\s]*(S|B\d?|A\d?|P\d?|E|H)\s*$', '', s)
    s = s.replace(',', '').replace(' ', '').replace('/', '').replace('-', '')
    if re.match(r'^(D|RE|PP|H)?\d{4,12}$', s):
        return s
    return None


def _parse_patent_json(text: str) -> list[str]:
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        try:
            patents = json.loads(match.group())
            results = []
            for p in patents:
                normalized = _normalize_patent_number(str(p))
                if normalized:
                    results.append(normalized)
            return results
        except json.JSONDecodeError:
            pass
    return []


def build_pdf_urls(patent_no: str) -> list[tuple[str, str]]:
    """Build download URLs from multiple sources, ordered by priority.
    
    USPTO format examples:
      Utility 7-digit:  /downloadPdf/7654321
      Utility 8-digit:  /downloadPdf/12345678
      Design:           /downloadPdf/D959480
      Plant:            /downloadPdf/PP12345
      Reissue:          /downloadPdf/RE45678
      Pub application:  /downloadPdf/20190123456
    """
    urls = []

    # 1) USPTO official
    if patent_no.isdigit():
        # Utility or published application — pad utility to 7 digits
        if len(patent_no) <= 8:
            padded = patent_no.zfill(7)
        else:
            padded = patent_no  # published application (11 digits)
        urls.append(("USPTO", f"https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{padded}"))
    else:
        # D/RE/PP/H prefix patents — use as-is
        urls.append(("USPTO", f"https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{patent_no}"))

    # 2) Google Patents — always prefix with US
    if patent_no.startswith(("D", "RE", "PP", "H")):
        urls.append(("Google Patents", f"https://patents.google.com/patent/US{patent_no}/en"))
    else:
        urls.append(("Google Patents", f"https://patents.google.com/patent/US{patent_no}/en"))

    # 3) FreePatentsOnline
    urls.append(("FreePatentsOnline", f"https://www.freepatentsonline.com/{patent_no}.pdf"))

    # 4) Pat2PDF
    urls.append(("Pat2PDF", f"http://www.pat2pdf.org/pat2pdf/foo.pl?number={patent_no}"))

    return urls


def download_patent_pdf(patent_no: str, timeout: int = 30) -> tuple[bool, bytes | str]:
    """Attempt to download a patent PDF, falling back through multiple sources."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,*/*",
    }
    urls = build_pdf_urls(patent_no)
    errors = []
    for source_name, url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                ct = r.headers.get("Content-Type", "")
                if "pdf" in ct.lower() or r.content[:5] == b'%PDF-':
                    return True, r.content
                else:
                    errors.append(f"{source_name}: not PDF")
            else:
                errors.append(f"{source_name}: HTTP {r.status_code}")
        except requests.exceptions.Timeout:
            errors.append(f"{source_name}: timeout")
        except requests.exceptions.ConnectionError:
            errors.append(f"{source_name}: connection failed")
        except Exception as e:
            errors.append(f"{source_name}: {e}")
    return False, " | ".join(errors)


def pack_all_zip(files: list[tuple[int, str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, pn, content in files:
            filename = f"{idx:02d}-{pn}.pdf"
            zf.writestr(filename, content)
    buf.seek(0)
    return buf.getvalue()


# ══════════════════════════════════════════════
# Session State Initialization
# ══════════════════════════════════════════════

for key, default in [
    ("extracted_patents", None),
    ("extraction_done", False),
    ("edited_patents", None),
    ("edit_confirmed", False),
    ("download_results", None),
    ("zip_data", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════
# Sidebar — Multi-page Navigation
# ══════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🧰 美國專利工具箱")
    st.markdown("---")
    page = st.radio(
        "選擇工具",
        ["📄 OA 專利下載器", "🔧 更多工具（開發中）"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("v2.0 — 側邊欄多工具版")

    # API Key in sidebar (shared across tools)
    secrets_key = get_api_key()
    api_key = secrets_key
    if not secrets_key:
        st.markdown("#### 🔑 API Key")
        manual_key = st.text_input(
            "Anthropic API Key", type="password", placeholder="sk-ant-...",
            help="Claude Vision OCR 所需。可在 console.anthropic.com 取得。",
            key="sidebar_api_key",
        )
        api_key = manual_key if manual_key else None
    else:
        api_key = secrets_key


# ══════════════════════════════════════════════
# Page: OA Patent Downloader
# ══════════════════════════════════════════════

if page == "📄 OA 專利下載器":

    st.markdown("""
    <div class="hero">
        <h1>📄 美國專利OA檢索報告中的美國專利下載工具</h1>
        <p>上傳美國專利OA → 自動擷取檢索報告中的美國專利清單 → 批次下載清單中的美國專利PDF</p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 使用說明", expanded=False):
        st.markdown("""
        **功能流程：**
        1. 上傳 USPTO Office Action PDF 檔案
        2. 程式自動辨識 Notice of References Cited（PTO-892）表格
        3. 擷取所有美國專利號碼（排除 IDS 表格資料）
        4. 可手動修正擷取結果（新增、刪除、修改號碼）
        5. 一鍵批次下載所有引用專利的 PDF

        **支援的 PDF 類型：**
        - 含文字層的 PDF（Regex 直接擷取，免 API）
        - 純掃描圖像 PDF（Claude Vision OCR）
        - 多頁 PTO-892 表格（Page 1 of 2、Page 2 of 2…）

        **下載來源（自動回退）：**
        1. USPTO 官方（優先）→ 2. Google Patents → 3. FreePatentsOnline → 4. Pat2PDF

        **API Key 設定方式：**
        - 方法 A：在 Streamlit Cloud Secrets 加入 `ANTHROPIC_API_KEY = "sk-ant-..."`（推薦）
        - 方法 B：在左側邊欄手動輸入
        """)

    # ── Step 1: Upload ──
    st.markdown('<div class="step-header"><span class="step-badge">1</span> 上傳美國專利OA的PDF檔</div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload Office Action PDF", type=["pdf"],
        help="上傳包含 PTO-892（Notice of References Cited）的 USPTO Office Action。",
        label_visibility="collapsed",
    )

    # ── Step 2: Extract ──
    if uploaded_file is not None:
        st.markdown('<div class="step-header"><span class="step-badge">2</span> 擷取檢索報告中的美國專利清單</div>', unsafe_allow_html=True)

        if st.button("🔍 擷取美國專利號碼清單", type="primary", use_container_width=True, disabled=not api_key):
            if not api_key:
                st.error("請先在左側邊欄輸入 Anthropic API Key。")
            else:
                pdf_bytes = uploaded_file.getvalue()
                with st.spinner("PDF 分析中…"):
                    try:
                        text_content = extract_text_from_pdf(pdf_bytes)
                        method = ""
                        patents = []

                        if has_meaningful_text(text_content) and has_pto892_us_format(text_content):
                            st.info("📝 偵測到文字層，以 regex 直接擷取中…")
                            method = "Regex 文字擷取（免 API）"
                            pto892_text = _filter_pto892_only(text_content)
                            patents = extract_patents_by_regex(pto892_text)

                        if not patents:
                            st.info("🖼️ 使用 Claude Vision OCR 辨識中…")
                            method = "Claude Vision OCR"
                            pages_b64 = pdf_to_base64_pages(pdf_bytes)
                            patents = call_claude_vision(pages_b64, api_key)

                        # deduplicate
                        seen = set()
                        unique = []
                        for p in patents:
                            if p not in seen:
                                seen.add(p)
                                unique.append(p)

                        st.session_state.extracted_patents = unique
                        st.session_state.extraction_done = True
                        st.session_state.edited_patents = None
                        st.session_state.edit_confirmed = False
                        st.session_state.download_results = None
                        st.session_state.zip_data = None

                        if unique:
                            st.success(f"✅ 成功擷取 {len(unique)} 件美國專利（{method}）")
                        else:
                            st.warning("未在 PTO-892 中找到美國專利號碼，請確認上傳的 PDF 包含 Notice of References Cited 表格。")

                    except requests.exceptions.HTTPError as e:
                        st.error(f"Claude API error: {e}")
                    except Exception as e:
                        st.error(f"Error: {e}")

        # ── Show extracted list + editable area ──
        if st.session_state.extraction_done and st.session_state.extracted_patents:
            patents_source = st.session_state.extracted_patents

            st.markdown(f"""
            <div class="stats-row">
                <div class="stat-card">
                    <div class="num">{len(patents_source)}</div>
                    <div class="label">擷取到的美國專利數</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Step 2.5: Editable Patent List ──
            st.markdown('<div class="step-header"><span class="step-badge">✏️</span> 確認或修改專利號碼清單</div>', unsafe_allow_html=True)

            st.caption("您可以在下方文字框中修改專利號碼：每行一個號碼。可新增、刪除或修正 OCR 辨識錯誤的號碼。")

            # Prepare default text for the editor
            if st.session_state.edited_patents is not None and st.session_state.edit_confirmed:
                default_text = "\n".join(st.session_state.edited_patents)
            else:
                default_text = "\n".join(patents_source)

            edited_text = st.text_area(
                "專利號碼清單（每行一個）",
                value=default_text,
                height=max(150, len(patents_source) * 28),
                key="patent_editor",
                label_visibility="collapsed",
            )

            # Parse edited text
            edited_list = []
            for line in edited_text.strip().split("\n"):
                cleaned = line.strip().upper()
                cleaned = re.sub(r'^US[-\s]*', '', cleaned)
                cleaned = cleaned.replace(',', '').replace(' ', '').replace('/', '').replace('-', '')
                # Remove trailing kind codes
                cleaned = re.sub(r'(S|B\d?|A\d?|P\d?|E|H)\s*$', '', cleaned)
                if cleaned and re.match(r'^(D|RE|PP|H)?\d{4,12}$', cleaned):
                    edited_list.append(cleaned)

            # Show diff if changes were made
            if edited_list != patents_source:
                added = set(edited_list) - set(patents_source)
                removed = set(patents_source) - set(edited_list)
                changes = []
                if added:
                    changes.append(f"新增 {len(added)} 件")
                if removed:
                    changes.append(f"刪除 {len(removed)} 件")
                modified_count = len(edited_list) - len(added) - (len(patents_source) - len(removed))
                if len(edited_list) != len(patents_source) or edited_list != patents_source:
                    st.info(f"📝 清單已修改：共 {len(edited_list)} 件專利" + (f"（{', '.join(changes)}）" if changes else ""))

            if st.button("✅ 確認清單，進入下載步驟", type="primary", use_container_width=True):
                st.session_state.edited_patents = edited_list
                st.session_state.edit_confirmed = True
                st.session_state.download_results = None
                st.session_state.zip_data = None
                st.rerun()

            # ── Step 3: Download ──
            if st.session_state.edit_confirmed and st.session_state.edited_patents:
                final_patents = st.session_state.edited_patents

                st.markdown('<div class="step-header"><span class="step-badge">3</span> 下載專利PDF檔</div>', unsafe_allow_html=True)

                st.markdown(f"即將下載 **{len(final_patents)}** 件美國專利 PDF：")

                col1, col2 = st.columns(2)
                with col1:
                    delay = st.slider("下載間隔（秒）", 0.5, 5.0, 1.0, 0.5)
                with col2:
                    timeout = st.slider("逾時時間（秒）", 10, 60, 30, 5)

                if st.button("🚀 下載號碼清單中的美國專利", type="primary", use_container_width=True):
                    success_files = []
                    total_fail = 0
                    fail_list = []

                    prog = st.progress(0, text="準備下載中…")
                    status = st.container()

                    for i, pn in enumerate(final_patents):
                        seq = i + 1
                        prog.progress(seq / len(final_patents), text=f"下載中 {seq}/{len(final_patents)}: {pn}")
                        ok, result = download_patent_pdf(pn, timeout=timeout)

                        if ok:
                            success_files.append((seq, pn, result))
                            kb = len(result) / 1024
                            status.markdown(f'<div class="result-item result-ok">✅ {seq:02d}-{pn} — 成功 ({kb:.0f} KB)</div>', unsafe_allow_html=True)
                        else:
                            total_fail += 1
                            fail_list.append((pn, result))
                            status.markdown(f'<div class="result-item result-fail">❌ {seq:02d}-{pn} — {result}</div>', unsafe_allow_html=True)

                        if i < len(final_patents) - 1:
                            time.sleep(delay)

                    prog.progress(1.0, text="下載完成！")

                    zip_data = pack_all_zip(success_files) if success_files else None
                    st.session_state.download_results = {
                        "total_success": len(success_files),
                        "total_fail": total_fail,
                        "fail_list": fail_list,
                        "total": len(final_patents),
                    }
                    st.session_state.zip_data = zip_data

                # ── Show download results ──
                if st.session_state.download_results and st.session_state.zip_data is not None:
                    dr = st.session_state.download_results

                    st.markdown(f"""
                    <div class="stats-row">
                        <div class="stat-card"><div class="num" style="color:#22c55e">{dr['total_success']}</div><div class="label">成功</div></div>
                        <div class="stat-card"><div class="num" style="color:#ef4444">{dr['total_fail']}</div><div class="label">失敗</div></div>
                        <div class="stat-card"><div class="num">{dr['total']}</div><div class="label">總計</div></div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.download_button(
                        label=f"📦 一鍵下載所有美國專利（{dr['total_success']} PDFs, ZIP）",
                        data=st.session_state.zip_data,
                        file_name="PTO892_patents.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )

                    if dr['fail_list']:
                        with st.expander(f"查看下載失敗清單（{dr['total_fail']} 件）"):
                            for pn, reason in dr['fail_list']:
                                st.text(f"{pn}: {reason}")

        elif st.session_state.extraction_done and not st.session_state.extracted_patents:
            st.info("未擷取到任何專利號碼，請確認上傳的 PDF 中包含 PTO-892 表格。")


# ══════════════════════════════════════════════
# Page: More Tools (placeholder)
# ══════════════════════════════════════════════

elif page == "🔧 更多工具（開發中）":
    st.markdown("""
    <div class="hero">
        <h1>🔧 更多工具</h1>
        <p>此區塊預留給未來新增的專利工具</p>
    </div>
    """, unsafe_allow_html=True)

    st.info("目前尚無其他工具。您可以在此頁面未來加入更多功能，例如：")
    st.markdown("""
    - **IDS 專利下載器** — 擷取 IDS（PTO/SB/08）中的專利號碼並批次下載
    - **專利家族查詢** — 輸入專利號碼，查詢其專利家族成員
    - **OA 回覆期限計算器** — 根據 OA 發文日計算回覆截止日
    - **批次專利號碼下載** — 直接輸入專利號碼清單，批次下載 PDF
    """)


# ── Footer ──
st.markdown("""
<div class="footer">
    Sources: USPTO · Google Patents · FreePatentsOnline · Pat2PDF<br>
    For personal research use only. Please comply with each source's terms of service.
</div>
""", unsafe_allow_html=True)
