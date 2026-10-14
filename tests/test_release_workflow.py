"""Run the real release shell step with a fake gh command; no network writes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]


def bash_path():
    if os.name == 'nt':
        git = shutil.which('git')
        if git:
            candidate = Path(git).resolve().parents[1] / 'bin/bash.exe'
            if candidate.is_file():
                return str(candidate)
        return None
    return shutil.which('bash')


class ReleaseWorkflowTests(unittest.TestCase):
    def execute(self, state):
        bash = bash_path()
        if not bash:
            self.skipTest('Bash is required to exercise the release workflow')
        source = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        shell = textwrap.dedent(source.rsplit('        run: |\n', 1)[1])
        fake = r'''
set -e
python3() { printf '%s\n' 'v0.2.0'; }
gh() {
  printf '%s\n' "$*" >> "$TRACE_FILE"
  if [ "$1 $2" = 'release view' ]; then
    if [ "$RELEASE_STATE" = 'missing' ]; then return 1; fi
    case "$*" in
      *--json*) if [ "$RELEASE_STATE" = 'draft' ]; then printf 'true\n'; else printf 'false\n'; fi ;;
      *) printf 'v0.2.0\n' ;;
    esac
    return 0
  fi
  return 0
}
'''
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            trace = folder / 'trace.txt'
            script = folder / 'workflow.sh'
            script.write_text(textwrap.dedent(fake)+shell, encoding='utf-8', newline='\n')
            env = os.environ.copy()
            env.update(RELEASE_STATE=state, TRACE_FILE=trace.as_posix(), GITHUB_SHA='test-commit')
            result = subprocess.run([bash, script.as_posix()], env=env, cwd=ROOT,
                                    capture_output=True, text=True)
            calls = trace.read_text().splitlines()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return calls

    def test_published_release_is_successful_noop(self):
        calls = self.execute('published')
        self.assertTrue(calls)
        self.assertFalse(any(c.startswith(('release create','release upload')) for c in calls))

    def test_existing_draft_accepts_assets(self):
        calls = self.execute('draft')
        self.assertTrue(any(c.startswith('release upload v0.2.0 ') and '--clobber' in c for c in calls))
        self.assertFalse(any(c.startswith('release create') for c in calls))

    def test_missing_release_creates_draft(self):
        calls = self.execute('missing')
        self.assertTrue(any(c.startswith('release create v0.2.0 ') and '--draft' in c and '--target test-commit' in c for c in calls))
        self.assertFalse(any(c.startswith('release upload') for c in calls))
