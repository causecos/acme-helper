# Changelog / 變更紀錄

所有 ACME Helper 對使用者可見的重要變更都記錄於此。本專案遵循 Semantic Versioning（語意化版本）。  
All notable user-visible changes to ACME Helper are recorded here. The project follows Semantic Versioning.

## [1.11.1] - 2026-09-12

### 修正 / Fixed

- 當遮蔽後的診斷資料在暫存後建立失敗、runtime 必須保留私人 raw fallback 時，仍保留原始憑證簽發 exit code。  
  Preserve the original certificate-issuance exit code when redacted diagnostic creation fails after staging and the runtime must retain a private raw fallback.
- `--lang=en issue`、`--lang=zh-TW issue` 與對應的 `quick` 相容別名，現在會和 `--lang VALUE` 一樣進入相同的自動 issue-failure diagnostic wrapper。  
  Route `--lang=en issue`, `--lang=zh-TW issue`, and the equivalent `quick` compatibility alias through the same automatic issue-failure diagnostic wrapper as `--lang VALUE`.
- 移除 launcher 中過期的硬編版本註解，讓 runtime version output 維持版本資訊的唯一來源。  
  Remove the stale hard-coded launcher version comment so runtime version output remains the version source of truth.

## [1.11.0] - 2026-09-12

### 變更 / Changed

- 將憑證簽發收斂為單一流程：主選單與 `acme issue` 現在使用同一套 wizard。  
  Consolidated certificate issuance into one workflow: the main menu and `acme issue` now use the same wizard.
- `acme quick` 僅保留為 `acme issue` 的向後相容別名，不再作為獨立文件化流程。  
  Kept `acme quick` only as a backward-compatible alias to `acme issue`; it is no longer a separate documented workflow.
- 多憑證 `separate` 模式的輸出結構改為 `<output>/<cert-name>/<domain>/`。  
  Changed multi-certificate `separate` output layout to `<output>/<cert-name>/<domain>/`.
- `separate` 模式下，`--cert-name` 現在代表父層憑證群組目錄，不再被拒絕。  
  In separate mode, `--cert-name` now names the parent certificate group instead of being rejected.
- 互動式 DNS 簽發在缺少本機 credential 時，可直接沿用既有的安全 provider credential 設定流程。  
  Interactive DNS issuance can reuse the existing secure provider-credential configuration flow when local credentials are missing.
- 詳細版本輸出新增 `helper_version=`，同時保留 `wrapper_version=` 作為相容欄位。  
  Added `helper_version=` to detailed version output while retaining `wrapper_version=` for compatibility.
- 專案文件重構為精簡 README、完整使用說明、Changelog 與明確版本規則。  
  Refactored project documentation into concise README files, detailed usage guides, this changelog, and an explicit versioning policy.

### 相容性 / Compatibility

- 既有直接簽發語法與 `merged` 預設行為維持不變。  
  Existing direct issuance syntax and `merged` default behavior remain unchanged.
- 既有 `acme quick ...` 腳本仍可透過相容別名繼續運作。  
  Existing `acme quick ...` scripts continue to work through the compatibility alias.

## [1.10.1]

### 修正 / Fixed

- 強化版本 rollback：新版備份會同時正確還原 `acme.sh`、`dnsapi`、`deploy`、`notify` 程式資產原本存在或不存在的狀態。  
  Hardened version rollback so new-format backups restore both presence and prior absence of `acme.sh`, `dnsapi`, `deploy`, and `notify` program assets.
- 收緊版本漂移判定：舊版介面能力不足時會拒絕，不再只相信版本字串。  
  Tightened version-drift evidence so reduced older interfaces are rejected instead of trusting a version string alone.

## [1.10.0]

### 新增 / Added

- 新增遮蔽敏感資訊、唯讀的 `acme diagnose`，用於真機故障交接。  
  Added the redacted, read-only `acme diagnose` handoff for field troubleshooting.
- 新增有界的離線 diagnostic regression，以及 supplied log 的 prompt-injection／secret-redaction 邊界測試。  
  Added bounded offline diagnostic regression and prompt-injection/secret-redaction boundaries for supplied logs.

## [1.9.0]

### 變更 / Changed

- 標準化 guided operations：在正式執行或確認前先顯示 shell-safe、可重複使用的 CLI。  
  Standardized guided operations to print a shell-safe reusable CLI before final execution or confirmation.
