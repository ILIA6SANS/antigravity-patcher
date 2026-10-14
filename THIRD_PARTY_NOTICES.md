# Third-party notices

`src/antigravity_patcher/native.py` contains selected code adapted from:

- Project: [QNIX-Dev/eligibility-antigravity-patcher](https://github.com/QNIX-Dev/eligibility-antigravity-patcher)
- Source revision: `d3e447fb9c5bebb6e15146620105055bae3f6628`
- Original file: `manager.py`, Git blob `d2033fc105c7c83ce58837d400b14223bbc67770`
- Copyright: (c) 2026 QNIX-Dev
- License: MIT, reproduced in [LICENSE](LICENSE)

Adapted portions: executable-format parsers, architecture-specific eligibility
signatures, installation discovery and macOS signing/snapshot helpers. The
snapshot manifest validator is restricted to the expected signing paths.

Account storage, token access, quota monitoring, network code and the upstream
terminal UI are excluded. The transaction engine and English interface in this
repository are separate implementations. IDE replacements preserve file length.

Native release packages include the Python runtime and PyInstaller support
files. Python uses the PSF license; PyInstaller uses GPL with its bootloader
exception. Their license texts are included in the release's `licenses/` folder.
Build dependency: PyInstaller 6.19.0. This project is not affiliated with Google.
