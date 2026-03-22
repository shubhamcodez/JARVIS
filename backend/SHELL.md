# Host shell agent (`shell`)

The **shell** route runs real **PowerShell** (Windows, if `bash` is not on PATH) or **bash/sh** (Unix / Git Bash) under a fixed working directory. This is the same capability as “run `mkdir`, `rm`, list drives” on the machine where the **backend** runs—not in the Python sandbox.

## Enable (required)

```bash
set JARVIS_ENABLE_SHELL=1
```

(Use `export` on Unix.) Restart the API after changing env.

If disabled, the supervisor will not choose `shell`, and the shell agent returns a short message pointing here.

**Persist without typing PowerShell each time:** add the same line to **`E:\JARVIS\.env`** (project root). `backend/config.py` loads that file on startup, so you only restart the server after editing.

### Do I need `JARVIS_SHELL_WORKDIR` to use drive `E:\`?

**No.** `JARVIS_SHELL_WORKDIR` only sets the **starting folder** for each command (`cwd`). It does **not** lock you to that drive.

- You can always use **absolute paths** on any drive, e.g. `Get-ChildItem E:\`, `dir E:\`, `bash -lc 'ls /e/'` (Git Bash), `New-Item E:\MyFolder -ItemType Directory`.
- If your repo is already `E:\JARVIS`, the default workdir is **`E:\JARVIS\jarvis-shell-work`** — you are already on **`E:`**.

Set `JARVIS_SHELL_WORKDIR=E:\` (or `E:\some\folder`) **only** if you want every command to start in the root of `E:\` (or that folder) without typing `cd` each time.

## Configuration

| Variable | Effect |
|----------|--------|
| `JARVIS_ENABLE_SHELL` | `1` / `true` / `yes` / `on` to allow shell agent and `POST /tools/shell`. |
| `JARVIS_SHELL_WORKDIR` | Default: `<repo>/jarvis-shell-work`. All commands start in this directory (created if missing). |
| `JARVIS_SHELL` | Force backend: `bash`, `powershell`, or `sh`. |
| `JARVIS_SHELL_TIMEOUT` | Seconds per command (default `120`). |
| `JARVIS_SHELL_MAX_OUTPUT` | Max characters kept from stdout/stderr each run (default `32000`). |

On Windows, if `bash.exe` is on `PATH` (e.g. Git for Windows), it is used unless you set `JARVIS_SHELL=powershell`.

## Security warning

- **Not a sandbox.** Anyone who can call your JARVIS API with shell enabled can read/write/delete files the backend user can access (within OS permissions).
- A few **high-risk patterns** are blocked (e.g. `rm -rf /`), but **`rm -rf` on your projects or home folder is still allowed** if the process can access those paths—use only on trusted machines.
- Prefer running the backend as a **low-privilege** user and keeping `JARVIS_SHELL_WORKDIR` on a dedicated folder.

## API

- **Agent:** Supervisor may return `agent: "shell"` when `JARVIS_ENABLE_SHELL=1` (or use phrases like “mkdir”, “powershell”, “list drives”—see `supervisor.py` heuristics).
- **Direct:** `POST /tools/shell` with JSON `{ "command": "...", "timeout_sec": 60 }` returns the same dict shape as `run_shell_command()` in `tools/shell_runner.py`.

## Git

The default workdir `jarvis-shell-work/` is listed in `.gitignore`.
