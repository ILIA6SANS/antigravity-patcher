# Verification record — 2026-10-14

Prepared version: **0.2.0**.

Local host: Windows 10 x64 (10.0.19045), CPython 3.10.11, PyInstaller 6.19.0.

- Unit suite: 13 test methods, 12 passed and 1 POSIX permission test skipped.
- Binary transaction cases cover PE, ELF and Mach-O fixtures, both x64 and ARM64,
  for CLI and Manager. Only intended bytes are changed and restore is exact.
- IDE tests cover byte preservation, repeat application and legacy PowerShell backups.
- Guard tests cover ambiguous signatures, non-executable data, corrupted backups,
  app updates, tampered target paths and rollback after a write/signing failure.
- The Windows folder bundle passes `--version` and the isolated `--self-test`.
- Windows file properties contain ProductVersion 0.2.0 and FileVersion 0.2.0.0.
- Workflow YAML syntax and repository Markdown links are checked locally.

Linux/macOS executables have **not** been built on this host. Native CI jobs
must run in GitHub before those assets can be published. POSIX permissions and
real macOS code-signing operations require their native environments; mocked
signing failure tests validate rollback logic, not Apple's signing behavior.

The earlier Windows PowerShell IDE patch was reported working by the requester.
This new build has not been exercised against the friend's real CLI/Manager
installations or Google account. Fixture checks do not prove service eligibility.
