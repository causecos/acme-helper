# Versioning policy

ACME Helper 使用 [Semantic Versioning](https://semver.org/) 的 `MAJOR.MINOR.PATCH`。

## 標示規則

| 對象 | 格式 | 範例 |
|---|---|---|
| 程式執行期版本 | `X.Y.Z` | `1.11.0` |
| CLI 短版顯示 | `ACME Helper vX.Y.Z` | `ACME Helper v1.11.0` |
| Git tag / GitHub Release | `vX.Y.Z` | `v1.11.0` |
| Release 壓縮包 | `acme-helper-vX.Y.Z.tar.gz` | `acme-helper-v1.11.0.tar.gz` |
| 上游 acme.sh | `acme.sh X.Y.Z` / `acme_sh_*` | `acme_sh_version=3.1.4` |

`v` 只用在人類可讀的 release/tag 標籤，不放進 Python `VERSION` 值。

## 單一來源

`acme_cli.py` 的 `VERSION` 是 Helper 的執行期版本來源。`acme --version` 與 `acme version` 都從這個值輸出。

README 不再把「目前版本」寫進標題或大量安裝命令，避免每次 release 產生無意義版本漂移。歷史版本只應出現在：

- Git tag / GitHub Release；
- `CHANGELOG.md`；
- 特定版本的 audit/test 歷史證據。

測試可以明確 pin 預期 release 版本，用來防止忘記 bump；這是驗證契約，不是第二個 runtime version source。

## 何時升版本

- **PATCH**：向後相容的 bug fix、安全修正、文件更正，沒有新的公開能力。
- **MINOR**：向後相容的新功能、公開 CLI/UX 能力、可選行為或重要操作流程重構。
- **MAJOR**：刻意移除/改變既有公開 CLI、設定、檔案格式或其他需要使用者遷移的不相容變更。

保留舊命令作 alias 時，通常不視為 MAJOR；若 alias 之後要移除，必須先在 changelog 記錄 deprecation，再於 major release 移除。

## Helper 與 acme.sh 版本不可混用

ACME Helper 自身版本只描述 Helper 程式。上游另有：

- `acme_sh_version`：目前偵測到的上游版本；
- `acme_sh_stable_target`：Helper 預設安裝/更新所 pin 的穩定目標；
- `acme_sh_interface_reference`：Helper 用來比對介面能力的參考版本。

因此「ACME Helper v1.11.0」不代表「acme.sh v1.11.0」，也不代表 bundled acme.sh；本專案並不內嵌上游。
