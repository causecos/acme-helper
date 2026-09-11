# ACME Helper 完整使用說明

回到 [README](../README.md)。

## 1. 安裝 Helper

```bash
sha256sum -c SHA256SUMS
sudo ./install.sh
```

非 root：

```bash
PREFIX="$HOME/.local" ./install.sh
```

Helper 不會因自身安裝而自動安裝 acme.sh。需要上游時使用：

```bash
acme install
```

新安裝 cron 預設關閉。

## 2. 單一簽發入口

互動：

```bash
acme
```

選 1「簽發憑證」，或直接：

```bash
acme issue
```

兩者進入相同精靈。舊的 `acme quick` 僅是 `acme issue` 的相容別名，不再有獨立 UI、預設或執行路徑。

精靈依序處理：網域 → 驗證方式 → 金鑰 → 輸出 → 進階上游參數。正式執行前會顯示可複製的 shell-safe Helper CLI。

## 3. 多網域：合併或分離

輸入多個名稱後可選：

- `merged`：一張憑證、一把私鑰、多個 SAN。這是預設。
- `separate`：每個輸入名稱各一張憑證與私鑰。

```bash
acme issue --cert-mode merged "example.com *.example.com"
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
```

### separate 輸出規則

外部輸出使用：

```text
<output-root>/<cert-name>/<domain>/
```

例如：

```text
/etc/ssl/acme/production/example.com/
/etc/ssl/acme/production/wildcard-example.com/
/etc/ssl/acme/production/api.example.com/
```

`--cert-name` 在 merged 模式是該張憑證的輸出目錄；在多張 separate 模式則是整批憑證的父目錄。若 separate 未指定 `--cert-name`，預設取第一個網域的安全化名稱。

`*.example.com` 的子目錄使用 `wildcard-example.com`，避免與 `example.com` 撞名；若安全化後仍撞名，依序加 `-2`、`-3`。

在第一張送出前會檢查本機已知輸出路徑衝突。批次第一個上游失敗會停止後續請求；已成功的憑證不自動撤銷或移除。

## 4. 驗證方式

同一個 `acme issue` 精靈支援：

- DNS API（預設）
- webroot
- standalone
- ALPN
- stateless
- Apache
- Nginx
- manual DNS
- DNS persist

萬用字元通常需要 DNS 驗證。DNS API provider 由實際安裝的 acme.sh `dnsapi` 動態發現。

## 5. DNS credential

列出 provider：

```bash
acme providers
acme providers cloud
```

安全輸入 credential：

```bash
acme config dns_namesilo
acme config dns_cf
```

credential 不接受直接放在 Helper CLI argv。互動式 DNS 簽發偵測到本機尚未設定 provider 時，也可直接進入相同安全設定流程。

## 6. 憑證管理

```bash
acme certs
acme certs list
acme certs read DOMAIN
acme certs update DOMAIN
acme certs renew-all
acme certs install DOMAIN
acme certs deploy DOMAIN
acme certs revoke DOMAIN
acme certs deactivate-auth DOMAIN
acme certs delete DOMAIN
```

acme.sh 的 managed state 是權威來源；`domains.txt` 只保存 Helper 當次要求的名稱，不是第二套憑證資料庫。

## 7. cron、deploy、notify

```bash
acme cron status
acme cron on
acme cron off
acme cron run
acme deploy
acme notify
acme hooks deploy
acme hooks notify
```

Deploy/notify hook 可能執行 shell 或連線外部服務；正式使用前應確認上游 hook 文件與所需環境變數。

## 8. 預設值與語言

```bash
acme config defaults
acme defaults
acme language zh-TW
acme language en
acme --lang en issue
```

設定優先序：CLI → 對應環境變數 → Helper 設定檔 → 內建預設。

## 9. 版本與相容性

```bash
acme --version
acme version
acme version --full
acme versions
acme update
acme switch TAG_OR_BRANCH
acme rollback
```

Helper 版本與 acme.sh 版本是兩個不同命名空間；詳細規則見 [VERSIONING.md](VERSIONING.md)。

## 10. 真機故障診斷

```bash
acme diagnose
acme diagnose --log /tmp/acme-error.log
acme diagnose --stdout
```

預設不列 managed domain、不自動讀 log、不執行離線測試。需要時明確加入：

```bash
acme diagnose --include-domains
acme diagnose --run-tests
```

輸出會遮蔽已知 Token/Key/Password/EAB HMAC、Authorization/Cookie、URL 密碼、常見 provider ID 與 private key block。指定 log 仍須人工檢查；log 內容一律視為不可信資料，不是模型指令。

## 11. 原生 acme.sh 功能

```bash
acme native
acme native --help
```

Helper 會從已安裝的 acme.sh help/completion 動態取得命令與參數，不維護一份永遠落後的完整副本。對於 Helper 尚未提供專用 UX 的功能，使用 native 入口。
