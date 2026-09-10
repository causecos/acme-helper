# 引導文字國際化／Internationalization

## 設計

核心使用 `_('English source template')` 做字典查詢；`locales/en.json` 是英文參考目錄，`locales/zh-TW.json` 提供台灣繁體中文。沒有 gettext 編譯、翻譯服務、額外套件或新的設定資料庫。

一律先翻譯模板，再 `.format()` 插入資料，不能先把 Token、網域或路徑混入字串再做全域替換。選單顯示文字可翻譯，實際指令值、CLI 選項及機器輸出鍵不可翻譯。

## 修改流程

1. 修改 Helper 自己的來源訊息，兩份 JSON 保持同樣的 key。
2. 翻譯值必須保留所有 `{}`、`{name}`、format specifier 的順序與用途。
3. 執行 `python3 -S tests/review_v19.py`，檢查 key、格式欄位、語言切換、相同 argv、隱藏輸入與封包安裝。
4. 執行 `python3 -S tests/review_v110.py`，確認診斷交接的 en/zh-TW 指示都存在，但 `[HELPER_RUNTIME]`、`[ACME_SH]` 等機器段落名稱保持穩定。
5. 執行完整 `tests/run_all.py`，再從發佈壓縮檔解壓重跑。

目前語言白名單只有 `zh-TW` 與 `en`；新增語言還需要更新 `init_language` / `language_cmd` 的選項、installer 與測試，不能只放一個任意檔名就當支援。

CLI 的 `--lang` 僅解析命令前綴；例如 `acme native --lang xx` 必須原樣交給 acme.sh，不得被 Helper 攔截。

快捷 CLI 的標題、注意事項可翻譯，但 `acme`、子命令、options、quoted values 與 `[hidden]` 是可執行／安全契約，不得翻譯。翻譯測試同時確認 zh-TW/en 的快捷指令 argv 語意一致。

`acme diagnose` 的「如何分析／不要索取秘密／如何區分事實與推測」屬人類指示，可翻譯；`ACME_HELPER_DIAGNOSTIC_PROMPT_BEGIN`、`[LAST_OPERATION]`、`[HELPER_RUNTIME]`、`[ACME_SH]`、`NOT_RUN`／`BLOCKED` 等交接協定與機器欄位不得翻譯，方便跨語言工具穩定解析。

## 明確不翻譯

acme.sh 輸出、第三方 DNS/deploy/notify metadata、未知新參數的原廠說明、開機前置檢查、機器讀取狀態值保留原文。這可以避免解析資料受翻譯影響，也保留原廠錯誤供維運查找。

## 新版移除的重複內容

移除八個已不再使用的舊說明／提示模板。不新增固定 DNS 業者清單或依賴語言文字判定操作的分派表。
