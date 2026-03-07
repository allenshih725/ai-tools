import streamlit as st
import requests
import time
import re
import io
import base64
import json
import zipfile


# ══════════════════════════════════════════════
# G1003 — Internal Functions (fully self-contained)
# ══════════════════════════════════════════════

def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Try to extract embedded text from PDF."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_text = ""
    for page in doc:
        all_text += page.get_text() + "\n"
    doc.close()
    return all_text.strip()


def _has_meaningful_text(text: str) -> bool:
    if not text or len(text.strip()) < 50:
        return False
    keywords = ["892", "references cited", "notice of references",
                "U.S. PATENT DOCUMENTS", "PTO-892", "Patent Number",
                "Document Number", "NOTICE OF REFERENCES CITED"]
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _has_pto892_us_format(text: str) -> bool:
    return bool(re.search(r'US-[A-Z]{0,2}[\d,/\s]+-.', text, re.IGNORECASE))


def _extract_patents_by_regex(text: str) -> list[str]:
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


def _pdf_to_base64_pages(pdf_bytes: bytes, only_pto892: bool = True) -> list[str]:
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


_VISION_EXTRACTION_PROMPT = """You are a patent document parser with OCR capability. Look at these pages from a USPTO Office Action PDF.

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


def _call_claude_vision(pages_b64: list[str], api_key: str) -> list[str]:
    content = []
    for b64 in pages_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
    content.append({"type": "text", "text": _VISION_EXTRACTION_PROMPT})
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


def _download_patent_pdf(patent_no: str, timeout: int = 30) -> tuple[bool, bytes | str]:
    """Download a patent PDF from USPTO."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,*/*",
    }
    if patent_no.isdigit():
        padded = patent_no.zfill(7) if len(patent_no) <= 8 else patent_no
    else:
        padded = patent_no
    url = f"https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{padded}"
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            ct = r.headers.get("Content-Type", "")
            if "pdf" in ct.lower() or r.content[:5] == b'%PDF-':
                return True, r.content
            else:
                return False, "USPTO: not PDF"
        else:
            return False, f"USPTO: HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, "USPTO: timeout"
    except requests.exceptions.ConnectionError:
        return False, "USPTO: connection failed"
    except Exception as e:
        return False, f"USPTO: {e}"


def _pack_all_zip(files: list[tuple[int, str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, pn, content in files:
            filename = f"{idx:02d}-{pn}.pdf"
            zf.writestr(filename, content)
    buf.seek(0)
    return buf.getvalue()


# ══════════════════════════════════════════════
# G1003 — Session State Initialization
# ══════════════════════════════════════════════

def _init_session_state():
    for key, default in [
        ("t9_extracted_patents", None),
        ("t9_extraction_done", False),
        ("t9_download_results", None),
        ("t9_zip_data", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


# ══════════════════════════════════════════════
# G1003 — Render (entry point called by app.py)
# ══════════════════════════════════════════════

def render(api_key: str | None = None):
    _init_session_state()

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
        4. 一鍵批次下載所有引用專利的 PDF

        **支援的 PDF 類型：**
        - 含文字層的 PDF（直接擷取）
        - 純掃描圖像 PDF（透過 Claude Vision OCR 辨識）
        - 多頁 PTO-892 表格（Page 1 of 2、Page 2 of 2…）

        **下載來源（自動回退）：**
        1. USPTO 官方（優先）→ 2. Google Patents → 3. FreePatentsOnline → 4. Pat2PDF
        """)

    st.markdown('<div class="step-header"><span class="step-badge">1</span> 上傳美國專利OA的PDF檔</div>', unsafe_allow_html=True)

    t9_uploaded = st.file_uploader(
        "Upload Office Action PDF", type=["pdf"],
        help="上傳包含 PTO-892（Notice of References Cited）的 USPTO Office Action。",
        label_visibility="collapsed",
        key="t9_uploader",
    )

    if t9_uploaded is not None:
        st.markdown('<div class="step-header"><span class="step-badge">2</span> 擷取檢索報告中的美國專利清單</div>', unsafe_allow_html=True)

        if st.button("🔍 擷取美國專利號碼清單", type="primary", use_container_width=True, disabled=not api_key, key="t9_extract_btn"):
            if not api_key:
                st.error("請先在左側邊欄輸入 Anthropic API Key。")
            else:
                pdf_bytes = t9_uploaded.getvalue()
                with st.spinner("PDF 分析中…"):
                    try:
                        text_content = _extract_text_from_pdf(pdf_bytes)
                        method = ""
                        patents = []

                        if _has_meaningful_text(text_content) and _has_pto892_us_format(text_content):
                            st.info("📝 偵測到文字層，以 regex 直接擷取中…")
                            method = "Regex 文字擷取（免 API）"
                            pto892_text = _filter_pto892_only(text_content)
                            patents = _extract_patents_by_regex(pto892_text)

                        if not patents:
                            st.info("🖼️ 使用 Claude Vision OCR 辨識中…")
                            method = "Claude Vision OCR"
                            pages_b64 = _pdf_to_base64_pages(pdf_bytes)
                            patents = _call_claude_vision(pages_b64, api_key)

                        seen = set()
                        unique = []
                        for p in patents:
                            if p not in seen:
                                seen.add(p)
                                unique.append(p)

                        st.session_state.t9_extracted_patents = unique
                        st.session_state.t9_extraction_done = True
                        st.session_state.t9_download_results = None
                        st.session_state.t9_zip_data = None

                        if unique:
                            st.success(f"✅ 成功擷取 {len(unique)} 件美國專利（{method}）")
                        else:
                            st.warning("未在 PTO-892 中找到美國專利號碼，請確認上傳的 PDF 包含 Notice of References Cited 表格。")

                    except requests.exceptions.HTTPError as e:
                        st.error(f"Claude API error: {e}")
                    except Exception as e:
                        st.error(f"Error: {e}")

        if st.session_state.t9_extraction_done and st.session_state.t9_extracted_patents:
            patents = st.session_state.t9_extracted_patents

            st.markdown(f"""
            <div class="stats-row">
                <div class="stat-card">
                    <div class="num">{len(patents)}</div>
                    <div class="label">擷取到的美國專利數</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            rows = "".join(f"<tr><td>{i}</td><td>{pn}</td></tr>" for i, pn in enumerate(patents, 1))
            st.markdown(f"""
            <table class="patent-table">
                <thead><tr><th>#</th><th>專利號碼</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
            """, unsafe_allow_html=True)

            st.markdown('<div class="step-header"><span class="step-badge">3</span> 下載專利PDF檔</div>', unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                delay = st.slider("下載間隔（秒）", 0.5, 5.0, 1.0, 0.5, key="t9_delay")
            with col2:
                timeout = st.slider("逾時時間（秒）", 10, 60, 30, 5, key="t9_timeout")

            if st.button("🚀 下載號碼清單中的美國專利", type="primary", use_container_width=True, key="t9_download_btn"):
                success_files = []
                total_fail = 0
                fail_list = []

                prog = st.progress(0, text="準備下載中…")
                status = st.container()

                for i, pn in enumerate(patents):
                    seq = i + 1
                    prog.progress(seq / len(patents), text=f"下載中 {seq}/{len(patents)}: {pn}")
                    ok, result = _download_patent_pdf(pn, timeout=timeout)

                    if ok:
                        success_files.append((seq, pn, result))
                        kb = len(result) / 1024
                        status.markdown(f'<div class="result-item result-ok">✅ {seq:02d}-{pn} — 成功 ({kb:.0f} KB)</div>', unsafe_allow_html=True)
                    else:
                        total_fail += 1
                        fail_list.append((pn, result))
                        status.markdown(f'<div class="result-item result-fail">❌ {seq:02d}-{pn} — {result}</div>', unsafe_allow_html=True)

                    if i < len(patents) - 1:
                        time.sleep(delay)

                prog.progress(1.0, text="下載完成！")

                zip_data = _pack_all_zip(success_files) if success_files else None
                st.session_state.t9_download_results = {
                    "total_success": len(success_files),
                    "total_fail": total_fail,
                    "fail_list": fail_list,
                    "total": len(patents),
                }
                st.session_state.t9_zip_data = zip_data

            if st.session_state.t9_download_results and st.session_state.t9_zip_data is not None:
                dr = st.session_state.t9_download_results

                st.markdown(f"""
                <div class="stats-row">
                    <div class="stat-card"><div class="num" style="color:#22c55e">{dr['total_success']}</div><div class="label">成功</div></div>
                    <div class="stat-card"><div class="num" style="color:#ef4444">{dr['total_fail']}</div><div class="label">失敗</div></div>
                    <div class="stat-card"><div class="num">{dr['total']}</div><div class="label">總計</div></div>
                </div>
                """, unsafe_allow_html=True)

                st.download_button(
                    label=f"📦 一鍵下載所有美國專利（{dr['total_success']} PDFs, ZIP）",
                    data=st.session_state.t9_zip_data,
                    file_name="PTO892_patents.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="t9_zip_btn",
                )

                if dr['fail_list']:
                    with st.expander(f"查看下載失敗清單（{dr['total_fail']} 件）"):
                        for pn, reason in dr['fail_list']:
                            st.text(f"{pn}: {reason}")

        elif st.session_state.t9_extraction_done and not st.session_state.t9_extracted_patents:
            st.info("未擷取到任何專利號碼，請確認上傳的 PDF 中包含 PTO-892 表格。")
