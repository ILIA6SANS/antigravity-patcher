"""Selected MIT-licensed upstream signatures, format parsers and signing helpers.

Source: QNIX-Dev/eligibility-antigravity-patcher
Commit: d3e447fb9c5bebb6e15146620105055bae3f6628
Copyright (c) 2026 QNIX-Dev. See LICENSE and THIRD_PARTY_NOTICES.md.
Account, token, quota and network code is excluded.
"""
from __future__ import annotations
import functools, glob, hashlib, json, os, plistlib, re, shutil, struct, subprocess, sys, tempfile
from xml.parsers.expat import ExpatError
try:
    import winreg
except ImportError:
    winreg = None
MAC_DISABLE_LIBRARY_VALIDATION = "com.apple.security.cs.disable-library-validation"


def _say(tag, msg): print(f"  [{tag}] {msg}")

def ok(m):   _say("ok", m)

def info(m): _say("..", m)

def warn(m): _say("!!", m)

def _bin(name):
    return name + (".exe" if os.name == "nt" else "")

def _files_equal(first, second):
    """Read actual bytes on every check, including same-size/mtime rewrites."""
    with open(first, "rb") as a, open(second, "rb") as b:
        while True:
            chunk = a.read(1024 * 1024)
            if chunk != b.read(1024 * 1024):
                return False
            if not chunk:
                return True

def _read_exact(f, offset, size):
    f.seek(offset)
    data = f.read(size)
    if len(data) != size:
        raise ValueError("truncated executable header")
    return data

def _normalized_ranges(ranges, file_size):
    clean = []
    for start, end in ranges:
        start, end = max(0, start), min(file_size, end)
        if start < end: clean.append((start, end))
    out = []
    for start, end in sorted(clean):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return tuple(out)

def _machine_arch(machine):
    return {0x8664: "x64", 0xaa64: "arm64", 0x3e: "x64", 0xb7: "arm64",
            0x01000007: "x64", 0x0100000c: "arm64"}.get(machine)

def _pe_executable_info(f, file_size):
    pe = struct.unpack("<I", _read_exact(f, 0x3c, 4))[0]
    if _read_exact(f, pe, 4) != b"PE\0\0":
        raise ValueError("invalid PE signature")
    coff = _read_exact(f, pe + 4, 20)
    arch = _machine_arch(struct.unpack_from("<H", coff, 0)[0])
    section_count = struct.unpack_from("<H", coff, 2)[0]
    optional_size = struct.unpack_from("<H", coff, 16)[0]
    section_table = pe + 24 + optional_size
    ranges = []
    for i in range(section_count):
        section = _read_exact(f, section_table + i * 40, 40)
        raw_size, raw_offset = struct.unpack_from("<II", section, 16)
        characteristics = struct.unpack_from("<I", section, 36)[0]
        if characteristics & 0x20000000:
            ranges.append((raw_offset, raw_offset + raw_size))
    return _normalized_ranges(ranges, file_size), arch

def _elf_executable_info(f, file_size):
    ident = _read_exact(f, 0, 16)
    elf_class, data_order = ident[4], ident[5]
    endian = "<" if data_order == 1 else ">" if data_order == 2 else None
    if endian is None:
        raise ValueError("unknown ELF byte order")
    machine = struct.unpack(endian + "H", _read_exact(f, 18, 2))[0]
    if elf_class == 2:
        header = _read_exact(f, 0, 64)
        phoff = struct.unpack_from(endian + "Q", header, 32)[0]
        phentsize, phnum = struct.unpack_from(endian + "HH", header, 54)
        layout = (0, 4, 8, 32, "I", "I", "Q", "Q")
    elif elf_class == 1:
        header = _read_exact(f, 0, 52)
        phoff = struct.unpack_from(endian + "I", header, 28)[0]
        phentsize, phnum = struct.unpack_from(endian + "HH", header, 42)
        layout = (0, 24, 4, 16, "I", "I", "I", "I")
    else:
        raise ValueError("unknown ELF class")
    type_off, flags_off, file_off, size_off, type_fmt, flags_fmt, off_fmt, size_fmt = layout
    ranges = []
    for i in range(phnum):
        entry = _read_exact(f, phoff + i * phentsize, phentsize)
        p_type = struct.unpack_from(endian + type_fmt, entry, type_off)[0]
        flags = struct.unpack_from(endian + flags_fmt, entry, flags_off)[0]
        offset = struct.unpack_from(endian + off_fmt, entry, file_off)[0]
        size = struct.unpack_from(endian + size_fmt, entry, size_off)[0]
        if p_type == 1 and flags & 1:
            ranges.append((offset, offset + size))
    return _normalized_ranges(ranges, file_size), _machine_arch(machine)

def _macho_slice_info(f, file_size, base, slice_size):
    magic = _read_exact(f, base, 4)
    if magic == b"\xcf\xfa\xed\xfe":
        endian = "<"
    elif magic == b"\xfe\xed\xfa\xcf":
        endian = ">"
    else:
        raise ValueError("unsupported Mach-O slice")
    header = _read_exact(f, base, 32)
    arch = _machine_arch(struct.unpack_from(endian + "I", header, 4)[0])
    command_count = struct.unpack_from(endian + "I", header, 16)[0]
    pos, ranges = base + 32, []
    for _ in range(command_count):
        command_header = _read_exact(f, pos, 8)
        command, command_size = struct.unpack(endian + "II", command_header)
        if command_size < 8 or pos + command_size > base + slice_size:
            raise ValueError("invalid Mach-O load command")
        if command == 0x19:
            segment = _read_exact(f, pos, command_size)
            section_count = struct.unpack_from(endian + "I", segment, 64)[0]
            if 72 + section_count * 80 > command_size:
                raise ValueError("invalid Mach-O section table")
            section_pos = 72
            for _ in range(section_count):
                section = segment[section_pos:section_pos + 80]
                section_name = section[:16].split(b"\0", 1)[0]
                segment_name = section[16:32].split(b"\0", 1)[0]
                size = struct.unpack_from(endian + "Q", section, 40)[0]
                offset = struct.unpack_from(endian + "I", section, 48)[0]
                flags = struct.unpack_from(endian + "I", section, 64)[0]
                is_code = ((segment_name, section_name) == (b"__TEXT", b"__text") or
                           flags & (0x80000000 | 0x00000400))
                if is_code:
                    ranges.append((base + offset, base + offset + size))
                section_pos += 80
        pos += command_size
    return _normalized_ranges(ranges, file_size), arch

def _macho_executable_info(f, file_size):
    magic = _read_exact(f, 0, 4)
    if magic in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
        return _macho_slice_info(f, file_size, 0, file_size)
    fat = {
        b"\xca\xfe\xba\xbe": (">", False), b"\xbe\xba\xfe\xca": ("<", False),
        b"\xca\xfe\xba\xbf": (">", True),  b"\xbf\xba\xfe\xca": ("<", True),
    }.get(magic)
    if not fat:
        raise ValueError("unsupported Mach-O header")
    endian, is_64 = fat
    count = struct.unpack(endian + "I", _read_exact(f, 4, 4))[0]
    entry_size = 32 if is_64 else 20
    ranges, arches = [], []
    for i in range(count):
        entry = _read_exact(f, 8 + i * entry_size, entry_size)
        if is_64:
            offset, size = struct.unpack_from(endian + "QQ", entry, 8)
        else:
            offset, size = struct.unpack_from(endian + "II", entry, 8)
        slice_ranges, arch = _macho_slice_info(f, file_size, offset, size)
        ranges += slice_ranges
        arches.append(arch)
    known_arch = arches[0] if arches and arches[0] and all(a == arches[0] for a in arches) else None
    return _normalized_ranges(ranges, file_size), known_arch

def executable_info(path):
    """Return executable file ranges and architecture for PE, ELF, or Mach-O."""
    with open(path, "rb") as f:
        file_size = os.fstat(f.fileno()).st_size
        magic = _read_exact(f, 0, min(4, file_size))
        if magic[:2] == b"MZ":
            ranges, arch = _pe_executable_info(f, file_size)
        elif magic == b"\x7fELF":
            ranges, arch = _elf_executable_info(f, file_size)
        else:
            ranges, arch = _macho_executable_info(f, file_size)
    if not ranges:
        raise ValueError("no executable code ranges found")
    return ranges, arch

@functools.lru_cache(maxsize=1)
def _reg_install_dirs():
    dirs = []
    if not winreg: return dirs
    for hive, sub in ((winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE,  r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE,  r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")):
        try: key = winreg.OpenKey(hive, sub)
        except OSError: continue
        try: cnt = winreg.QueryInfoKey(key)[0]
        except OSError: cnt = 0
        for i in range(cnt):
            try:
                s = winreg.OpenKey(key, winreg.EnumKey(key, i))
                if "antigravity" in str(winreg.QueryValueEx(s, "DisplayName")[0]).lower():
                    loc = winreg.QueryValueEx(s, "InstallLocation")[0]
                    if loc: dirs.append(loc)
            except OSError:
                pass
    return dirs

@functools.lru_cache(maxsize=1)
def _roots():
    out = []
    for v in ("LOCALAPPDATA", "ProgramW6432", "PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramData", "APPDATA"):
        p = os.environ.get(v)
        if not p: continue
        out += [p, os.path.join(p, "Programs")]
    up = os.environ.get("USERPROFILE", "")
    out += [os.path.join(up, "scoop", "apps"), os.path.join(os.environ.get("SCOOP", ""), "apps")]
    out += _reg_install_dirs()
    seen, roots = set(), []
    for r in out:
        if r and os.path.isdir(r):
            k = os.path.normcase(os.path.realpath(r))
            if k not in seen: seen.add(k); roots.append(r)
    return roots

def _dedup_newest(paths):
    seen, out = set(), []
    for p in sorted({p for p in paths if os.path.exists(p)},
                    key=lambda x: os.path.getmtime(x), reverse=True):
        k = os.path.normcase(os.path.realpath(p))
        if k not in seen: seen.add(k); out.append(p)
    return out

def find_marker(rel):
    """Find a marker below known Windows install roots."""
    hits = []
    for root in _roots():
        hits += glob.glob(os.path.join(root, "*ntigravity*", rel))
        hits += glob.glob(os.path.join(root, "*ntigravity*", "*", rel))
        direct = os.path.join(root, rel)
        if os.path.isfile(direct): hits.append(direct)
    return _dedup_newest(hits)

def _posix_install_roots(*launchers):
    home = os.path.expanduser("~")
    roots = ["/opt", "/usr/share", "/usr/lib", "/usr/local/share", "/usr/local/lib",
             "/Applications",
             os.path.join(home, ".local", "share"),
             os.path.join(home, "Applications"),
             os.path.join(home, "Downloads"), home]
    for launcher in launchers:
        w = shutil.which(launcher)
        if w: roots.append(os.path.dirname(os.path.realpath(w)))
    return roots

def _posix_find(rel, *launchers):
    """Find a marker below known POSIX install roots."""
    hits = []
    for root in _posix_install_roots(*launchers):
        hits += glob.glob(os.path.join(root, "*ntigravity*", rel))
        hits += glob.glob(os.path.join(root, "*ntigravity*", "*", rel))
        direct = os.path.join(root, rel)
        if os.path.isfile(direct): hits.append(direct)
    return _dedup_newest(hits)

class SignatureNotFound(LookupError):
    pass

class SignatureAmbiguous(LookupError):
    pass

def _unique_match(pattern, data, ranges, label, accept=None):
    found = None
    for start, end in ranges:
        pos = start
        while pos < end:
            match = pattern.search(data, pos, end)
            if not match:
                break
            if accept is not None and not accept(data, match, start, end):
                pos = max(match.end(), match.start() + 1)
                continue
            if found is not None:
                raise SignatureAmbiguous(f"{label} signature is not unique — refusing to guess")
            found = match
            pos = max(match.end(), match.start() + 1)
    return found

class Gate:
    def __init__(self, sig, patched, fix, offset=0, desc="", arch=None, accept=None):
        self.sig, self.patched = re.compile(sig, re.S), re.compile(patched, re.S)
        self.fix, self.offset, self.desc, self.arch, self.accept = fix, offset, desc, arch, accept
    def find(self, data, ranges=None):
        """Return state and write offset for one unambiguous signature."""
        search_ranges = ranges or ((0, len(data)),)
        original = _unique_match(self.sig, data, search_ranges, "unpatched gate", self.accept)
        patched = _unique_match(self.patched, data, search_ranges, "patched gate", self.accept)
        if original and patched:
            raise SignatureAmbiguous("both patched and unpatched gate signatures are present")
        if patched:
            return ("patched", patched.start() + self.offset)
        if original:
            return ("unpatched", original.start() + self.offset)
        raise SignatureNotFound("gate signature not found (unsupported version?)")
    def resolve(self, data, ranges=None, arch=None):
        kind, off = self.find(data, ranges)
        return kind, off, self

class MultiGate:
    """Select one architecture-specific gate."""
    def __init__(self, *gates, desc=""):
        self.gates, self.desc = gates, desc
    def resolve(self, data, ranges=None, arch=None):
        matches = []
        gates = [g for g in self.gates
                 if arch is None or getattr(g, "arch", None) is None or g.arch == arch]
        for g in gates:
            try:
                matches.append(g.resolve(data, ranges, arch))
            except SignatureNotFound:
                pass
        if len(matches) > 1:
            raise SignatureAmbiguous("multiple architecture gate signatures matched")
        if matches:
            return matches[0]
        raise SignatureNotFound("no architecture gate signature matched (unsupported version?)")

CLI_GATE_X64 = Gate(
    rb"\x48\x85\xc0\x0f\x84....\x80\x78\x08\x00\x0f\x85...."
    rb"\xe8....\x48\x89\x84\x24\xd8\x00\x00\x00"
    rb"\x48\x89\x9c\x24\xe0\x00\x00\x00\x48\x89\x8c\x24\xe8\x00\x00\x00",
    rb"\x48\x85\xc0\x0f\x84....\x48\x85\xc0\x90\x0f\x85...."
    rb"\xe8....\x48\x89\x84\x24\xd8\x00\x00\x00"
    rb"\x48\x89\x9c\x24\xe0\x00\x00\x00\x48\x89\x8c\x24\xe8\x00\x00\x00",
    b"\x48\x85\xc0\x90", offset=9, desc="eligibility screen off (x64)", arch="x64")

def _cli_arm64_context(data, match, start, end):
    off = match.start()
    if off - 8 < start:
        return False
    cbnz_x1, cbz_x0 = struct.unpack_from("<II", data, off - 8)
    return ((cbnz_x1 & 0xff00001f) == 0xb5000001 and
            (cbz_x0 & 0xff00001f) == 0xb4000000)

CLI_GATE_ARM64 = Gate(
    rb"\x02\x20\x40\x39[\x02\x22\x42\x62\x82\xa2\xc2\xe2].[\x00-\x07]\x37"
    rb"...[\x94-\x97]\xe0\x07\x0e\xa9\xe2\x0f\x0f\xa9\xe4\x17\x10\xa9\xe6\x1f\x11\xa9",
    rb"\x22\x00\x80\x52[\x02\x22\x42\x62\x82\xa2\xc2\xe2].[\x00-\x07]\x37"
    rb"...[\x94-\x97]\xe0\x07\x0e\xa9\xe2\x0f\x0f\xa9\xe4\x17\x10\xa9\xe6\x1f\x11\xa9",
    b"\x22\x00\x80\x52", desc="eligibility screen off (arm64)",
    arch="arm64", accept=_cli_arm64_context)

CLI_GATE = MultiGate(CLI_GATE_X64, CLI_GATE_ARM64, desc="eligibility screen off")

def cli_default_paths():
    cands = []
    w = shutil.which("agy")
    if w:
        base, ext = os.path.splitext(w); cands.append(base + ext.lower())
    if os.name == "nt":
        for root in _roots():
            cands += glob.glob(os.path.join(root, "agy", "bin", "agy.exe"))
            cands += glob.glob(os.path.join(root, "agy", "*", "bin", "agy.exe"))
            cands += glob.glob(os.path.join(root, "agy*", "agy.exe"))
    else:
        home = os.path.expanduser("~")
        cands += [os.path.join(d, "agy") for d in
                  (os.path.join(home, ".local", "bin"), os.path.join(home, "bin"),
                   "/usr/local/bin", "/usr/bin", "/opt/homebrew/bin")]
    return _dedup_newest(cands)

MANAGER_GATE_X64 = Gate(rb"\x80\x78\x08\x00\x74.\x48\x8b\x54\x24\x70\x48\x89\x50\x60",
                        rb"\xc6\x40\x08\x01\x90\x90\x48\x8b\x54\x24\x70\x48\x89\x50\x60",
                        b"\xc6\x40\x08\x01\x90\x90", desc="hasValidAuth=true", arch="x64")

MANAGER_GATE_ARM64 = Gate(rb"\x03\x20\x40\x39[\x03\x23\x43\x63\x83\xa3\xc3\xe3]."
                          rb"[\x00-\x07]\x36\xe3\x13\x48\xa9\x03\x10\x06\xa9",
                          rb"\x23\x00\x80\x52\x03\x20\x00\x39\xe3\x13\x48\xa9"
                          rb"\x03\x10\x06\xa9",
                          b"\x23\x00\x80\x52\x03\x20\x00\x39", desc="hasValidAuth=true (arm64)",
                          arch="arm64")

MANAGER_GATE = MultiGate(MANAGER_GATE_X64, MANAGER_GATE_ARM64, desc="hasValidAuth=true")

def manager_default_bins():
    if os.name == "nt":
        return find_marker(os.path.join("resources", "bin", "language_server.exe"))
    rel = (os.path.join("Contents", "Resources", "bin", "language_server") if sys.platform == "darwin"
           else os.path.join("resources", "bin", "language_server"))
    return _posix_find(rel, "antigravity")

def ide_default_mains():
    if os.name == "nt":
        return find_marker(os.path.join("resources", "app", "out", "main.js"))
    rel = (os.path.join("Contents", "Resources", "app", "out", "main.js") if sys.platform == "darwin"
           else os.path.join("resources", "app", "out", "main.js"))
    return _posix_find(rel, "antigravity-ide", "antigravity")

def _mac_app_bundle(path):
    """Return the enclosing .app bundle, if path is inside one."""
    cur = os.path.realpath(path)
    if not os.path.isdir(cur):
        cur = os.path.dirname(cur)
    while True:
        if cur.endswith(".app") and os.path.isdir(os.path.join(cur, "Contents")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent

def _mac_bundle_main(app):
    info_path = os.path.join(app, "Contents", "Info.plist")
    with open(info_path, "rb") as f:
        executable = plistlib.load(f).get("CFBundleExecutable")
    if not isinstance(executable, str) or not executable or os.path.basename(executable) != executable:
        raise ValueError("invalid CFBundleExecutable in macOS app bundle")
    path = os.path.join(app, "Contents", "MacOS", executable)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"app bundle executable not found: {path}")
    return path

def _mac_entry_kind(path):
    if os.path.islink(path):
        return "symlink"
    if os.path.isdir(path):
        return "dir"
    if os.path.isfile(path):
        return "file"
    return "missing"

def _mac_entry_digest(path):
    h = hashlib.sha256()

    def add(cur, rel):
        kind = _mac_entry_kind(cur)
        h.update(kind.encode() + b"\0" + rel.encode("utf-8", "surrogateescape") + b"\0")
        if kind == "symlink":
            h.update(os.readlink(cur).encode("utf-8", "surrogateescape"))
        elif kind == "file":
            h.update(str(os.stat(cur, follow_symlinks=False).st_mode & 0o7777).encode())
            with open(cur, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
        elif kind == "dir":
            for name in sorted(os.listdir(cur)):
                add(os.path.join(cur, name), rel + "/" + name if rel else name)

    add(path, "")
    return h.hexdigest()

def _mac_remove_entry(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)

def _mac_copy_entry(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    kind = _mac_entry_kind(src)
    if kind == "symlink":
        os.symlink(os.readlink(src), dst)
    elif kind == "dir":
        shutil.copytree(src, dst, symlinks=True, copy_function=shutil.copy2)
    elif kind == "file":
        shutil.copy2(src, dst)

def _mac_signature_relpaths(app):
    main = os.path.relpath(_mac_bundle_main(app), app)
    return (main, os.path.join("Contents", "_CodeSignature"),
            os.path.join("Contents", "CodeResources"))

def _mac_write_signature_snapshot(app, snapshot):
    app = os.path.abspath(app)
    payload = os.path.join(snapshot, "payload")
    os.makedirs(payload, exist_ok=True)
    items = []
    for rel in _mac_signature_relpaths(app):
        src = os.path.join(app, rel)
        kind = _mac_entry_kind(src)
        if kind != "missing":
            _mac_copy_entry(src, os.path.join(payload, rel))
        items.append({"path": rel.replace(os.sep, "/"), "kind": kind,
                      "digest": _mac_entry_digest(src)})
    manifest = {"version": 1, "app": app, "items": items}
    with open(os.path.join(snapshot, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, sort_keys=True)
        f.flush(); os.fsync(f.fileno())
    _mac_validate_signature_snapshot(snapshot, app)

def _mac_load_signature_snapshot(snapshot, app):
    with open(os.path.join(snapshot, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    app = os.path.abspath(app)
    if manifest.get("version") != 1 or os.path.abspath(manifest.get("app", "")) != app:
        raise OSError("macOS signature backup belongs to a different app bundle")
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise OSError("invalid macOS signature backup manifest")
    expected = {p.replace(os.sep, "/") for p in _mac_signature_relpaths(app)}
    if {item.get("path") for item in items} != expected or len(items) != len(expected):
        raise OSError("unexpected paths in macOS signature backup")
    for item in items:
        rel = item.get("path", "").replace("/", os.sep)
        dst = os.path.abspath(os.path.join(app, rel))
        if (not rel or os.path.isabs(rel) or
                os.path.normcase(os.path.commonpath((app, dst))) != os.path.normcase(app)):
            raise OSError("unsafe path in macOS signature backup")
    return manifest

def _mac_validate_signature_snapshot(snapshot, app):
    manifest = _mac_load_signature_snapshot(snapshot, app)
    for item in manifest["items"]:
        rel = item["path"].replace("/", os.sep)
        saved = os.path.join(snapshot, "payload", rel)
        if _mac_entry_kind(saved) != item["kind"]:
            raise OSError("macOS signature backup type verification failed")
        if _mac_entry_digest(saved) != item["digest"]:
            raise OSError("macOS signature backup content verification failed")
    return manifest

def _mac_restore_signature_snapshot(snapshot, app):
    manifest = _mac_validate_signature_snapshot(snapshot, app)
    app = os.path.abspath(app)
    for item in manifest["items"]:
        rel = item["path"].replace("/", os.sep)
        dst = os.path.join(app, rel)
        _mac_remove_entry(dst)
        if item["kind"] != "missing":
            _mac_copy_entry(os.path.join(snapshot, "payload", rel), dst)
            if _mac_entry_digest(dst) != item["digest"]:
                raise OSError("restored macOS signature state failed verification")

def _mac_command(args, check=True):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise OSError(detail[-1] if detail else f"command failed ({result.returncode}): {args[0]}")
    return result

def _mac_entitlements(path):
    result = _mac_command(["/usr/bin/codesign", "-d", "--entitlements", "-", "--xml", path])
    if not result.stdout.strip():
        return {}
    try:
        entitlements = plistlib.loads(result.stdout.encode("utf-8"))
    except (ValueError, ExpatError):
        raise OSError("cannot parse macOS signing entitlements") from None
    if not isinstance(entitlements, dict):
        raise OSError("macOS signing entitlements must be a dictionary")
    return entitlements

def _mac_library_validation_entitlements(app, allow_disable=False):
    """Plan an explicit Electron signing exception before any patch writes."""
    framework = os.path.join(app, "Contents", "Frameworks", "Electron Framework.framework")
    if not os.path.isdir(framework):
        return None
    _mac_bundle_main(app)  # Validate the executable covered by the bundle signature.
    display = _mac_command(["/usr/bin/codesign", "-d", "--verbose=4", app])
    details = display.stdout + display.stderr
    flags = re.search(r"\bflags=0x([0-9a-fA-F]+)\b", details)
    if not flags:
        raise OSError("cannot determine Electron code-signing flags before patching")
    # CS_RUNTIME enables Library Validation; CS_REQUIRE_LV requests it explicitly.
    if not int(flags[1], 16) & (0x10000 | 0x2000):
        return None
    entitlements = _mac_entitlements(app)
    exception = entitlements.get(MAC_DISABLE_LIBRARY_VALIDATION, False)
    if not isinstance(exception, bool):
        raise OSError("invalid Electron disable-library-validation entitlement")
    if exception:
        return None
    framework_display = _mac_command(["/usr/bin/codesign", "-d", "--verbose=4", framework])
    framework_details = framework_display.stdout + framework_display.stderr
    team = re.search(r"^TeamIdentifier=(.*)$", framework_details, re.M)
    if not team:
        raise OSError("cannot determine Electron Framework Team ID before patching")
    if not allow_disable:
        raise OSError(
            "Electron Library Validation would reject bundled frameworks after ad-hoc signing "
            f"(Electron Framework Team ID: {team[1].strip()}; ad-hoc Team ID: none). "
            "No patch was applied. To permit other/unsigned libraries in this app's main executable, "
            "rerun patch with --macos-disable-library-validation")
    return {**entitlements, MAC_DISABLE_LIBRARY_VALIDATION: True}

def _mac_codesign(path, bundle=False, entitlements=None):
    display = _mac_command(["/usr/bin/codesign", "-d", "--verbose=2", path], check=False)
    if entitlements is not None and display.returncode:
        raise OSError("cannot preserve Electron signing metadata before applying the Library Validation exception")
    args = ["/usr/bin/codesign", "--force", "--sign", "-"]
    if display.returncode == 0:
        metadata = "identifier,flags,runtime" if entitlements is not None else "identifier,entitlements,flags,runtime"
        args.append("--preserve-metadata=" + metadata)
    with tempfile.TemporaryDirectory(prefix="agy-macos-entitlements-") as temp:
        if entitlements is not None:
            if not bundle:
                raise ValueError("Library Validation exceptions are limited to the app bundle's main executable")
            plist = os.path.join(temp, "entitlements.plist")
            with open(plist, "wb") as f:
                plistlib.dump(entitlements, f)
            args += ["--entitlements", plist]
            warn(f"disabling Library Validation for {os.path.basename(path)} main executable only; "
                 "this permits libraries with other or no signatures")
        _mac_command(args + [path])
        _mac_codesign_verify(path, bundle=bundle)
        if entitlements is not None and _mac_entitlements(path) != entitlements:
            raise OSError("signed macOS entitlements do not match the requested entitlements")

def _mac_sign_transaction(entries, bundle_entitlements=None):
    binaries = []
    bundles = []
    for target, path in entries.items():
        actual = os.path.realpath(path)
        if target in ("cli", "manager", "extension") and actual not in binaries:
            binaries.append(actual)
        app = _mac_app_bundle(path)
        if app and app not in bundles:
            bundles.append(app)
    if not binaries and not bundles:
        return

    with tempfile.TemporaryDirectory(prefix="agy-macos-sign-") as temp:
        binary_copies = []
        bundle_copies = []
        for i, path in enumerate(binaries):
            saved = os.path.join(temp, f"binary-{i}")
            shutil.copy2(path, saved)
            if not _files_equal(path, saved):
                raise OSError("temporary macOS signing backup verification failed")
            binary_copies.append((path, saved))
        for i, app in enumerate(bundles):
            saved = os.path.join(temp, f"bundle-{i}")
            os.makedirs(saved)
            _mac_write_signature_snapshot(app, saved)
            bundle_copies.append((app, saved))
        try:
            for path in binaries:
                _mac_codesign(path)
            for app in bundles:
                entitlements = (bundle_entitlements or {}).get(app)
                if entitlements is None:
                    _mac_codesign(app, bundle=True)
                else:
                    _mac_codesign(app, bundle=True, entitlements=entitlements)
            for path in binaries:
                ok(f"ad-hoc signed {os.path.basename(path)}")
            for app in bundles:
                ok(f"ad-hoc signed {os.path.basename(app)}")
        except Exception:
            restore_errors = []
            for path, saved in binary_copies:
                try:
                    shutil.copy2(saved, path)
                except Exception as e:
                    restore_errors.append(str(e))
            for app, saved in bundle_copies:
                try:
                    _mac_restore_signature_snapshot(saved, app)
                except Exception as e:
                    restore_errors.append(str(e))
            if restore_errors:
                raise OSError("macOS signing failed and its temporary state could not be restored: " +
                              "; ".join(restore_errors))
            raise

def _mac_codesign_verify(path, bundle=False):
    args = ["/usr/bin/codesign", "--verify"]
    if bundle:
        args.append("--deep")
    args += ["--strict", "--verbose=2", path]
    _mac_command(args)
