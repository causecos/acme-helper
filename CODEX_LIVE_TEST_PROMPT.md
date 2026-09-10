# 工程代理／ChatGPT 實機驗收提示詞：ACME Helper v1.10.1

你接手 repo `acme-helper`，目標是讓初學者與專業維運人員不必記大量 acme.sh 參數。以收到的完整 v1.10.1 套件為準，先驗證 SHA256SUMS；不要改用對話裡更早版本或散落單檔。

**目標真機不需要安裝 Codex 或任何 AI agent。** 如果工程代理不直接執行在真機，請由操作者在真機先跑 `acme diagnose`；需要實際錯誤輸出時使用 `acme diagnose --log FILE`。將產生的 mode-0600 提示詞人工檢查後貼回 ChatGPT／工程代理，再由代理依證據規劃下一個非秘密驗證步驟。

## 固定契約

CLI `acme`；letsencrypt / dns_namesilo / 120 / ec-256 / minimal；domains.txt 保留；email 選填；新安裝 cron off；英文及台灣繁體中文。語言只能改顯示，不能改 DNS/CA/網域/路徑/Token 或機器讀取鍵。

## 先盤點與隔離

辨認實際 OS、Python/Bash、執行帳號、acme.sh 程式目錄、config home、account.conf、現有憑證、排程與正在執行的簽發。不得把 `sudo -n` 失敗說成不是實機。預設建立獨立測試目錄；不要讀出或印出正式 Token、私鑰、帳號設定全文。不要把正式網域或正式 DNS 修改當作已授權。

先記錄原程式／設定 hash、權限、排程及輸出目錄；建立可恢復備份。版本回滾只備份程式資產，不能當秘密資料或憑證的完整備份。停止條件：遇到無法辨識的生產目標、權限不足、校驗不符、未授權 DNS/服務變更即停止該分支並列 BLOCKED，不阻塞可做的隔離測試。

## 四項整合驗收

1. 消融：對真正有刪減候選的設計，在隔離副本移除一項後重測。測試語系檔缺失、快速選單不影響專業 CLI、非空 Key 判斷與下載完整性檢查。區分必要保護、純 UX、重複設計；不能只換檔名重跑當消融。
2. Code Review：核對 CLI 分派、選單、設定優先序、語系模板、subprocess argv/environment、認證保密、同名 RSA/ECC、輸出碰撞、cron 精準定位、版本回滾。新發現問題先重現再修；保留修補前後證據。
3. 三輪對抗：正確性與預設契約；注入／秘密／取消／失敗完整性；版本／metadata／i18n 漂移。不得重複一組 smoke 充三輪。
4. CLI + 真 PTY + non-TTY：各公開流程列出成功、拒絕、取消、失敗與適用模式。檢驗真實副作用而不是只找 PASS 字串；沒有執行或不適用的分支明列原因。

先執行：

```bash
python3 -S tests/run_all.py --report-dir /tmp/acme-helper-verification
```

這是 mock/隔離流程，不是外網 E2E。

## 真機無 AI agent 的交接流程

最低需求只有 ACME Helper 本身：

```bash
acme diagnose
```

診斷預設不含網域、不讀任何 log、不跑 tests。需要加入已保存的終端／acme.sh 錯誤時明確使用：

```bash
acme diagnose --log /tmp/acme-error.log
```

完整 source/release package 可選 `--run-tests`；它只跑有界 diagnostic profile，必須明列 canonical `flow_matrix` 為 omitted。完整 release regression 仍另外執行 `tests/run_all.py`。安裝版沒有 `tests/` 時必須標 `NOT_RUN`。`--include-domains` 只有在 SAN／主網域證據必要且操作者同意暴露 hostnames 時使用。

審查診斷提示詞必須確認：輸出 mode 0600；不覆寫既有檔；不自動讀 log；account.conf 不輸出 value；provider 只列狀態；Secret/Authorization/Cookie/URL 密碼/provider ID/private-key block 被遮蔽；log 內容在提示詞中被明確標為不可信證據而非 AI 指令。

## 必做 UX / i18n

逐一抽查所有互動式正式執行路徑：最終設定解析完成後、執行／最後確認前必須先出現可直接複製的 `acme ...`。確認顯示值與實際下游 argv 一致；直接 CLI 不應額外重複預覽。Token、Password、EAB HMAC、DNS credential、hook environment 不得出現在預覽；PKCS#12/EAB 使用 stdin 安全入口；破壞性快捷不可自動加入 `--yes`。version/defaults/status/providers/hooks 等唯讀選單也要能得到下次直接指令。

空白安裝、新手選單七分類、快速簽發、DNS 搜尋後編號選擇、缺少 Key 的安全輸入、中文/英文切換後主選單即更新、舊 CLI 可用、:back 不得吞掉 Secret 值、Ctrl-C/D、Backspace/DEL/方向鍵/CJK、stdout/stderr、只留必要提示。

檢查兩份訊息目錄 key 與 placeholder；翻譯缺失退回英文；原生 `--lang` 等未知參數必須原樣轉送。多語言同一操作的 argv 與檔案結果必須相同。安裝到有空白的自訂 PREFIX 後再測語系資源。實際跑至少一個 Python 3.6 相容環境或明列 NOT_RUN；語法檢查不能冒充直譯器測試。

## 外部實機階段（需明確授權）

下載固定 tag 的官方 acme.sh，記錄實際 hash/version/help/completion；完整掃描當版 dnsapi/deploy/notify corpus，核對清單與 metadata 分類，不以測試快照 35/80 當完整上游事實。

對每個有合法 credential 的 DNS provider，使用授權測試 zone 與 Let's Encrypt staging 驗證 TXT 新增、傳播、清除；無 credential 標 BLOCKED_NO_CREDENTIAL。驗證實際 X.509 SAN、私鑰匹配、minimal/full/nginx/none、原始 provider 的續期、所有域名顯示、相同主網域 RSA/ECC 選取與部署，及 domains.txt 與原生重簽時的邊界。不得反覆對 production `--force`。

使用隔離 crontab／帳號測試 off/on/run，確認不誤改其他 home 的任務，且自訂 ACCOUNT_CONF_PATH/LE_CONFIG_HOME 在排程內仍可用。若僅靠臨時環境變數，先設計並驗證同環境執行方案，不自動重寫使用者正式排程。

對實際版本切換、失敗回滾、卸載進行 staging target 測試；保留資料，驗證程式、hook 與設定目錄分工。至少做一個「切換前某個 optional 程式資產目錄不存在 → 目標版本新增該目錄 → 故意讓相容性／版本檢查失敗」案例，確認新格式備份回滾後該 target-only 目錄再次不存在；另以沒有 `assets=` 欄位的舊格式備份確認只恢復備份內實際內容，不推測並刪除未記錄的 live 目錄。記錄回滾不具跨目錄 crash atomicity 的限制；不得未驗證便宣稱斷電恢復保證。

實際 deploy / notify 要有授權的目標。證明服務讀到新憑證、reload 成功及通知到達，不能只用 exit=0。生產簽發、撤銷、刪除與真服務 reload 另需使用者明確授權。

## 最終交付

完整 repo 與單一版本包、README、功能矩陣、測試清單、修補前後證據、完整 hash 與封包解壓重測。狀態僅用 CONFIRMED / FAILED / BLOCKED / NOT_RUN，明確分隔 mock、真 PTY、真 DNS/CA。修程式後重跑受影響的四項驗收；不可沿用舊 PASS。
