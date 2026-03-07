# 🧰 慧盈AI工具庫

多功能工作平台，側邊欄以折疊式群組分類，可快速切換不同工具頁面。

## 架構說明

v4.0 起採用模組化架構，每個工具完全獨立，修改任一工具不會影響其他工具。

```
├── app.py                              # 主程式（側邊欄導航 + 路由）
├── tools/
│   ├── __init__.py
│   ├── g1001.py                   # G1001：下載美國OA中的US專利
│   ├── g1002.py                   # G1002：手動輸入專利號來下載PDF
│   └── g1003.py                   # G1003：美國專利OA檢索報告中的美國專利下載工具
├── requirements.txt                    # Python 依賴套件
└── README.md                           # 本文件
```

### 模組化設計原則

- **每個工具 100% 自給自足**：所有函式（下載、擷取、打包等）都內建在各工具檔案中，不與其他工具共用
- **app.py 只負責兩件事**：畫側邊欄、根據選擇呼叫對應工具的 `render()` 函式
- **新增工具只需兩步**：在 `tools/` 新增檔案，在 `app.py` 的 `TOOL_GROUPS` 和 `ROUTE` 各加一行

## 工具群組架構

| 群組 | 工具數 | 目前狀態 |
|------|--------|----------|
| 專利行政工具 | 10 | 工具 1～3 已上線，其餘開發中 |
| 專利實體工具 | 10 | 開發中 |
| 商標行政工具 | 10 | 開發中 |
| 商標實體工具 | 10 | 開發中 |
| 其他工具 | 20 | 開發中 |

## 已上線功能

### 專利行政工具 — 工具 1：下載美國OA中的US專利

上傳 USPTO Office Action PDF → 自動擷取 PTO-892（Notice of References Cited）中的美國專利號碼 → 可手動修正清單 → 確認後顯示含下載連結的專利清單表格 → 批次下載專利 PDF。

### 專利行政工具 — 工具 2：手動輸入專利號來下載PDF

直接輸入美國專利號碼清單 → 批次下載 PDF。

### 專利行政工具 — 工具 3：美國專利OA檢索報告中的美國專利下載工具

上傳 USPTO Office Action PDF → 自動擷取檢索報告中的美國專利清單 → 批次下載 PDF。

### 特色

- **模組化架構** — 每個工具完全獨立，修改不互相影響
- **折疊式群組導航** — 側邊欄以 5 大群組分類，各群組可獨立展開/收合
- **雙模式擷取** — 有文字層的 PDF 用 Regex 直接擷取（免 API），純掃描 PDF 用 Claude Vision OCR
- **僅擷取 PTO-892** — 自動排除 IDS（PTO/SB/08）表格中的資料
- **可編輯清單** — 擷取後可手動修正 OCR 辨識錯誤，再進入下載步驟
- **序號檔名** — ZIP 內 PDF 命名為 `01-D959480.pdf`、`02-7654321.pdf` 等

## 部署方式

### Streamlit Cloud（推薦）

1. 將所有檔案（含 `tools/` 資料夾）上傳至 GitHub repository
2. 至 [share.streamlit.io](https://share.streamlit.io) 部署該 repo
3. 在 Settings → Secrets 設定 API Key：
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-your-key-here"
   ```

### 本機執行

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
streamlit run app.py
```

## 新增工具步驟

1. 在 `tools/` 資料夾新增一個 Python 檔案（例如 `g1004.py` 或 `g2001.py`）
2. 檔案內定義 `render(api_key=None)` 函式作為入口
3. 所有函式和 session state 初始化都寫在該檔案內
4. 在 `app.py` 中：
   - `import` 新工具模組
   - 在 `TOOL_GROUPS` 中將佔位名稱替換為正式工具名稱
   - 在 `ROUTE` 字典中加入對應的 render 函式

### 工具命名規則

檔名格式為 `g{群組編號}_tool_{工具編號}.py`，例如：

| 群組 | 檔名範例 | 程式碼內部命名 |
|------|----------|---------------|
| 專利行政工具（G1） | `g1001.py` | G1001 |
| 專利實體工具（G2） | `g2001.py` | G2001 |
| 商標行政工具（G3） | `g3001.py` | G3001 |
| 商標實體工具（G4） | `g4001.py` | G4001 |
| 其他工具（G5） | `g5001.py` | G5001 |

## 依賴套件

| 套件 | 用途 |
|------|------|
| streamlit | Web 應用框架 |
| requests | HTTP 請求（Claude API + 專利 PDF 下載） |
| PyMuPDF | PDF 文字提取與頁面轉圖片 |

## 注意事項

- Regex 擷取模式不需要 API，零成本且 100% 準確
- Vision OCR 模式每次擷取約消耗 1 次 Claude API 呼叫
- 下載間隔預設 1 秒，可自行調整
- Streamlit Cloud 免費方案記憶體約 1 GB，一般 PTO-892（5~20 件專利）足夠使用

## 授權

僅供個人學習研究使用，請遵守各專利來源網站的使用條款。
