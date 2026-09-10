# ACME Helper v1.10.1：ChatGPT 修復交接

真機不需要安裝 Codex、ChatGPT CLI 或其他 AI agent。ACME Helper 本身可以把唯讀環境證據整理成一份可直接貼到 ChatGPT 的診斷提示詞。

## 最短流程

真機發生問題後：

```bash
acme diagnose
```

預設輸出到新建的暫存檔，權限 `0600`。Helper 會印出實際檔案位置。打開檔案人工看過一次，再把**檔案內容**貼進 ChatGPT。

如果 ChatGPT 判定需要修改 ACME Helper 程式碼，請再提供**和提示詞內版本／SHA-256 相符的完整 ACME Helper 壓縮包**。不要只貼散落的單一 `acme_cli.py`，避免版本漂移。

## 把實際錯誤輸出一起交接

`acme diagnose` 不會自行讀任何 log。先把已發生的錯誤輸出保存成檔案，再明確指定：

```bash
acme diagnose --log /tmp/acme-error.log
```

可重複使用 `--log` 附多個檔案。Helper 只讀 regular file；symlink 會拒絕。

不要為了取得 log 而無腦重跑 revoke、delete、deactivate、uninstall、deploy 等可能有副作用的操作。如果錯誤已經發生但當時沒有保存完整 stdout/stderr，先用不會重複破壞操作的唯讀狀態證據產生 `acme diagnose`，再由 ChatGPT 判斷還缺什麼。

## 其他模式

直接印到 stdout：

```bash
acme diagnose --stdout
```

指定輸出檔：

```bash
acme diagnose --output /tmp/acme-helper-handoff.txt
```

既有檔案不會被覆寫。

預設不列憑證網域。如果問題和 SAN／主網域對應有關，才明確允許：

```bash
acme diagnose --include-domains
```

在完整 repo／release package 裡，可跑**有界診斷 regression**：

```bash
acme diagnose --run-tests
```

這個 profile 執行消融、三輪對抗與兩份獨立 UX／診斷 review，刻意省略耗時的 canonical `flow_matrix`，提示詞會列 `offline_omitted_suites=flow_matrix`。完整發行驗收仍用 `python3 -S tests/run_all.py`。測試 runner 會建立每套 suite 專用的 HOME/TMPDIR，並移除真機 ACME/provider/account/BASH_ENV/PYTHONPATH 等環境，避免 mock regression 誤讀正式機狀態或 credential。系統安裝版通常不帶 `tests/`，會明確輸出 `NOT_RUN`。不能把 offline PASS 當成真實 DNS API、CA、deploy 或 notify E2E PASS。

## 交接提示詞包含什麼

預設會整理：

- ACME Helper 版本、Python、core 路徑與 SHA-256。
- Linux／kernel／locale／TTY 基本環境。
- Helper source compile、launcher `bash -n`、語系 catalog parity、ShellCheck 是否存在。
- acme.sh 路徑、檔案 metadata、SHA-256、版本、help/parameter/provider compatibility 與唯讀 smoke。
- server／DNS provider／dnssleep／keylength／output layout 等非秘密 default。
- wrapper config 與 account config 的**檔案 metadata**，不讀取 account.conf 明文到提示詞。
- DNS provider 的 `configured`／`runtime-ready` 狀態與統計，不列 credential value。
- managed certificate 數量；網域名稱預設不列。
- acme.sh cron 狀態與匹配數量。
- 使用者用 `--log FILE` 明確提供的 log tail。
- `--run-tests` 的離線測試結果或 `NOT_RUN`。
- 明確要求 ChatGPT 區分確認事實、假設與缺少證據，先提出最小安全修復。

## 遮蔽契約

提示詞產生前會集中遮蔽常見敏感資料，包括：

- Token / Secret / Password / Credential / API Key / Private Key / HMAC。
- `--password`、`--eab-hmac-key` 及同類 secret flag。
- Authorization Bearer / Basic。
- Cookie / Set-Cookie / X-API-Key / API-Key / X-Auth-Key / Proxy-Authorization。
- URL `user:password@host` 的 password。
- 常見 provider Account/Zone/Tenant/Client/Subscription ID assignment。
- PEM private-key block。

但是：**自動遮蔽不是資料外洩保證。** 網域、路徑、帳號名稱、第三方錯誤內容或業務資料仍可能出現在使用者明確提供的 log，所以送出前要人工看一次。

## 正常失敗時的提示

一般 ACME Helper 命令以非零狀態結束時會提示：

```text
For a redacted ChatGPT repair handoff, run: acme diagnose
If you saved the failing terminal output, use: acme diagnose --log FILE
```

繁中介面會顯示對應繁中提示。

診斷命令本身若輸入錯誤，不會再遞迴提示自己。

## 貼給 ChatGPT 後的責任邊界

產生的提示詞要求 ChatGPT：

1. 先分類故障層：Helper、acme.sh、DNS API、CA/account、certificate state、cron、deploy/notify、權限／路徑或外部網路／服務。
2. 引用提示詞內具體證據，不從缺少資訊猜答案。
3. 區分已確認、推測與仍缺證據。
4. 優先最小、安全、可回歸驗證的修補。
5. 若需修改程式碼，鎖定提示詞內 Helper 版本與 SHA-256，指出修改檔案／函式與必跑 regression。
6. 不索取 Token、Key、password、private key。
7. 外部 E2E 尚未驗證時標 `NOT_RUN`／`BLOCKED`，不要拿本地 configured 或 mock PASS 冒充 live success。
