import streamlit as st
import os

from tools import g1001
from tools import g1002
from tools import g1003

# ── Page Config ──
st.set_page_config(
    page_title="慧盈AI工具庫",
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

/* Sidebar navigation styling */
div[data-testid="stSidebar"] .stRadio > div { gap: 0.2rem; }
div[data-testid="stSidebar"] .stRadio label { font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════
# Tool Group Definitions & Route Table
# ══════════════════════════════════════════════

TOOL_GROUPS = {
    "專利行政工具": [
        "下載美國OA中的US專利",
        "手動輸入專利號來下載PDF",
        "美國專利OA檢索報告中的美國專利下載工具",
        "群組1工具4", "群組1工具5", "群組1工具6",
        "群組1工具7", "群組1工具8", "群組1工具9", "群組1工具10",
    ],
    "專利實體工具": [f"群組2工具{i}" for i in range(1, 11)],
    "商標行政工具": [f"群組3工具{i}" for i in range(1, 11)],
    "商標實體工具": [f"群組4工具{i}" for i in range(1, 11)],
    "其他工具": [f"群組5工具{i}" for i in range(1, 21)],
}

ROUTE = {
    "下載美國OA中的US專利": g1001.render,
    "手動輸入專利號來下載PDF": g1002.render,
    "美國專利OA檢索報告中的美國專利下載工具": g1003.render,
}

ALL_TOOLS = []
for _grp, _tools in TOOL_GROUPS.items():
    ALL_TOOLS.extend(_tools)


# ══════════════════════════════════════════════
# Sidebar — Multi-page Navigation
# ══════════════════════════════════════════════

if "selected_page" not in st.session_state:
    st.session_state.selected_page = ALL_TOOLS[0]

def _on_group_change(group_key):
    st.session_state.selected_page = st.session_state[group_key]

def _get_api_key() -> str | None:
    """Read API key from Secrets or env var."""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", None)
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", None)

with st.sidebar:
    st.markdown("## 🧰 慧盈AI工具庫")
    st.markdown("---")

    for group_name, tools in TOOL_GROUPS.items():
        group_key = f"grp_{group_name}"
        current_in_group = st.session_state.selected_page in tools
        with st.expander(f"📁 {group_name}", expanded=current_in_group):
            default_idx = tools.index(st.session_state.selected_page) if current_in_group else 0
            st.radio(
                f"選擇{group_name}",
                tools,
                index=default_idx,
                key=group_key,
                on_change=_on_group_change,
                args=(group_key,),
                label_visibility="collapsed",
            )

    st.markdown("---")
    st.caption("v4.0 — 模組化架構版")

    # API Key in sidebar (shared across tools)
    secrets_key = _get_api_key()
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
# Page Routing
# ══════════════════════════════════════════════

page = st.session_state.selected_page

if page in ROUTE:
    ROUTE[page](api_key=api_key)
else:
    st.markdown(f"""
    <div class="hero">
        <h1>🚧 {page}</h1>
        <p>此工具尚在開發中，敬請期待</p>
    </div>
    """, unsafe_allow_html=True)
    st.info("🚧 此工具尚在開發中，敬請期待。")


# ── Footer ──
st.markdown("""
<div class="footer">
    Sources: USPTO · Google Patents · FreePatentsOnline · Pat2PDF<br>
    For personal research use only. Please comply with each source's terms of service.
</div>
""", unsafe_allow_html=True)
