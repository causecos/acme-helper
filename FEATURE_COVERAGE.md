# ACME Helper v1.10.1：功能覆蓋與 UX 邊界

## 三個不同的檢核層級

**入口可達**：功能可以經 Helper 專用路徑、動態原生編輯器或 native 呼叫。**引導可操作**：能從選單選取目標、看到用途與風險、處理取消或錯誤。**外部實機成功**：DNS/CA、部署、通知等服務確實完成；本輪沒有把第三層列為通過。

不能把「有 native 轉送」直接說成每個外部服務都已具備完整新手精靈。

## 功能矩陣

| 範圍 | 入口與 UX | 本輪證據／限制 |
|---|---|---|
| 上游安裝、更新、切版、回滾、移除 | 安裝與版本分類；原短指令保留 | CLI/PTY fixture 回歸；新格式回滾會依 manifest 還原程式資產的存在／不存在狀態；真實下載安裝未執行 |
| 快速 DNS 簽發 | 一個任務精靈、預設值、搜尋編號、缺少設定時引導輸入 | 中英雙語 PTY、取消、成功、argv 一致測試 |
| 全驗證模式 | 進階 issue：DNS、webroot、standalone、ALPN、stateless、Apache、Nginx、手動 DNS、DNS persist | 各入口參數回歸；外部驗證未執行 |
| DNS provider | 實際安裝樹動態清單、metadata 認證精靈 | 不維護第二份 vendor schema；manual-schema/runtime-only 明示 |
| 憑證/SAN | 列全部網域、讀取、續期、安裝、部署、撤銷、停用授權、移除管理 | RSA/ECC 選取身分不再二次查找；跨憑證輸出路徑防衝突 |
| cron | 查看、啟用、停用、執行一次 | 依目前程式絕對路徑辨認；新安裝預設 off |
| deploy / notify | 動態 hook、環境欄位、確認 | 只有可觀察欄位，不假裝有完整 required/optional schema |
| 帳號 / CA / CSR / key / export | 進階工具與既有命令 | 已儲存 CA 預設套用一致；保留敏感資料遮蔽 |
| 原生命令與參數 | native/all 動態 help/completion + 原樣轉送 | 測試快照 35 個命令、80 個參數；不是今天上游總數宣告 |
| 互動快捷 CLI | 所有 guided 執行在正式動作前顯示可複製的 `acme ...`；唯讀 guided 任務同樣提供快捷入口 | shell-safe quoting；Secret/HMAC/PFX/hook env 不展開；破壞性命令不自動加入 `--yes` |
| ChatGPT 修復交接 | `acme diagnose`／進階選單；可選 `--log`、`--include-domains`、`--run-tests` | 唯讀狀態收集；log 明確 opt-in；0600；集中遮蔽；log 視為不可信證據防 prompt injection；bounded 測試使用獨立 HOME/TMPDIR 且不繼承正式 credential；安裝版沒 tests 時標 NOT_RUN |
| 語言 | zh-TW/en、設定持久化、全域前綴參數 | 715 對訊息模板；key/格式欄位一致、真實 PTY 與相同 argv |
| 安裝資源 | 自訂 PREFIX、核心與兩份語系檔一起安裝 | 完整安裝流程測試，非僅工作目錄直接執行 |

## UX 採用原則

主選單是七種任務，不再平鋪二十多個操作名稱。憑證、排程、帳號、通知等選單可用編號或原指令值；DNS 搜尋結果可選編號。操作完成回主選單，保留 :back、Ctrl-C、Ctrl-D 與非 TTY 單次執行。

初學者預設從快速 DNS 簽發開始；熟手仍能使用原有 `acme "DOMAIN ..." 120`。不新增第二個 ACME 引擎、排程器、認證資料庫或憑證資料庫。

真機故障交接不要求安裝 AI agent。`acme diagnose` 只做唯讀探測並產生可貼給 ChatGPT 的提示詞；設定檔只列 metadata、provider 只列狀態，網域與 log 都採明確 opt-in。這不是第二套監控／log 系統。

## 保留的限制

- 上游文字、未知參數說明與第三方 metadata 不自動翻譯；原廠錯誤維持可搜尋性。
- 無 metadata 的 DNS driver 仍須依原廠文件設定，不能宣稱全部 provider 都一鍵完成。
- 本機 configured 不等於 API 授權有效；沒有真實 credential 的服務測試均為 NOT_RUN/BLOCKED。
- Python 3.6 是語法/API 目標，不是本輪實際直譯器；實測 3.13.5。
- 自訂環境只作用於本次子程序，獨立排程仍需相同設定。
- v1.10.1 新格式備份會還原 `acme.sh/dnsapi/deploy/notify` 的存在／不存在狀態；舊備份沒有 `assets=` 時只恢復實際備份內容，不猜測原狀。整體仍不是跨目錄斷電安全交易；不得與其他寫入者同時執行。
- 案例清單不代表 100% 程式碼分支／條件組合覆蓋。
- 診斷提示詞有集中式秘密遮蔽，但自動遮蔽不是資料外洩保證；使用者明確附加的 log 仍須人工檢視。
- `diagnose --run-tests` 是有界 offline profile，刻意省略耗時 canonical `flow_matrix`；完整 release regression 與外部 E2E 仍需另外執行。
