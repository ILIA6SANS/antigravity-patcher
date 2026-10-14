from pathlib import Path
import hashlib
import json
import os
import struct
import tempfile
import unittest
from unittest.mock import patch

from antigravity_patcher import engine, native

CLI_X64 = bytes.fromhex('48 85 c0 0f 84 10 00 00 00 80 78 08 00 0f 85 20 00 00 00 e8 30 00 00 00 48 89 84 24 d8 00 00 00 48 89 9c 24 e0 00 00 00 48 89 8c 24 e8 00 00 00')
CLI_ARM64 = bytes.fromhex('41 00 00 b5 40 00 00 b4 02 20 40 39 42 00 00 37 00 00 00 94 e0 07 0e a9 e2 0f 0f a9 e4 17 10 a9 e6 1f 11 a9')
MANAGER_X64 = bytes.fromhex('80 78 08 00 74 13 48 8b 54 24 70 48 89 50 60')
MANAGER_ARM64 = bytes.fromhex('03 20 40 39 43 00 00 36 e3 13 48 a9 03 10 06 a9')
IDE = b'\xef\xbb\xbf// Unicode \xd0\x96\nlet x=(resetIsTierGCPTos(),this.a_$9.isGoogleInternal?yes():no());'


def pe(payload, arch='x64', executable=True):
    d = bytearray(1024)
    d[:2] = b'MZ'
    struct.pack_into('<I', d, 0x3c, 0x80)
    d[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', d, 0x84, 0x8664 if arch == 'x64' else 0xaa64, 1)
    struct.pack_into('<H', d, 0x94, 0xf0)
    s = 0x80+24+0xf0
    struct.pack_into('<II', d, s+16, 512, 512)
    struct.pack_into('<I', d, s+36, 0x60000020 if executable else 0x40000040)
    d[600:600+len(payload)] = payload
    return bytes(d)


def elf(payload, arch='x64', executable=True):
    d = bytearray(1024)
    d[:8] = b'\x7fELF\x02\x01\x01\x00'
    struct.pack_into('<HHI', d, 16, 2, 0x3e if arch == 'x64' else 0xb7, 1)
    struct.pack_into('<Q', d, 32, 64)
    struct.pack_into('<HHH', d, 52, 64, 56, 1)
    struct.pack_into('<IIQQQQQQ', d, 64, 1, 5 if executable else 4, 512, 0, 0, 512, 512, 4096)
    d[600:600+len(payload)] = payload
    return bytes(d)


def macho(payload, arch='x64', executable=True):
    d = bytearray(1024)
    d[:4] = b'\xcf\xfa\xed\xfe'
    struct.pack_into('<IIII', d, 4, 0x01000007 if arch == 'x64' else 0x0100000c, 0, 2, 1)
    struct.pack_into('<I', d, 20, 152)
    struct.pack_into('<II', d, 32, 0x19, 152)
    d[40:46] = b'__TEXT'
    struct.pack_into('<I', d, 96, 1)
    s = 104
    d[s:s+6] = b'__text' if executable else b'__data'
    d[s+16:s+22] = b'__TEXT' if executable else b'__DATA'
    struct.pack_into('<QI', d, s+40, 512, 512)
    struct.pack_into('<I', d, s+64, 0x80000400 if executable else 0)
    d[600:600+len(payload)] = payload
    return bytes(d)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backups = self.root / 'backups'
        # Synthetic Mach-O images have no real signature; native signing is tested separately.
        self.sign = patch.object(native, '_mac_sign_transaction')
        self.sign.start()
        self.verify = patch.object(native, '_mac_codesign_verify')
        self.verify.start()
        self.cache = patch.object(engine, 'invalidate_caches')
        self.cache.start()

    def tearDown(self):
        self.cache.stop()
        self.verify.stop()
        self.sign.stop()
        self.temp.cleanup()

    def target(self, data, kind='ide', name=None):
        path = self.root / (name or {'ide':'main.js','cli':'agy','manager':'language_server'}[kind])
        path.write_bytes(data)
        return engine.Target(kind, path.resolve())

    def test_ide_preserves_bytes_and_round_trips(self):
        t = self.target(IDE)
        self.assertEqual(engine.status(t)[0], 'ready')
        engine.patch_group([t], self.backups)
        changed = t.path.read_bytes()
        self.assertEqual(len(changed), len(IDE))
        self.assertTrue(changed.startswith(b'\xef\xbb\xbf// Unicode \xd0\x96'))
        self.assertIn(b'resetIsTierGCPTos(),true', changed)
        self.assertEqual(engine.patch_group([t], self.backups), 'Already patched.')
        engine.restore_group([t], self.backups)
        self.assertEqual(t.path.read_bytes(), IDE)
        self.assertIn('already restored', engine.restore_group([t], self.backups))

    def test_binaries_change_only_intended_bytes_all_formats_and_architectures(self):
        for constructor in (pe, elf, macho):
            for kind in ('cli','manager'):
                for arch in ('x64','arm64'):
                    with self.subTest(format=constructor.__name__, kind=kind, arch=arch):
                        payload = {'cli': {'x64': CLI_X64,'arm64':CLI_ARM64}, 'manager':{'x64':MANAGER_X64,'arm64':MANAGER_ARM64}}[kind][arch]
                        original = constructor(payload, arch)
                        t = self.target(original, kind, f'{constructor.__name__}-{kind}-{arch}')
                        p = engine.plan(t)
                        engine.patch_group([t], self.backups)
                        self.assertEqual(t.path.read_bytes(), original[:p.offset]+p.fix+original[p.offset+len(p.fix):])
                        engine.restore_group([t], self.backups)
                        self.assertEqual(t.path.read_bytes(), original)

    def test_signature_outside_executable_section_is_rejected(self):
        for constructor in (pe, elf, macho):
            t = self.target(constructor(CLI_X64, executable=False), 'cli')
            self.assertEqual(engine.status(t)[0], 'unsupported')
            original = t.path.read_bytes()
            with self.assertRaises((LookupError, ValueError)):
                engine.patch_group([t], self.backups)
            self.assertEqual(t.path.read_bytes(), original)

    def test_missing_duplicate_and_mixed_signatures(self):
        for data in (b'ordinary code', IDE*2, IDE+b'resetIsTierGCPTos(),true?x:y', b'resetIsTierGCPTos(),this.a.isGoogleInternalExtra?x:y'):
            t = self.target(data)
            with self.assertRaises(LookupError):
                engine.patch_group([t], self.backups)
            self.assertEqual(t.path.read_bytes(), data)
        t = self.target(pe(MANAGER_X64+b'\x90'*10+MANAGER_X64), 'manager')
        with self.assertRaises(native.SignatureAmbiguous):
            engine.patch_group([t], self.backups)

    def test_restore_does_not_overwrite_app_update(self):
        t = self.target(IDE)
        engine.patch_group([t], self.backups)
        updated = t.path.read_bytes()+b'// updated'
        t.path.write_bytes(updated)
        with self.assertRaisesRegex(OSError, 'changed since patch'):
            engine.restore_group([t], self.backups)
        self.assertEqual(t.path.read_bytes(), updated)

    def test_damaged_backup_is_rejected(self):
        t = self.target(IDE)
        engine.patch_group([t], self.backups)
        folder = engine.group_dir(t, self.backups)
        state = json.loads((folder/'current.json').read_text())
        (folder/state['version']/'original-0.bin').write_bytes(b'damaged')
        current = t.path.read_bytes()
        with self.assertRaisesRegex(OSError, 'Backup is damaged'):
            engine.restore_group([t], self.backups)
        self.assertEqual(t.path.read_bytes(), current)

    def test_write_failure_rolls_back_exactly(self):
        t = self.target(IDE)
        actual = engine.write_patch
        def fail_after_write(*args):
            actual(*args)
            raise OSError('Injected failure after mutation')
        with patch.object(engine, 'write_patch', side_effect=fail_after_write):
            with self.assertRaisesRegex(OSError, 'Original files restored'):
                engine.patch_group([t], self.backups)
        self.assertEqual(t.path.read_bytes(), IDE)

    def test_signing_failure_rolls_back_binary(self):
        t = self.target(macho(CLI_ARM64, 'arm64'), 'cli')
        original = t.path.read_bytes()
        with patch.object(engine.sys, 'platform', 'darwin'), patch.object(native, '_mac_sign_transaction', side_effect=OSError('Signing failed')):
            with self.assertRaisesRegex(OSError, 'Original files restored'):
                engine.patch_group([t], self.backups)
        self.assertEqual(t.path.read_bytes(), original)

    def test_backup_path_tampering_is_rejected(self):
        t = self.target(IDE)
        engine.patch_group([t], self.backups)
        f = engine.group_dir(t, self.backups)/'current.json'
        data = json.loads(f.read_text())
        data['entries'][0]['path'] = str(self.root/'outside.js')
        f.write_text(json.dumps(data))
        with self.assertRaisesRegex(OSError, 'Unexpected target'):
            engine.restore_group([t], self.backups)

    def test_legacy_powershell_backup_can_be_restored(self):
        t = self.target(IDE)
        p = engine.plan(t)
        changed = IDE[:p.offset]+p.fix+IDE[p.offset+len(p.fix):]
        t.path.write_bytes(changed)
        original_hash = hashlib.sha256(IDE).hexdigest()
        changed_hash = hashlib.sha256(changed).hexdigest()
        legacy = Path(str(t.path)+'.agpatch-backups')
        legacy.mkdir()
        (legacy/(original_hash+'.bin')).write_bytes(IDE)
        Path(str(t.path)+'.agpatch-state').write_text(f'AGPATCH1\n{original_hash}\n{changed_hash}\n')
        engine.restore_group([t], self.backups)
        self.assertEqual(t.path.read_bytes(), IDE)

    def test_mode_is_preserved(self):
        if os.name == 'nt':
            self.skipTest('POSIX permissions only')
        t = self.target(elf(CLI_X64), 'cli')
        t.path.chmod(0o755)
        engine.patch_group([t], self.backups)
        engine.restore_group([t], self.backups)
        self.assertEqual(t.path.stat().st_mode & 0o777, 0o755)


class InterfaceTests(unittest.TestCase):
    def test_self_test_is_isolated_and_english(self):
        from antigravity_patcher.application import main
        with patch.object(engine, 'invalidate_caches', side_effect=AssertionError('Must not inspect live caches')):
            self.assertEqual(main(['--self-test']), 0)

    def test_custom_path_is_used(self):
        from antigravity_patcher.application import discover
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/'main.js'
            file.write_bytes(IDE)
            targets = discover({'ide':str(file), 'cli':'', 'manager':''})
            self.assertIn(engine.Target('ide', file.resolve()), targets)


if __name__ == '__main__':
    unittest.main()
