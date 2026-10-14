Antigravity Local Patcher v0.2.0 adds CLI support alongside Antigravity 2.0 /
Manager and IDE, with an English interface and a Russian README.

Download the archive for your operating system and architecture. Extract the
entire folder, close Antigravity and launch `AntigravityPatcher.exe` (Windows)
or `./AntigravityPatcher` (Linux/macOS). Choose **1 — Patch all detected installations**.
Choose **3 — Restore originals** to restore verified backups.

The release includes native Windows x64, Linux x64/ARM64 and macOS Intel/Apple
Silicon packages plus SHA256 checksums. Python installation is not required.
These are portable folder bundles; keep `_internal` next to the executable.

Known local signatures are required. Unknown/ambiguous builds are left unchanged;
patching a local gate does not establish server-side eligibility. Each native
package is smoke-tested in CI. The real Google account and model access are not
part of the fixture tests. macOS packages are not notarized.

Russian instructions: README.md inside each archive and in the repository.
