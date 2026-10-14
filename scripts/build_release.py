"""Build and smoke-test a native release on the current OS/architecture."""
from __future__ import annotations
import argparse
import hashlib
import json
from importlib.metadata import distribution
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from antigravity_patcher import __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "release-assets")
    args = parser.parse_args()
    machine = platform.machine().lower()
    arch = {"amd64":"x64", "x86_64":"x64", "arm64":"arm64", "aarch64":"arm64"}.get(machine)
    os_name = {"win32":"windows", "linux":"linux", "darwin":"macos"}.get(sys.platform)
    if not arch or not os_name:
        raise SystemExit(f"Unsupported build host: {sys.platform} / {machine}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for directory in (ROOT / "build", ROOT / "dist"):
        if not directory.resolve().is_relative_to(ROOT):
            raise SystemExit("Build directory escaped the repository root")
    build_env = os.environ.copy()
    build_env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build/pyinstaller-cache")
    metadata = ["--version-file", str(ROOT / "scripts/windows-version.txt")] if os_name == "windows" else []
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", *metadata,
                    "--name", "AntigravityPatcher", "--paths", str(ROOT / "src"),
                    "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build/pyinstaller"),
                    "--specpath", str(ROOT / "build"), str(ROOT / "scripts/entrypoint.py")], check=True, cwd=ROOT, env=build_env)
    bundle = ROOT / "dist/AntigravityPatcher"
    executable = bundle / ("AntigravityPatcher.exe" if os_name == "windows" else "AntigravityPatcher")
    subprocess.run([str(executable), "--version"], check=True)
    subprocess.run([str(executable), "--self-test"], check=True)
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, bundle / name)
    licenses = bundle / "licenses"
    licenses.mkdir(exist_ok=True)
    python_license = next((p for p in (Path(sys.base_prefix)/"LICENSE.txt", Path(sys.base_prefix)/"LICENSE",
                                      Path(sys.base_prefix)/"lib/python3.10/LICENSE.txt") if p.is_file()), None)
    if python_license:
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    else:
        # setup-python framework layouts can differ from the local interpreter.
        import sysconfig
        candidate = Path(sysconfig.get_path("stdlib"))/"LICENSE.txt"
        if not candidate.is_file():
            raise SystemExit("Python runtime license was not found; refusing to package an incomplete release")
        shutil.copy2(candidate, licenses / "Python-LICENSE.txt")
    packager = distribution("pyinstaller")
    copying = next((packager.locate_file(f) for f in (packager.files or []) if f.name == "COPYING.txt"), None)
    if not copying or not copying.is_file():
        raise SystemExit("PyInstaller license was not found")
    shutil.copy2(copying, licenses / "PyInstaller-COPYING.txt")
    info = {"version":__version__, "platform":os_name, "architecture":arch,
            "python":platform.python_version(), "smoke_test":"passed", "format":"onedir"}
    (bundle / "BUILD_INFO.json").write_text(json.dumps(info, indent=2)+"\n", encoding="utf-8")
    name = f"antigravity-patcher-v{__version__}-{os_name}-{arch}"
    if os_name == "windows":
        archive = output / (name + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for file in sorted(bundle.rglob("*")):
                if file.is_file():
                    z.write(file, file.relative_to(bundle.parent))
    else:
        archive = output / (name + ".tar.gz")
        # tar preserves the runtime's symlinks and executable permissions.
        with tarfile.open(archive, "w:gz", dereference=False) as tar:
            tar.add(bundle, arcname=bundle.name)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    print(f"Release: {archive}\nSHA256: {checksum}")


if __name__ == "__main__":
    main()
