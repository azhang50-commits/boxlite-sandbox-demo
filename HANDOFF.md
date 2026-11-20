# Current release handoff

This repository now contains the runnable customer-facing Mac demo as ordinary source files. The earlier archive-only WIP checkpoint remains in Git history.

Start with README.md, 使用说明.md, docs/PRESENTATION.zh-CN.md, and docs/VALIDATION.md. The supported entry point is Start BoxLite Demo.command. Two real local BoxLite microVMs run the HTML service and Python games. The native Key dialog is optional; the local path does not use Cloud credentials.

The shared scenario, independent scenario, and full browser tour passed on Apple Silicon. Twelve local tests cover game, stream, recovery, and credential-file behavior. See validation notes for limits. No real credentials, runtime directories, or SDK binaries belong in this repository or release ZIP.

The original Cloud Runner failure is not fixed by this release. Do not treat historical deployment addresses or scripts as a supported live endpoint. No existing Cloud Boxes were deleted or had their idle-stop policy disabled during local packaging.
