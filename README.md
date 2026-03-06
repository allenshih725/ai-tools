# 🧰 慧盈AI工具庫

多功能專利工作平台，透過側邊欄切換不同工具。目前包含兩個可運作的專利下載工具。

## 工具列表

| 工具 | 狀態 | 說明 |
|------|------|------|
| 📄 下載美國OA中的US前案 | ✅ 可用 | 擷取 PTO-892 專利號碼 → 可手動編輯清單 → 批次下載 PDF |
| 📄 美國專利OA檢索報告中的美國專利下載工具 | ✅ 可用 | 擷取 PTO-892 專利號碼 → 直接批次下載 PDF |
| 🧪 測試工具 | 🔲 預留 | 開發中 |
| 🔧 更多工具 | 🔲 預留 | 開發中 |

### 兩個工具的差異

- **下載美國OA中的US前案** — 擷取後有 Step 2.5 可編輯清單，讓使用者在下載前修正 OCR 錯誤
- **美國專利OA檢索報告中的美國專利下載工具** — 擷取後直接顯示表格並下載，流程較簡潔

### 共通功能

- 支援有文字層的 PDF（Regex 直接擷取，免 API）和純掃描 PDF（Claude Vision OCR）
- 僅擷取 PTO-892（Notice of References Cited），自動排除 IDS
- 多來源回退下載：USPTO → Google Patents → FreePatentsOnline → Pat2PDF
- ZIP 內 PDF 檔名格式：`01-D959480.pdf`、`02-7654321.pdf`

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
- Streamlit Cloud 免費方案記憶體約 1 GB，一般 PTO-892（5~20 件專利）足夠使用
- 免費方案只能部署 1 個私有 app，所有工具已整合在同一個 app 中透過側邊欄切換

## 授權

僅供個人學習研究使用，請遵守各專利來源網站的使用條款。
