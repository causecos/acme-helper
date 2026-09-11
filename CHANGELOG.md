# Changelog

All notable user-visible changes to ACME Helper are recorded here. The project follows Semantic Versioning.

## [1.11.0] - 2026-09-12

### Changed

- Consolidated certificate issuance into one workflow: the main menu and `acme issue` now use the same wizard.
- Kept `acme quick` only as a backward-compatible alias to `acme issue`; it is no longer a separate documented workflow.
- Changed multi-certificate `separate` output layout to `<output>/<cert-name>/<domain>/`.
- In separate mode, `--cert-name` now names the parent certificate group instead of being rejected.
- Interactive DNS issuance can reuse the existing secure provider-credential configuration flow when local credentials are missing.
- Added `helper_version=` to detailed version output while retaining `wrapper_version=` for compatibility.
- Refactored project documentation into concise README files, detailed usage guides, this changelog, and an explicit versioning policy.

### Compatibility

- Existing direct issuance syntax and `merged` default behavior remain unchanged.
- Existing `acme quick ...` scripts continue to work through the compatibility alias.

## [1.10.1]

- Hardened version rollback so new-format backups restore both presence and prior absence of `acme.sh`, `dnsapi`, `deploy`, and `notify` program assets.
- Tightened version-drift evidence so reduced older interfaces are rejected instead of trusting a version string alone.

## [1.10.0]

- Added the redacted, read-only `acme diagnose` handoff for field troubleshooting.
- Added bounded offline diagnostic regression and prompt-injection/secret-redaction boundaries for supplied logs.

## [1.9.0]

- Standardized guided operations to print a shell-safe reusable CLI before final execution or confirmation.
