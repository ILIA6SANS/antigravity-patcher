# Contributing

Run `python -m unittest discover -s tests -v` with `PYTHONPATH=src` before opening
a pull request. Runtime code must use the standard library, remain offline and
avoid reading account credentials.

For a new binary signature, provide the app version, OS, architecture and
instruction context. Match executable sections, require one unique match and
include both original and patched recognition. Verify that only the intended
bytes change and that restoring the backup returns the exact original file.
Never replace fixed offsets without contextual validation.

The application interface and diagnostics are English. Keep README.md in Russian.
Do not include tokens, profile databases, private logs or proprietary application
binaries in issues or pull requests. Native signing behavior must be checked on
the corresponding OS before claiming support for a new architecture.
