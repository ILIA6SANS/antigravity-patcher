# Publication privacy check — 2026-10-14

Scope: the prepared source archive and Windows x64 release archive, including
the executable's compressed Python archive and the bundled base-library bytecode.

The initial check scanned 89 archive members and 8,907 embedded code objects.
No requester profile name/path, chat identifier, clipboard attachment identifier,
private-key block or tested API/token format was found. Embedded application
filenames are relative module paths, not the build machine's home directory.

Application source excludes account/token storage and quota/network functions.
Fixtures contain synthetic data. Source archives exclude build logs, Git metadata,
local backups, caches and the development workspace.

The `github.token` expression in release.yml is a GitHub-generated workflow
credential reference. It is not a saved personal token or credential value.
Public upstream attribution and license author information remain in the files.

This is a targeted artifact privacy check, not a guarantee of absence of all
possible defects. The patcher modifies local application files; fixture tests
and backup/rollback guards do not replace validation against every real build.
Linux/macOS native packages still require their CI builds and runtime checks.
