"""Offline patch transactions with verified backups and guarded restore."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import uuid

from . import native

KINDS = ("cli", "manager", "ide")
NAMES = {"cli": "Antigravity CLI", "manager": "Antigravity 2.0 / Manager", "ide": "Antigravity IDE"}
IDE_RE = re.compile(rb"(resetIsTierGCPTos\(\),)(this\.[A-Za-z_$0-9]+\.isGoogleInternal)(?![A-Za-z_$0-9])")
IDE_DONE = re.compile(rb"resetIsTierGCPTos\(\),true(?![A-Za-z_$0-9])")


@dataclass(frozen=True)
class Target:
    kind: str
    path: Path


@dataclass(frozen=True)
class Plan:
    state: str
    offset: int = 0
    fix: bytes = b""
    detail: str = ""


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def plan(target: Target) -> Plan:
    data = target.path.read_bytes()
    if target.kind == "ide":
        before, after = list(IDE_RE.finditer(data)), list(IDE_DONE.finditer(data))
        if len(before) == 1 and not after:
            match = before[0]
            length = match.end(2) - match.start(2)
            return Plan("ready", match.start(2), b"true" + b" " * (length - 4), "Local IDE login branch")
        if len(after) == 1 and not before:
            return Plan("patched", detail="Local IDE login branch")
        if before or after:
            raise native.SignatureAmbiguous("IDE signature is ambiguous; no changes made")
        raise native.SignatureNotFound("Known IDE signature not found; unsupported build")
    ranges, arch = native.executable_info(str(target.path))
    if arch not in ("x64", "arm64"):
        raise native.SignatureNotFound("Unsupported or mixed executable architecture")
    gate = native.CLI_GATE if target.kind == "cli" else native.MANAGER_GATE
    state, offset, signature = gate.resolve(data, ranges, arch)
    return Plan("ready" if state == "unpatched" else state, offset, signature.fix, f"Local {target.kind} gate ({arch})")


def status(target: Target) -> tuple[str, str]:
    try:
        p = plan(target)
        return p.state, p.detail
    except (OSError, LookupError, ValueError, IndexError, struct.error) as e:
        return "unsupported", str(e)


def default_backup_root() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "AntigravityPatcher/backups"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/AntigravityPatcher/backups"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "antigravity-patcher/backups"


def group_key(target: Target) -> str:
    if sys.platform == "darwin":
        app = native._mac_app_bundle(str(target.path))
        if app:
            return str(Path(app).resolve())
    return str(target.path.resolve())


def group_dir(target: Target, backup_root: Path) -> Path:
    key = os.path.normcase(group_key(target)).encode("utf-8", "surrogateescape")
    return backup_root / hashlib.sha256(key).hexdigest()


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise OSError("Backup directory must not be a symbolic link")
    if os.name != "nt":
        path.chmod(0o700)


@contextlib.contextmanager
def group_lock(folder: Path):
    ensure_private_dir(folder)
    lock = folder / "operation.lock"
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise OSError(f"Another operation is active, or a previous run was interrupted. Check {lock}") from None
    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def save_json(path: Path, data: dict) -> None:
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def verified_copy(src: Path, dst: Path) -> None:
    shutil.copy2(src, dst)
    if digest(src) != digest(dst):
        raise OSError(f"Backup verification failed: {dst}")


def durable_restore(src: Path, dst: Path) -> None:
    # Existing inode is retained, including permissions and extended attributes.
    with src.open("rb") as saved, dst.open("r+b") as f:
        f.seek(0)
        shutil.copyfileobj(saved, f)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
    if digest(dst) != digest(src):
        raise OSError(f"Restore verification failed: {dst}")


def write_patch(target: Target, p: Plan, expected_original: str) -> None:
    with target.path.open("r+b") as f:
        data = f.read()
        if hashlib.sha256(data).hexdigest() != expected_original:
            raise OSError("Target changed before patch write")
        expected = data[:p.offset] + p.fix + data[p.offset + len(p.fix):]
        expected_hash = hashlib.sha256(expected).hexdigest()
        f.seek(p.offset)
        f.write(p.fix)
        f.flush()
        os.fsync(f.fileno())
        f.seek(0)
        if hashlib.sha256(f.read()).hexdigest() != expected_hash:
            raise OSError("Post-write SHA256 verification failed")
    if plan(target).state != "patched":
        raise OSError("Post-write signature verification failed")


def app_signature_fingerprint(app: str) -> dict:
    return {rel.replace(os.sep, "/"): native._mac_entry_digest(os.path.join(app, rel))
            for rel in native._mac_signature_relpaths(app)}


def load_record(folder: Path, key: str) -> dict | None:
    pointer = folder / "current.json"
    if not pointer.exists():
        return None
    data = json.loads(pointer.read_text(encoding="utf-8"))
    if data.get("format") != 1 or data.get("key") != key:
        raise OSError("Backup record belongs to a different installation")
    version = data.get("version", "")
    if not re.fullmatch(r"[0-9a-f]{32}", version):
        raise OSError("Invalid backup version")
    entries = data.get("entries", [])
    if not entries:
        raise OSError("Empty backup record")
    seen = set()
    for entry in entries:
        if entry.get("kind") not in KINDS or not Path(entry.get("path", "")).is_absolute():
            raise OSError("Invalid backup target")
        for field in ("original", "patched"):
            if not re.fullmatch(r"[0-9a-f]{64}", entry.get(field, "")):
                raise OSError("Invalid backup digest")
        if entry["path"] in seen or group_key(Target(entry["kind"], Path(entry["path"]))) != key:
            raise OSError("Unexpected target in backup record")
        seen.add(entry["path"])
    return data


def patch_group(targets: list[Target], backup_root: Path, allow_library_validation: bool = False,
                *, clear_caches: bool = True) -> str:
    key = group_key(targets[0])
    if any(group_key(t) != key for t in targets):
        raise ValueError("Transaction contains unrelated installations")
    plans = [(t, plan(t)) for t in targets]  # Preflight all signatures before creating a backup.
    ready = [(t, p) for t, p in plans if p.state == "ready"]
    if not ready:
        return "Already patched."
    if len(ready) != len(plans):
        raise OSError("Mixed original/patched files in one app. Restore this app before changing additional targets.")
    folder = group_dir(targets[0], backup_root)
    app = native._mac_app_bundle(str(targets[0].path)) if sys.platform == "darwin" else None
    entitlements = native._mac_library_validation_entitlements(app, allow_library_validation) if app else None
    with group_lock(folder):
        existing = load_record(folder, key)
        if existing and app:
            old_paths = {e["path"] for e in existing["entries"]}
            if old_paths != {str(t.path) for t in targets}:
                raise OSError("Existing macOS backup covers different targets. Restore the previous app transaction first.")
        version = uuid.uuid4().hex
        saved = folder / version
        ensure_private_dir(saved)
        entries = []
        for i, (target, _) in enumerate(ready):
            original = digest(target.path)
            backup = saved / f"original-{i}.bin"
            verified_copy(target.path, backup)
            if digest(backup) != original:
                raise OSError("Target changed while creating backup")
            entries.append({"kind": target.kind, "path": str(target.path), "original": original, "patched": original})
        if app:
            native._mac_write_signature_snapshot(app, str(saved / "signature"))
        record = {"format": 1, "key": key, "version": version, "entries": entries,
                  "state": "prepared", "app": app, "signature": None}
        save_json(folder / "current.json", record)
        try:
            for (target, p), entry in zip(ready, entries):
                write_patch(target, p, entry["original"])
            if sys.platform == "darwin":
                native._mac_sign_transaction({t.kind: str(t.path) for t, _ in ready},
                                             {app: entitlements} if entitlements is not None else None)
            for (target, _), entry in zip(ready, entries):
                if plan(target).state != "patched":
                    raise OSError("Signature no longer matches after signing")
                entry["patched"] = digest(target.path)
            record["state"] = "patched"
            record["signature"] = app_signature_fingerprint(app) if app else None
            save_json(folder / "current.json", record)
        except BaseException as failure:
            errors = []
            for i, entry in enumerate(entries):
                try:
                    durable_restore(saved / f"original-{i}.bin", Path(entry["path"]))
                except OSError as e:
                    errors.append(str(e))
            if app:
                try:
                    native._mac_restore_signature_snapshot(str(saved / "signature"), app)
                except (OSError, ValueError) as e:
                    errors.append(str(e))
            record["state"] = "rollback_failed" if errors else "restored"
            save_json(folder / "current.json", record)
            if errors:
                raise OSError(f"{failure}. Rollback failed: {'; '.join(errors)}. Backups: {saved}") from failure
            raise OSError(f"{failure}. Original files restored.") from failure
    for target, _ in ready:
        if clear_caches and target.kind == "ide":
            invalidate_caches(target.path)
    return f"Patched and verified. Backups: {saved}"


def import_legacy(target: Target, folder: Path) -> bool:
    """Read and verify backups created by the earlier Windows PowerShell release."""
    legacy = Path(str(target.path) + ".agpatch-state")
    if not legacy.is_file() or sys.platform == "darwin":
        return False
    fields = legacy.read_text(encoding="ascii").splitlines()
    if len(fields) != 3 or fields[0] != "AGPATCH1" or any(not re.fullmatch(r"[0-9a-f]{64}", v) for v in fields[1:]):
        raise OSError("Invalid legacy backup record")
    if digest(target.path) not in fields[1:]:
        raise OSError("File changed since the legacy patch. Refusing to restore an older build.")
    backup = Path(str(target.path) + ".agpatch-backups") / (fields[1] + ".bin")
    if digest(backup) != fields[1]:
        raise OSError("Legacy backup is damaged")
    version = uuid.uuid4().hex
    saved = folder / version
    ensure_private_dir(saved)
    verified_copy(backup, saved / "original-0.bin")
    record = {"format": 1, "key": group_key(target), "version": version, "state": "patched",
              "app": None, "signature": None,
              "entries": [{"kind": target.kind, "path": str(target.path), "original": fields[1], "patched": fields[2]}]}
    save_json(folder / "current.json", record)
    return True


def restore_group(targets: list[Target], backup_root: Path, *, clear_caches: bool = True) -> str:
    folder = group_dir(targets[0], backup_root)
    key = group_key(targets[0])
    with group_lock(folder):
        if not (folder / "current.json").exists() and len(targets) == 1:
            import_legacy(targets[0], folder)
        record = load_record(folder, key)
        if not record:
            raise OSError("No verified backup found for this installation")
        if record["state"] not in ("patched", "restored"):
            raise OSError("Previous operation was interrupted. Keep backups and restore original files manually.")
        saved = folder / record["version"]
        # Restoring an app restores all files in its recorded transaction.
        for i, entry in enumerate(record["entries"]):
            if digest(saved / f"original-{i}.bin") != entry["original"]:
                raise OSError("Backup is damaged; no files restored")
            current = digest(Path(entry["path"]))
            expected = entry["patched"] if record["state"] == "patched" else entry["original"]
            if current != expected:
                raise OSError("File changed since patch (possibly an app update). Refusing to restore an older build.")
        if record["state"] == "restored":
            return "Original already restored."
        app = record.get("app")
        if app:
            if app != key or sys.platform != "darwin":
                raise OSError("Invalid macOS app record")
            if app_signature_fingerprint(app) != record["signature"]:
                raise OSError("App signing state changed since patch; refusing restore")
            native._mac_validate_signature_snapshot(str(saved / "signature"), app)
        with tempfile.TemporaryDirectory(prefix="restore-", dir=folder) as temp:
            temp = Path(temp)
            for i, entry in enumerate(record["entries"]):
                verified_copy(Path(entry["path"]), temp / f"current-{i}.bin")
            if app:
                native._mac_write_signature_snapshot(app, str(temp / "signature"))
            try:
                for i, entry in enumerate(record["entries"]):
                    durable_restore(saved / f"original-{i}.bin", Path(entry["path"]))
                if app:
                    native._mac_restore_signature_snapshot(str(saved / "signature"), app)
                    native._mac_codesign_verify(app, bundle=True)
                elif sys.platform == "darwin":
                    for entry in record["entries"]:
                        if entry["kind"] != "ide":
                            native._mac_codesign_verify(entry["path"])
                record["state"] = "restored"
                save_json(folder / "current.json", record)
            except BaseException as failure:
                errors = []
                for i, entry in enumerate(record["entries"]):
                    try:
                        durable_restore(temp / f"current-{i}.bin", Path(entry["path"]))
                    except OSError as e:
                        errors.append(str(e))
                if app:
                    try:
                        native._mac_restore_signature_snapshot(str(temp / "signature"), app)
                    except (OSError, ValueError) as e:
                        errors.append(str(e))
                if errors:
                    raise OSError(f"{failure}. Restore rollback failed: {'; '.join(errors)}") from failure
                raise OSError(f"{failure}. State before restore recovered.") from failure
    for entry in record["entries"]:
        if clear_caches and entry["kind"] == "ide":
            invalidate_caches(Path(entry["path"]))
    return "Original restored and SHA256 verified."


def invalidate_caches(main: Path) -> None:
    if os.name == "nt":
        config = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    elif sys.platform == "darwin":
        config = Path.home() / "Library/Application Support"
    else:
        config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    bases = [config / "Antigravity", config / "Antigravity IDE"]
    if main.parent.name == "out" and main.parent.parent.name == "app":
        bases.append(main.parents[3] / "data/user-data")
    if os.name == "nt":
        bases.append(Path.home() / "scoop/persist/antigravity-ide/data/user-data")
    for base in bases:
        for relative in ("CachedData", "Code Cache/js"):
            cache = base / relative
            if not cache.is_dir():
                continue
            try:
                if cache.is_symlink() or any(p.is_symlink() for p in cache.parents):
                    raise OSError("Linked cache folder is not supported")
                if not cache.resolve().is_relative_to(base.resolve()):
                    raise OSError("Cache path escaped the intended profile")
                cache.rename(cache.with_name(cache.name + ".agpatch-" + uuid.uuid4().hex))
            except OSError as e:
                print(f"[warning] Cache was not moved: {cache}: {e}")
