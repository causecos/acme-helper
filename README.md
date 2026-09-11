# ACME Helper

[English](README.en.md) · [完整使用說明](docs/USAGE.md) · [版本規則](docs/VERSIONING.md) · [Changelog](CHANGELOG.md) · [功能覆蓋](FEATURE_COVERAGE.md) · [稽核基線](AUDIT.md)

**讓 acme.sh 不必靠記憶大量參數才能安全維運。** ACME Helper 是一個偏向人類操作的 CLI 前端：提供憑證簽發、DNS API 設定、SAN/續期/部署、版本管理與可遮蔽敏感資訊的診斷交接，同時保留 acme.sh 原生能力。

> ACME Helper 是獨立、非官方的第三方專案，不隸屬於 acme.sh / acmesh-official。本倉庫不重新實作 ACME 協定，也不內嵌 acme.sh 原始碼；真正的 ACME、DNS 驗證與憑證狀態仍由上游 acme.sh 負責。ACME Helper 採 MIT License；acme.sh 依其自身授權發布。

## 適合誰

- 第一次維護 TLS 憑證，不想背 DNS provider、SAN、輸出與續期參數的人。
- 需要可預測 CLI、部署/通知 hook、版本切換與診斷資訊的系統管理者。
- 希望互動操作最後能得到可複製 CLI，而不是只能重新走一次選單的人。

## 核心能力

- **單一簽發入口**：互動選單與 `acme issue` 使用同一套流程；舊的 `acme quick` 僅保留為相容別名，不再是第二套功能。
- **多網域模式**：`merged` 將所有名稱放在一張 SAN 憑證；`separate` 每個名稱各簽一張。
- **DNS provider 動態發現**：從已安裝的 acme.sh `dnsapi` 取得 provider，不維護第二份固定清單。
- **憑證生命週期**：列出 SAN、續期、安裝、部署、撤銷、停用授權與移除管理。
- **版本與相容性**：安裝、更新、指定 tag/branch、切換、回滾及介面探測。
- **診斷交接**：`acme diagnose` 產生遮蔽敏感資訊的唯讀診斷資料，可交給 ChatGPT 分析。
- **雙語介面**：繁體中文與英文；指令、參數、路徑與上游錯誤保持原樣。

## 安裝

下載 release 壓縮包後：

```bash
sha256sum -c SHA256SUMS
sudo ./install.sh
```

非 root 安裝：

```bash
PREFIX="$HOME/.local" ./install.sh
```

需要 Python 3.6+；目前以 Linux 為正式測試平台。Helper 安裝與 acme.sh 安裝是兩件事，不會因安裝 Helper 就自動下載或改動上游。

## 第一次使用

```bash
acme
```

主選單第一項就是「簽發憑證」。DNS、webroot、standalone、ALPN、Apache/Nginx、手動 DNS 與 DNS persist 都從同一個簽發精靈進入。

熟悉 CLI 後可直接：

```bash
acme issue "example.com *.example.com"
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
acme certs
acme config dns_namesilo
acme cron status
acme version --full
```

舊版腳本中的 `acme quick ...` 仍會轉到 `acme issue ...`，但新文件與選單不再把它當成獨立功能。

## 多網域憑證

### 合併：`merged`（預設）

```bash
acme issue --cert-mode merged "example.com *.example.com api.example.com"
```

一次呼叫上游 `--issue`，所有名稱共用一張憑證與私鑰。

### 分離：`separate`

```bash
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
```

每個名稱各自呼叫一次上游 `--issue`。外部輸出依群組收納：

```text
/etc/ssl/acme/
└── production/
    ├── example.com/
    │   ├── key.pem
    │   ├── fullchain.pem
    │   └── domains.txt
    ├── wildcard-example.com/
    │   ├── key.pem
    │   ├── fullchain.pem
    │   └── domains.txt
    └── api.example.com/
        ├── key.pem
        ├── fullchain.pem
        └── domains.txt
```

也就是 `<output>/<cert-name>/<domain>/`。萬用字元目錄使用 `wildcard-` 前綴，避免與 base domain 撞名；其他碰撞會以 `-2`、`-3` 遞增。若未指定 `--cert-name`，群組名稱預設取第一個網域的安全化名稱。

批次在第一個簽發錯誤時停止。已成功的憑證保留在 acme.sh 管理中，不假裝對 CA/DNS 外部狀態做交易式回滾。

## 預設值

| 項目 | 內建預設 |
|---|---|
| CA | Let's Encrypt |
| DNS | `dns_namesilo` |
| DNS 等待 | 120 秒 |
| 金鑰 | `ec-256` |
| 輸出根目錄 | `/etc/ssl/acme` |
| 輸出格式 | `minimal` |
| 新安裝 cron | off |

簽發設定優先序：CLI → 環境變數 → Helper 設定檔 → 內建值。

## 安全邊界

ACME Helper 會接觸 DNS/API credential、私鑰路徑、檔案寫入、子程序、cron、deploy/notify hook 與網路動作，因此預覽與診斷刻意避免把秘密展開到 shell history。`acme diagnose` 的 log 內容被視為**不可信資料，不是 AI 指令**；自動遮蔽仍不是資料外洩保證，分享前應人工檢查。

完整威脅與驗證證據見 [AUDIT.md](AUDIT.md) 與 [FEATURE_COVERAGE.md](FEATURE_COVERAGE.md)。

## 文件

- [docs/USAGE.md](docs/USAGE.md)：完整安裝、簽發、憑證、排程、hook、版本與診斷操作。
- [docs/VERSIONING.md](docs/VERSIONING.md)：Helper 版本、Git tag、release archive 與 acme.sh 上游版本如何區分。
- [CHANGELOG.md](CHANGELOG.md)：使用者可見變更。
- [FEATURE_COVERAGE.md](FEATURE_COVERAGE.md)：功能入口、測試證據與限制。
- [AUDIT.md](AUDIT.md)：已完成的安全／失敗原子性／相容性稽核基線。
- [CHATGPT_REPAIR_HANDOFF.md](CHATGPT_REPAIR_HANDOFF.md)：真機故障交接格式。
- [CODEX_LIVE_TEST_PROMPT.md](CODEX_LIVE_TEST_PROMPT.md)：需要外部 DNS/CA 的實機驗收提示詞。
- [TRANSLATING.md](TRANSLATING.md)：翻譯規則。

## 版本

執行：

```bash
acme --version
acme version --full
```

Helper 採 Semantic Versioning。程式內的 `VERSION` 是執行期版本來源；Git tag / GitHub Release 使用 `vX.Y.Z`。acme.sh 自身版本會以 `acme_sh_*` 欄位獨立顯示，不能把兩者混成同一個版本號。詳細規則見 [docs/VERSIONING.md](docs/VERSIONING.md)。

## License

MIT. See [LICENSE](LICENSE).
