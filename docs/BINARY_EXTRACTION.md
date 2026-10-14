# Original binary extraction

The `agentdecompile-cli extract-binary` implementation exports the original
FileBytes stored in an existing Ghidra program when the source file is gone.
It does not import, analyze, save or check out the program. The current recovery
mission still routes operations through the existing 8080 action catalog; these
examples describe the standalone command interface, not authorization to start
another JVM against an owner-held project.

```sh
agentdecompile-cli extract-binary /path/project.gpr --program /folder/app.exe --output /home/user/recovered/app.exe
agentdecompile-cli extract-binary /path/project-folder --program /app.exe --output /home/user/recovered/app.exe
agentdecompile-cli extract-binary /shared-folder --shared --program app.exe --output /home/user/recovered/app.exe
```

A local folder must contain exactly one `.gpr`; otherwise pass the desired file.
`--program` selects a program explicitly, including nested project paths. With
`--shared`, PROJECT identifies a folder in the configured Ghidra Server repository;
existing CLI host/port/repository/username `--ghidra-server-*` options and the
shared-server configuration supply connection details. Shared extraction uses
the existing SSH authenticator (`GHIDRA_SERVER_SSH_KEY`); password authentication
is unsupported by this extraction path. A shared folder is not a raw server
storage/database folder.
PyGhidra and `GHIDRA_INSTALL_DIR` are required. A project held by another process
may fail to open; leave that owner's project and lock intact.

Existing outputs are never overwritten. One FileBytes blob writes to `--output`;
multiple blobs write separate files suffixed with their index and sanitized stored
filename. JSON reports the project, program, stored executable path/hash, each
blob's original file offset, size, output path and SHA-256. A failed read attempts
to remove that blob's incomplete output after closing it; earlier complete blobs may remain if a later blob
fails. Reruns therefore require a new destination or deliberate cleanup.

The older corpus `export-bytes` implementation explicitly opts into refreshing
its outputs through temporary files, preserving an existing blob when a new read
fails. Failed or skipped exports return a failure status and preserve its previous
manifest. This legacy refresh behavior does not change `extract-binary`'s default.

`whole_original_file_verified` is true only for a single blob starting at offset
zero whose SHA-256 matches Ghidra's stored executable SHA-256. Without that match,
the result establishes complete stored FileBytes extraction, not independent
whole-file identity. Multiple blobs are not silently concatenated. Programs with
no FileBytes fail explicitly: reconstructed memory cannot restore absent headers,
overlays or original layout, and is never substituted for the original file.

This command's source was reviewed without tests, builds, service restart or live
extraction under the current mission constraints. Installed and live behavior
remain unverified.
