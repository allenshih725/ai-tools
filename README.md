# 🧰 慧盈AI工具庫

多功能工作平台，目前包含「下載美國OA中的US前案」工具，透過側邊欄可切換不同工具頁面。

## 主要功能：下載美國OA中的US前案

上傳 USPTO Office Action PDF → 自動擷取 PTO-892（Notice of References Cited）中的美國專利號碼 → 可手動修正清單 → 批次下載專利 PDF。

### 特色

- **雙模式擷取** — 有文字層的 PDF 用 Regex 直接擷取（免 API），純掃描 PDF 用 Claude Vision OCR
- **僅擷取 PTO-892** — 自動排除 IDS（PTO/SB/08）表格中的資料
- **可編輯清單** — 擷取後可手動修正 OCR 辨識錯誤，再進入下載步驟
- **多來源回退下載** — 依序嘗試 USPTO、Google Patents、FreePatentsOnline、Pat2PDF
- **序號檔名** — ZIP 內 PDF 命名為 `01-D959480.pdf`、`02-7654321.pdf` 等
- **多頁面架構** — 側邊欄可切換不同工具，未來可擴充

## 檔案結構

```
├── app.py               # 主程式
├── requirements.txt     # Python 依賴套件
└── README.md            # 本文件
```

## 部署方式

### Streamlit Cloud（推薦）

1. 將三個檔案上傳至 GitHub repository
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
