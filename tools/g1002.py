import streamlit as st
import requests
import time
import re
import io
import zipfile


# ══════════════════════════════════════════════
# G1002 — Internal Functions (fully self-contained)
# ══════════════════════════════════════════════

def _normalize_patent_number(raw: str) -> str | None:
    s = raw.strip().upper()
    s = re.sub(r'^US[-\s]*', '', s)
    s = re.sub(r'[-\s]*(S|B\d?|A\d?|P\d?|E|H)\s*$', '', s)
    s = s.replace(',', '').replace(' ', '').replace('/', '').replace('-', '')
    if re.match(r'^(D|RE|PP|H)?\d{4,12}$', s):
        return s
    return None


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
# G1002 — Session State Initialization
# ══════════════════════════════════════════════

def _init_session_state():
    for key, default in [
        ("t2_patents_input", ""),
        ("t2_download_results", None),
        ("t2_zip_data", None),
        ("t2_is_downloading", False),
        ("t2_cancel_requested", False),
        ("t2_success_files", []),
        ("t2_fail_list", []),
        ("t2_progress", 0),
        ("t2_current_idx", 0),
        ("t2_dl_delay", 1.0),
        ("t2_dl_timeout", 30),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


# ══════════════════════════════════════════════
# G1002 — Render (entry point called by app.py)
# ══════════════════════════════════════════════

def render(api_key: str | None = None):
    _init_session_state()

    st.markdown("""
    <div class="hero">
        <h1>✍️ 手動輸入專利號來下載PDF</h1>
        <p>直接輸入美國專利號碼清單 → 批次下載PDF</p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 使用說明", expanded=False):
        st.markdown("""
        **功能流程：**
        1. 在下方文字框中輸入美國專利號碼（每行一個）
        2. 設定下載間隔與逾時時間
        3. 點擊「開始下載」，可隨時按「取消下載」中斷

        **支援的號碼格式：**
        - 一般實用專利：`7654321`
        - 設計專利：`D959480`
        - 再發專利：`RE45678`
        - 植物專利：`PP12345`
        - 公開申請案：`20220242717`
        - 也支援含前綴格式：`US7654321`、`US-7,654,321-B2`（自動清理）

        **下載來源（自動回退）：**
        1. USPTO 官方（優先）→ 2. Google Patents → 3. FreePatentsOnline → 4. Pat2PDF
        """)

    # ── Step 1: Input patent numbers ──
    st.markdown('<div class="step-header"><span class="step-badge">1</span> 輸入美國專利號碼</div>', unsafe_allow_html=True)
    st.caption("每行輸入一個專利號碼，支援多種格式（程式會自動清理格式）。")

    raw_input = st.text_area(
        "專利號碼清單",
        value=st.session_state.t2_patents_input,
        height=200,
        placeholder="例如：\n7654321\nD959480\nRE45678\n20220242717\nUS-7,123,456-B2",
        label_visibility="collapsed",
        key="t2_input_area",
        disabled=st.session_state.t2_is_downloading,
    )
    st.session_state.t2_patents_input = raw_input

    # Parse input
    t2_patents = []
    seen_t3 = set()
    for line in raw_input.strip().split("\n"):
        normalized = _normalize_patent_number(line.strip())
        if normalized and normalized not in seen_t3:
            t2_patents.append(normalized)
            seen_t3.add(normalized)

    if t2_patents:
        st.info(f"✅ 共偵測到 **{len(t2_patents)}** 個有效專利號碼")

    # ── Step 2: Settings & Download ──
    st.markdown('<div class="step-header"><span class="step-badge">2</span> 下載設定與執行</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        t2_delay = st.slider("下載間隔（秒）", 0.5, 5.0, 1.0, 0.5, key="t2_delay",
                             disabled=st.session_state.t2_is_downloading)
    with col2:
        t2_timeout = st.slider("逾時時間（秒）", 10, 60, 30, 5, key="t2_timeout",
                               disabled=st.session_state.t2_is_downloading)

    # Download / Cancel buttons
    btn_col1, btn_col2 = st.columns([3, 1])
    with btn_col1:
        start_btn = st.button(
            "🚀 開始下載",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.t2_is_downloading or not t2_patents,
            key="t2_start_btn",
        )
    with btn_col2:
        cancel_btn = st.button(
            "⛔ 取消",
            use_container_width=True,
            disabled=not st.session_state.t2_is_downloading,
            key="t2_cancel_btn",
        )

    if cancel_btn:
        st.session_state.t2_cancel_requested = True
        st.rerun()

    if start_btn and t2_patents:
        st.session_state.t2_is_downloading = True
        st.session_state.t2_cancel_requested = False
        st.session_state.t2_success_files = []
        st.session_state.t2_fail_list = []
        st.session_state.t2_download_results = None
        st.session_state.t2_zip_data = None
        st.session_state.t2_current_idx = 0
        st.session_state.t2_dl_delay = t2_delay
        st.session_state.t2_dl_timeout = t2_timeout
        st.rerun()

    # ── Download loop ──
    if st.session_state.t2_is_downloading and t2_patents:
        prog = st.progress(0, text="準備下載中…")
        status_box = st.container()

        # Re-render already-downloaded items
        for seq, pn, data in st.session_state.t2_success_files:
            kb = len(data) / 1024
            status_box.markdown(f'<div class="result-item result-ok">✅ {seq:02d}-{pn} — 成功 ({kb:.0f} KB)</div>', unsafe_allow_html=True)
        for pn, reason in st.session_state.t2_fail_list:
            idx_display = len(st.session_state.t2_success_files) + len(st.session_state.t2_fail_list)
            status_box.markdown(f'<div class="result-item result-fail">❌ {pn} — {reason}</div>', unsafe_allow_html=True)

        start_idx = st.session_state.t2_current_idx

        if st.session_state.t2_cancel_requested:
            # User cancelled — wrap up with what we have
            prog.progress(1.0, text="⛔ 已取消下載")
            st.warning(f"下載已取消。已完成 {start_idx}/{len(t2_patents)} 件。")

            zip_data = _pack_all_zip(st.session_state.t2_success_files) if st.session_state.t2_success_files else None
            st.session_state.t2_download_results = {
                "total_success": len(st.session_state.t2_success_files),
                "total_fail": len(st.session_state.t2_fail_list),
                "fail_list": st.session_state.t2_fail_list,
                "total": len(t2_patents),
                "cancelled": True,
            }
            st.session_state.t2_zip_data = zip_data
            st.session_state.t2_is_downloading = False
            st.session_state.t2_cancel_requested = False
            st.rerun()

        elif start_idx < len(t2_patents):
            # Download one patent per rerun
            i = start_idx
            pn = t2_patents[i]
            seq = i + 1
            prog.progress(seq / len(t2_patents), text=f"下載中 {seq}/{len(t2_patents)}: {pn}")

            ok, result = _download_patent_pdf(pn, timeout=st.session_state.t2_dl_timeout)
            if ok:
                st.session_state.t2_success_files.append((seq, pn, result))
                kb = len(result) / 1024
                status_box.markdown(f'<div class="result-item result-ok">✅ {seq:02d}-{pn} — 成功 ({kb:.0f} KB)</div>', unsafe_allow_html=True)
            else:
                st.session_state.t2_fail_list.append((pn, result))
                status_box.markdown(f'<div class="result-item result-fail">❌ {seq:02d}-{pn} — {result}</div>', unsafe_allow_html=True)

            st.session_state.t2_current_idx = i + 1

            if i < len(t2_patents) - 1:
                time.sleep(st.session_state.t2_dl_delay)

            st.rerun()

        else:
            # All done
            prog.progress(1.0, text="✅ 下載完成！")
            zip_data = _pack_all_zip(st.session_state.t2_success_files) if st.session_state.t2_success_files else None
            st.session_state.t2_download_results = {
                "total_success": len(st.session_state.t2_success_files),
                "total_fail": len(st.session_state.t2_fail_list),
                "fail_list": st.session_state.t2_fail_list,
                "total": len(t2_patents),
                "cancelled": False,
            }
            st.session_state.t2_zip_data = zip_data
            st.session_state.t2_is_downloading = False
            st.rerun()

    # ── Results ──
    if st.session_state.t2_download_results and not st.session_state.t2_is_downloading:
        dr = st.session_state.t2_download_results

        st.markdown(f"""
        <div class="stats-row">
            <div class="stat-card"><div class="num" style="color:#22c55e">{dr['total_success']}</div><div class="label">成功</div></div>
            <div class="stat-card"><div class="num" style="color:#ef4444">{dr['total_fail']}</div><div class="label">失敗</div></div>
            <div class="stat-card"><div class="num">{dr['total']}</div><div class="label">總計</div></div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.t2_zip_data:
            st.download_button(
                label=f"📦 一鍵下載所有專利（{dr['total_success']} PDFs, ZIP）",
                data=st.session_state.t2_zip_data,
                file_name="manual_patents.zip",
                mime="application/zip",
                use_container_width=True,
                key="t2_zip_btn",
            )

        if dr['fail_list']:
            with st.expander(f"查看下載失敗清單（{dr['total_fail']} 件）"):
                for pn, reason in dr['fail_list']:
                    st.text(f"{pn}: {reason}")
