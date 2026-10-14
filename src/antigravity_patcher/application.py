"""English terminal interface and command-line entry point."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from . import __version__, engine, native


def discover(overrides: dict[str, str]) -> list[engine.Target]:
    native._reg_install_dirs.cache_clear()
    native._roots.cache_clear()
    finders = {"cli": native.cli_default_paths, "manager": native.manager_default_bins, "ide": native.ide_default_mains}
    targets = []
    for kind, finder in finders.items():
        paths = [overrides[kind]] if overrides.get(kind) else finder()
        seen = set()
        for path in paths:
            actual = Path(path).expanduser().resolve()
            if not actual.is_file():
                if overrides.get(kind):
                    raise OSError(f"{kind} file does not exist: {actual}")
                continue
            if actual not in seen:
                targets.append(engine.Target(kind, actual))
                seen.add(actual)
    return targets


def require_closed() -> None:
    # This is conservative: do not patch while any Antigravity component is active.
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                           errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode:
            raise OSError("Could not inspect running processes. Close Antigravity and try again.")
        names = {row[0].lower() for row in csv.reader(io.StringIO(r.stdout)) if row}
        active = names & {"antigravity.exe", "antigravity ide.exe", "antigravity-ide.exe", "language_server.exe", "agy.exe"}
    else:
        r = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, errors="replace")
        if r.returncode:
            raise OSError("Could not inspect running processes. Close Antigravity and try again.")
        active = {Path(line.strip()).name.lower() for line in r.stdout.splitlines()} & {
            "antigravity", "antigravity ide", "antigravity-ide", "language_server", "agy"}
    if active:
        raise OSError("Close Antigravity and its background processes first: " + ", ".join(sorted(active)))


def run(action: str, selected: list[str], overrides: dict[str, str], backup_root: Path,
        allow_library_validation: bool = False) -> int:
    targets = [t for t in discover(overrides) if t.kind in selected]
    if not targets:
        print("[error] No installations found. Set --path-cli, --path-manager or --path-ide to the target FILE.")
        return 1
    if action != "status":
        require_closed()
    if action == "status":
        failed = False
        for t in targets:
            state, detail = engine.status(t)
            print(f"[{state}] {engine.NAMES[t.kind]}\n  {t.path}\n  {detail}")
            failed |= state == "unsupported"
        return int(failed)
    groups = defaultdict(list)
    for target in targets:
        groups[engine.group_key(target)].append(target)
    failed = False
    for key, group in groups.items():
        print(f"\n{', '.join(engine.NAMES[t.kind] for t in group)}\n  {key}")
        try:
            if action == "patch":
                print("[ok] " + engine.patch_group(group, backup_root, allow_library_validation))
            else:
                print("[ok] " + engine.restore_group(group, backup_root))
        except (OSError, LookupError, ValueError) as e:
            print(f"[error] {e}")
            failed = True
    return int(failed)


def menu(overrides: dict[str, str], backup_root: Path, allow_library_validation: bool) -> int:
    print(f"Antigravity Local Patcher v{__version__}")
    print("CLI + Antigravity 2.0 / Manager + IDE")
    print("Close Antigravity before patching or restoring.")
    while True:
        print("\n1  Patch all detected installations")
        print("2  Show status")
        print("3  Restore originals")
        print("4  Set custom file paths")
        print("0  Exit")
        try:
            choice = input("Choose: ").strip()
        except EOFError:
            return 0
        if choice == "0":
            return 0
        if choice == "4":
            print("Enter the target FILE, not the installation folder. Leave blank for auto-detection.")
            for kind in engine.KINDS:
                overrides[kind] = input(f"{engine.NAMES[kind]} file: ").strip().strip('"')
            continue
        if choice not in ("1", "2", "3"):
            print("Please choose 0, 1, 2, 3 or 4.")
            continue
        try:
            run({"1": "patch", "2": "status", "3": "restore"}[choice], list(engine.KINDS), overrides,
                backup_root, allow_library_validation)
        except (OSError, ValueError) as e:
            print(f"[error] {e}")


def self_test() -> int:
    """Packaged-runtime smoke test; only touches files in a fresh temporary folder."""
    with tempfile.TemporaryDirectory(prefix="antigravity-patcher-self-test-") as temp:
        root = Path(temp)
        main = root / "main.js"
        original = b"let x=(resetIsTierGCPTos(),this.a.isGoogleInternal?yes():no());"
        main.write_bytes(original)
        target = engine.Target("ide", main.resolve())
        engine.patch_group([target], root / "backups", clear_caches=False)
        assert engine.plan(target).state == "patched"
        engine.restore_group([target], root / "backups", clear_caches=False)
        assert main.read_bytes() == original
        main.write_bytes(original * 2)
        state, _ = engine.status(target)
        assert state == "unsupported"
    print("Self-test passed: patch, SHA256 verification, restore and ambiguous-signature rejection.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline local eligibility patcher for Antigravity CLI, Manager and IDE.")
    parser.add_argument("action", nargs="?", choices=("menu", "status", "patch", "restore"), default="menu")
    parser.add_argument("targets", nargs="*", metavar="TARGET", help="Optional target selection: cli, manager, ide")
    for kind in engine.KINDS:
        parser.add_argument(f"--path-{kind}", metavar="FILE", help=f"Explicit {kind} file path (replaces auto-detection)")
    parser.add_argument("--backup-dir", type=Path, default=engine.default_backup_root(), help="Directory for verified backups")
    parser.add_argument("--macos-disable-library-validation", action="store_true", help="Allow the app-specific signing entitlement needed by some Electron apps")
    parser.add_argument("--version", action="version", version=f"Antigravity Local Patcher {__version__}")
    parser.add_argument("--self-test", action="store_true", help="Run isolated packaged-runtime checks without touching installed apps")
    args = parser.parse_args(argv)
    if any(t not in engine.KINDS for t in args.targets):
        parser.error("Targets must be cli, manager or ide")
    overrides = {kind: getattr(args, f"path_{kind}") for kind in engine.KINDS}
    try:
        if args.self_test:
            return self_test()
        if args.action == "menu":
            return menu(overrides, args.backup_dir.expanduser().resolve(), args.macos_disable_library_validation)
        return run(args.action, args.targets or list(engine.KINDS), overrides,
                   args.backup_dir.expanduser().resolve(), args.macos_disable_library_validation)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except (OSError, ValueError) as e:
        print(f"[error] {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
