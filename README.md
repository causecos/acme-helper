# ACME Helper v1.10.1

[English](README.en.md) · [功能與限制](FEATURE_COVERAGE.md) · [檢核報告](AUDIT.md) · [ChatGPT 修復交接](CHATGPT_REPAIR_HANDOFF.md) · [進階實機驗收](CODEX_LIVE_TEST_PROMPT.md)

Repository：`acme-helper`。指令：`acme`。

**宗旨：讓初學者不用記一堆參數就能使用 acme.sh，也讓專業人員能快速、可預測地維運。**

Helper 是 acme.sh 的引導前端，不重新實作 ACME、DNS 驗證或憑證資料庫。一般工作從任務選單完成；既有短指令和原生參數入口保留。

### v1.10.1 修正

版本切換失敗時，回滾現在會依新格式備份的 `assets=` 清單，同時還原 `acme.sh/dnsapi/deploy/notify` 的「存在」與「原本不存在」狀態，避免目標版本新加入的 hook 目錄殘留。舊版備份若沒有 `assets=` 欄位，為避免猜錯原狀，仍只恢復備份裡實際存在的程式資產。測試也不再只修改 mock 版本字串就宣稱舊版相容；缺少目前必要命令的 3.1.3-like 介面會明確判定 `incompatible`。

## 安裝與升級 Helper

```bash
tar -xzf acme-helper-v1.10.1.tar.gz
cd acme-helper-v1.10.1
sha256sum -c SHA256SUMS
sudo ./install.sh
```

非 root 安裝：

```bash
PREFIX="$HOME/.local" ./install.sh
"$HOME/.local/bin/acme"
```

`~/.local/bin` 未在 PATH 時使用完整路徑；非 root 使用者請透過 `acme config defaults` 把輸出根目錄改為可寫位置。從舊版升級時執行同一個 installer，不清除憑證、Token、已存預設或 cron。

安裝內容是 `<PREFIX>/bin/acme`、`<PREFIX>/lib/acme/acme_cli.py` 與 `<PREFIX>/lib/acme/locales/*.json`。請勿只複製 launcher；缺少語系檔會退回英文，缺少核心則無法執行。

## 初次使用

```bash
acme
```

主選單：

```text
1. 快速簽發（DNS API）
2. 憑證：所有 SAN／續期／部署／移除管理
3. 設定 DNS 認證資料
4. 排程與通知
5. 安裝與版本
6. 進階工具／acme.sh 完整功能
7. 預設值與語言
0. 離開
```

尚未安裝 acme.sh 時，先選 5 → 安裝。email 可略過，cron 預設關閉。安裝版本固定使用本套件目標 `3.1.4`，**不是宣稱它永遠是最新版本**；可指定其他 tag 或 branch。

之後選 1，輸入網域、選擇實際代管 DNS 的服務商。缺少認證資料時，可直接進入安全輸入流程。搜尋用 `/cloud` 之類的關鍵字，列出結果後輸入編號，不必背 `dns_cf`。

一般欄位輸入 `:back` 可返回主選單；Token／密碼欄位不把 `:back` 當命令。Ctrl-C 取消、Ctrl-D 結束輸入。操作完成或可恢復的錯誤會回主選單，不自動重試破壞性操作。原本的 `issue`、`certs` 等指令名稱仍可直接輸入。

### 互動完成後直接得到下次的 CLI

互動精靈在所有最終設定都解析完成後、正式執行或確認前，先印出等價的 ACME Helper 指令：

```text
下次可直接執行：
  acme issue --server letsencrypt --keylength ec-256 --dns dns_namesilo --dnssleep 120 --output-layout minimal --output-root /etc/ssl/acme --cert-name example.com 'example.com *.example.com'
確認開始簽發？ [y/N]:
```

下一次可直接複製該行，不必重新走精靈或記參數。version/defaults/status/providers/hooks 等唯讀任務也會顯示對應快捷指令；本來就以 CLI 呼叫的專業模式維持安靜，不重複輸出自己。

快捷指令採 shell-safe quoting。Token、Password、EAB HMAC、DNS credential 與 deploy/notify hook 環境值**不會展開到畫面或 shell history**；有安全 stdin 路徑時使用 `--password-stdin`／`--eab-hmac-stdin`，無通用安全輸入方式的原生秘密參數只顯示 `[hidden]` 並附警告。中央顯示層還會再次遮蔽已知 `--password`／`--eab-hmac-key`。

撤銷、刪除、停用帳號、卸載等破壞性操作的預覽刻意**不加入 `--yes`**，所以下次複製後仍保留確認。版本 switch/rollback 這類非互動 CLI 會在預覽旁明確提醒重新執行即會直接執行。

## 真機出錯時：直接產生可貼給 ChatGPT 的修復交接

真機不需要安裝 Codex。遇到問題時執行：

```bash
acme diagnose
```

在 TTY 會詢問三件事：是否包含管理中網域名稱、是否附上已保存的錯誤 log、是否執行套件內的離線回歸測試。預設全部採較保守選項；非互動環境則直接產生不含網域、不含 log、且不執行測試的診斷提示詞。

若剛才的終端輸出已保存：

```bash
acme diagnose --log /tmp/acme-error.log
```

要直接輸出到 stdout：

```bash
acme diagnose --stdout
```

完整原始套件上可選擇執行**有界診斷回歸**（消融／對抗／UX/i18n／診斷本身，不含耗時 311 條 canonical flow matrix）：

```bash
acme diagnose --run-tests
```

安裝到系統的精簡 runtime 通常沒有 `tests/`，這時會明確標 `NOT_RUN`，不會假裝測過。診斷提示詞也會列出 `offline_omitted_suites=flow_matrix`；完整發行驗收仍使用 `python3 -S tests/run_all.py`。離線測試會使用獨立 HOME/TMPDIR，且不繼承真機的 ACME/provider credential、account path 或 `BASH_ENV/PYTHONPATH`，避免測試碰到正式資料或把秘密寫進測試 log。

診斷交接會收集 Helper 版本與 SHA-256、Python/OS、acme.sh 版本與相容性、非秘密預設值、設定檔 metadata、DNS provider configured/runtime-ready 狀態、憑證數量、cron 狀態，以及使用者**明確指定**的 log tail。預設不列網域名稱，也不會自動讀任何 log；需要網域證據時才使用：

```bash
acme diagnose --include-domains
```

Token、Key、Password、EAB HMAC、Authorization/Cookie、URL 密碼、常見 provider ID、private key block 等會先遮蔽。輸出檔權限固定為 `0600`，且拒絕覆寫既有檔案或讀取 symlink log。**自動遮蔽不是資料外洩保證，送出前仍要人工看一次。**

一般 Helper 命令非零退出時也會提示 `acme diagnose`；如果要把當時的完整終端輸出一起交接，先把輸出保存成檔案再用 `--log FILE`。產生後把提示詞檔內容貼回 ChatGPT；若需要修改程式碼，再一併提供相同版本的 ACME Helper 壓縮包。

詳細流程見 [CHATGPT_REPAIR_HANDOFF.md](CHATGPT_REPAIR_HANDOFF.md)。

## 語言

```bash
acme --lang zh-TW
acme --lang en
acme language en
acme language zh-TW
```

`--lang` 放在 Helper 指令前，只影響這次執行；`acme language` 儲存偏好。優先序是 `--lang` → `ACME_HELPER_LANG`（兼容 `ACME_LANG`）→ 設定檔 `[ui] language` → `zh-TW`。

翻譯 Helper 自己的選單、提示、說明及錯誤。不翻譯指令名稱、參數、網域、路徑、Token、機器讀取欄位，也不改寫 acme.sh 或外部 hook 的輸出。上游 metadata、未知新功能說明與安裝前置檢查可能仍為英文；這是明確的翻譯範圍。

缺少／無法解析 JSON 語系檔時退回英文。新增翻譯請看 [TRANSLATING.md](TRANSLATING.md)。

## 快速指令與預設

```bash
acme "example.com *.example.com"
acme "*.aa.bb *.dd.bb *.gg.bb" 100
acme -dns dns_cf -name web-prod "example.com *.example.com"
acme -out /srv/ssl -format nginx "example.com *.example.com"
acme config defaults
acme defaults
```

| 設定 | 內建預設 |
|---|---|
| CA | letsencrypt |
| DNS | dns_namesilo |
| 等待秒數 | 120 |
| 金鑰 | ec-256 |
| 輸出根目錄 | /etc/ssl/acme |
| 格式 | minimal |
| 新安裝 cron | off |

簽發參數優先序：CLI → 對應環境變數 → `[defaults]` → 內建值。`acme config defaults` 不會把暫時環境變數誤存成永久值。

`*.example.com` 不涵蓋 `example.com` 或多一層的 `www.api.example.com`。一個命令裡的所有網域共用一張憑證與私鑰。

預設輸出：

```text
/etc/ssl/acme/example.com/
  key.pem
  fullchain.pem
  domains.txt
```

格式：`minimal` 為 key/fullchain；`full` 再加 cert/ca；`nginx` 為 privkey/fullchain；上述三者保留 `domains.txt`。`none` 不建立外部輸出。PEM 位置由 acme.sh 保存並於續期更新；`domains.txt` 是 Helper 成功 issue/install 後產生的清單，不是憑證資料庫，原生重簽時不會自動同步。

Helper 會拒絕覆寫**已被另一張管理中憑證占用**的 PEM 輸出路徑。RSA、ECC 或不同主網域要共存時，請用不同 `-name`／`-out`；不要期待自動改名。

## DNS、憑證與日常維運

```bash
acme providers
acme providers cloud
acme config dns_namesilo
acme config dns_cf
acme status --all
acme certs
acme certs read "*.aa.bb"
acme certs update "*.aa.bb"
acme certs delete "*.aa.bb" --yes
acme cron status
acme cron on
acme cron off
acme cron run
acme diagnose
```

憑證清單列出全部 SAN 與金鑰類型。更新沿用 acme.sh 已存的 DNS provider、網域、CA 及輸出位置，不重新猜測；同名 RSA/ECC 憑證請由清單編號選擇。`update` 是續期；增刪 SAN 要用完整最終清單重新 issue。`delete` 僅移除管理，不等於撤銷或清除私鑰。

DNS/deploy/notify 依實際安裝樹動態發現。有 `Options/OptionsAlt` metadata 才能產生可靠的 DNS 認證欄位精靈；缺 metadata 的 provider 會明確標示 `manual-schema`。`configured` 只表示本機存在非空設定，**不是 API 認證成功**。runtime-only 認證資料仍需由實際執行及排程環境提供。

## 安裝、版本與進階功能

```bash
acme install
acme install --email admin@example.com --version 3.1.4
acme install --branch master --no-cron
acme version --full
acme versions
acme update
acme switch master
acme rollback
acme uninstall
acme certs --help
acme deploy
acme notify
acme account
acme csr
acme export
acme ca
acme hooks deploy
acme native
acme native --help
```

`acme update` 更新的是 acme.sh，不是 Helper；無參數時使用套件固定目標。Helper 升級用新版套件的 `install.sh`。`acme uninstall` 委派 upstream，不額外清除憑證、帳號資料或 Helper。

`version` 為基本介面探測；`version --full` 再執行唯讀 list/info 檢查。`probed-compatible` 不代表 DNS/CA 實機通過。切版備份只含程式資產，不含私鑰／憑證；請另行備份資料。v1.10.1 新格式備份會記錄哪些程式資產原本存在，回滾也會移除切版後才新增的 `dnsapi/deploy/notify` 目錄；舊備份沒有 `assets=` 時則採保守恢復。回滾仍不是跨多個目錄的斷電安全交易，勿與其他升級／續期作業同時執行。

所有 Helper 子命令都有離線 `--help`；`acme help certs` 也可使用。進階選單保留 webroot/standalone/ALPN/Apache/Nginx/手動 DNS 等模式，以及帳號、CSR、匯出、deploy、notify、CA、原生參數編輯器。不把 private shell 函式當公開功能。

## 自訂執行環境

`ACME_SH_BIN` 指定上游程式。未明確給 `LE_WORKING_DIR` 時，Helper 使用該程式的實際目錄；明確指定的 `LE_WORKING_DIR`／`LE_CONFIG_HOME` 保留。`ACME_ACCOUNT_CONF` 會傳給上游 `ACCOUNT_CONF_PATH`，避免設定與簽發讀不同檔案。

自訂環境變數只保證本次子程序使用；獨立 cron/service 必須提供相同環境，或依 upstream 正式安裝方式持久化 config home。Helper 不會自動改寫其他人的排程。

## 支援與驗證

實測：Linux、Bash 5.2.37、Python 3.13.5。程式保留 Python 3.6+ 語法及 subprocess 相容目標，**未在 Python 3.6 真直譯器或各發行版逐一實測**。測試套件需 Python 3.7+。

```bash
python3 -S tests/run_all.py --report-dir /tmp/acme-helper-tests
```

套件附帶本輪實際報告；`tests/review_v110.py` 專門驗證診斷交接、遮蔽、唯讀邊界與雙語流程。案例數不等於程式碼分支覆蓋率；未將所有外部 DNS API、CA、部署目標、通知服務的真實驗證列為完成。
