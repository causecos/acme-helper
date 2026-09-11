# ACME Helper：功能覆蓋與 UX 邊界

本文件描述**目前主線功能邊界**；版本歷史請看 [CHANGELOG.md](CHANGELOG.md)，特定安全驗證證據請看 [AUDIT.md](AUDIT.md)。

## 三個不同的證據層級

**入口可達**：功能可經 Helper 專用路徑、動態原生編輯器或 native 呼叫。  
**引導可操作**：能從選單選取目標、看到用途與風險、處理取消或錯誤。  
**外部實機成功**：DNS/CA、部署、通知等真實外部服務完成。

離線回歸只能證明前兩層與本機邊界；不能把 mock/PTY 通過寫成所有 provider、CA 或 hook 的外部成功。

## 功能矩陣

| 範圍 | 入口與 UX | 主要證據／限制 |
|---|---|---|
| 憑證簽發 | 主選單 1 與 `acme issue` 為同一精靈；DNS、webroot、standalone、ALPN、stateless、Apache、Nginx、manual DNS、DNS persist | CLI/PTY 與參數轉送回歸；`acme quick` 只保留相容 alias |
| 多網域 | `merged` 單張 SAN；`separate` 每名稱獨立憑證 | separate 逐域名 request、重複名稱、部分失敗、輸出碰撞與 `<output>/<cert-name>/<domain>` 路徑回歸 |
| DNS provider | 實際安裝樹動態清單、metadata 認證精靈 | 不維護第二份 vendor schema；configured 不等於真實 API 認證成功 |
| 憑證/SAN | 列全部 SAN、讀取、續期、安裝、部署、撤銷、停用授權、移除管理 | acme.sh managed state 為權威；`domains.txt` 只是要求內容 manifest |
| cron | 查看、啟用、停用、執行一次 | 新安裝預設 off；仍由上游管理實際 cron 格式 |
| deploy / notify | 動態 hook、環境欄位、確認 | 外部服務成功需真機 credential/target 驗證 |
| 帳號 / CA / CSR / key / export | 進階工具與既有命令 | 敏感輸入採隱藏/遮蔽路徑；高風險操作保留確認 |
| 原生命令與參數 | native/all 動態 help/completion + 原樣轉送 | 不宣稱固定上游命令總數；未知新功能保持原廠文字 |
| 互動快捷 CLI | guided 執行在正式動作前顯示可複製 `acme ...` | shell-safe quoting；secret/HMAC/PFX/hook env 不展開；破壞性命令不偷偷加 `--yes` |
| ChatGPT 修復交接 | `acme diagnose`，可選 `--log`、`--include-domains`、`--run-tests` | 唯讀、log opt-in、0600、集中遮蔽、prompt-injection trust boundary、獨立 HOME/TMPDIR |
| 語言 | zh-TW / en | Helper UI 翻譯；不改寫上游錯誤、網域、路徑、token 或機器欄位 |
| 安裝與版本 | Helper installer；acme.sh install/update/switch/rollback/uninstall | Helper 與 upstream 版本分開顯示；完整版本規則見 `docs/VERSIONING.md` |

## UX 原則

- 主選單按「任務」分組，不把同一件事拆成兩個近似入口。
- 初學者與熟手使用相同核心行為；互動模式只是幫忙解析參數與確認。
- acme.sh 擁有 ACME、provider/hook catalog、managed certificate state 與 renewal/cron 行為；Helper 不建立第二套引擎或資料庫。
- 對外部不可逆或有副作用的動作，錯誤時 fail closed；不做無法保證一致性的假 transaction。

## 保留限制

- 真實 DNS/CA、deploy、notify 成功仍需要對應 provider credential 與外部環境驗收。
- Python 3.6 是 runtime 語法/API floor；CI 可能使用較新 Python 執行同一份相容語法。
- 自訂環境只作用於本次程序；獨立排程需要相同設定來源。
- 自動 secret redaction 是風險降低措施，不是任意 log 的資料外洩保證。
- `diagnose --run-tests` 是有界診斷 profile；完整 release regression 仍使用 `python3 -S tests/run_all.py`。
- 測試案例數不等於 100% 程式碼分支覆蓋率。
