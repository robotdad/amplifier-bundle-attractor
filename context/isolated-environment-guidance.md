# Isolated Environment Execution

You are executing inside an isolated environment (Docker container or remote host).
All file and command operations MUST use the environment tools:

- `env_exec` -- execute shell commands (replaces `bash`)
- `env_read_file` -- read file contents (replaces `read_file`)
- `env_write_file` -- write file contents (replaces `write_file`)
- `env_edit_file` -- edit file with string replacement (replaces `edit_file`)
- `env_apply_patch` -- apply V4A file patches (replaces `apply_patch`)
- `env_grep` -- search file contents (replaces `grep`)
- `env_glob` -- find files by pattern (replaces `glob`)
- `env_list_dir` -- list directory contents
- `env_file_exists` -- check if a file exists

Do NOT use `bash`, `read_file`, `write_file`, `edit_file`, `apply_patch`, `grep`, or `glob` directly.
Those tools operate on the host filesystem and would bypass the isolated environment.

All environment tools accept an optional `instance` parameter (default: "local").
If an environment instance was created for this session, use the instance name provided.
