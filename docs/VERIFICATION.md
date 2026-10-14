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

Linux/macOS executables have **not** been built on this host. All five native
GitHub CI builds subsequently completed successfully, including their packaged
runtime smoke tests. Real macOS application signing requires validation against
an installed Antigravity app; mocked
signing failure tests validate rollback logic, not Apple's signing behavior.

## First native CI run and test correction

The first GitHub release run built and smoke-tested Windows x64 and both Linux
architectures successfully. Both macOS jobs stopped at the Test step. The old
Windows-backup test incorrectly expected import to succeed on macOS, where the
runtime intentionally refuses that unsigned legacy format.

The Windows legacy test now explicitly exercises the Windows branch; a separate
test verifies that macOS refuses legacy import without changing the target.
All 14 test methods pass with Windows/Linux/macOS platform branches simulated
locally (the POSIX permissions test remains skipped on the Windows host). This
does not replace rerunning the native macOS jobs. Actions versions are pinned
to current releases using the Node.js 24 runtime.

The subsequent manual release workflow passed all native jobs and created a
draft, which was published. Tag publication then triggered another build: all
five native jobs passed, but the draft step failed because its guard used a
failing shell test when the release was already public. That branch now exits
successfully without uploading or replacing any published assets.
Three tests execute the actual release shell step with a fake gh command:
published release is unchanged, an existing draft receives assets, and a missing
release is created as a draft. The updated local suite contains 17 methods,
with 16 passing and the POSIX-only permission check skipped on Windows.

The earlier Windows PowerShell IDE patch was reported working by the requester.
This new build has not been exercised against the friend's real CLI/Manager
installations or Google account. Fixture checks do not prove service eligibility.
