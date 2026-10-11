# PHI Protect

Catches patient information (PHI) in Claude Code before it reaches Claude, and gives you a
de-identified version to send instead.

- **Checks** every prompt you send and every file Claude reads.
- **Flags, doesn't stop you:** likely PHI is held back with a de-identified version ready; on a false
  alarm you proceed in one step.
- **Stays on your machine:** the detection model runs locally, works offline after setup, and never logs
  or sends your text.

## Requirements

| | |
|---|---|
| Claude Code | Installed and logged in; 2.1.295 or later recommended |
| System | Linux, WSL, Windows x64, or macOS 14+ on Apple Silicon (no Intel Macs) |
| Resources | ~2.5 GB disk, ~1 GB memory |
| Network | Internet for the first install only |
| Tools | `git`; `uv` (step 1) |

## Install

### 1. Install `uv`

Skip if `uv --version` already works.

macOS, Linux, WSL:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Open a new terminal afterwards.

### 2. Install the `phi-protect` command

```bash
git clone https://github.com/harigovind011235/phi-protect.git
uv tool install ./phi-protect
```

Takes a few minutes. Check it with `phi-protect --help`. If the command is not found, run
`uv tool update-shell` and open a new terminal.

### 3. Connect it to Claude Code

```bash
phi-protect setup
```

This takes about a minute the first time. It:

1. downloads the detection model (~0.4 GB, once),
2. runs a self-test,
3. adds the PHI Protect hooks to `~/.claude/settings.json` for all projects (the old file is backed up
   next to it),
4. starts the PHI Protect service in the background.

**WSL users:** Claude Code started on the Windows side (VS Code not connected to WSL, the desktop app)
reads its own Windows settings. Cover it too by running this from WSL instead:

```bash
phi-protect setup --windows
```

### 4. Check it is running

```bash
phi-protect status
```

Expect `Service: running` and `Hooks for all projects: installed`.

### 5. Try it

Start a **new** Claude Code session in the cloned folder (hooks load when a session starts):

```bash
cd phi-protect && claude
```

The first message can take ~10 seconds while the model loads. All data in `examples/` is fake.

| Type in Claude Code | Expected |
|---|---|
| `Draft an appeal for Maria Lopez, DOB 03/14/1985, member ID XGH884213901` | Held back; a de-identified version is on your clipboard |
| `Read examples/eob_with_phi.pdf and summarize it` | Permission dialog listing the PHI types found |
| `Read examples/clean_benefits.pdf. What is the frequency limit for D2740?` | Works normally |
| `Read examples/scanned_page.pdf` | Permission dialog: images cannot be checked |

## Everyday use

**A prompt was flagged.** Nothing was sent. Pick one:

- **Send the de-identified version:** it is already on your clipboard. Paste, check, send.
- **Send the original (false alarm):** copy it again and send it within 5 minutes. The same patient data
  sent again goes through once.
- **Skip the check:** put `[phi-ok]` anywhere in the prompt.

**A file read was flagged.** Claude Code asks for permission. Allow it on a false alarm; otherwise deny,
then create a de-identified copy (PDF or text) and use that:

```bash
phi-protect deidentify path/to/file.pdf
```

**"PHI Protect could not check …"** means the service is down; your work continues with this warning.
Run `phi-protect status`, then `phi-protect start`. The log, which never contains your text, is
`~/.phi-protect/service.log`.

**A repo has test fixtures with fake patients.** List those paths in a `.phi-protect-ignore` file at the
repo root, one pattern per line:

```
# Only files with FAKE patient data.
tests/fixtures/
samples/*.csv
```

Reads of matching files are no longer checked; prompts always are. The file only takes effect once
committed to git and unchanged, so every exception is reviewed. `*`, `**`, absolute paths and `..` are
rejected.

## Commands

| Command | What it does |
|---|---|
| `phi-protect setup` | Download the model, add the hooks, start the service. `--windows`: also cover Windows-side Claude Code (run from WSL). `--project DIR`: one project only |
| `phi-protect status` | Show the service state and where hooks are installed |
| `phi-protect start` / `stop` | Start or stop the background service (it also starts with each Claude Code session) |
| `phi-protect deidentify FILE [-o OUT]` | Write a de-identified copy of a PDF or text file |
| `phi-protect uninstall` | Remove only the PHI Protect hooks and stop the service; add `--windows` / `--project DIR` to match setup |
| `phi-protect serve` | Run the service in the foreground (debugging) |

**Update:**

```bash
cd phi-protect && git pull && uv tool install --reinstall . && phi-protect setup
```

**Remove completely:**

```bash
phi-protect uninstall && uv tool uninstall phi-protect
```

## What it checks

- **Detects:** names, dates of birth and service, SSN, phone, email, street address, PO box, city, ZIP,
  member/subscriber, group, claim, MRN/account and Medicare IDs, and patient fields in X12 files
  (837, 835, 270/271).
- **Leaves alone:** dentist names with "Dr.", NPI/TIN, payer names, CDT codes, amounts, versions, hashes,
  usernames in file paths, and AI tool names such as Claude.
- **Cannot check, so always asks:** scanned pages and images, fillable or annotated PDFs, encrypted
  PDFs, Word/Excel files, and files over 25 MB, 50 pages or 50,000 characters.
- **Not covered yet:** shell command output (e.g. `cat claims.csv`), Grep results, MCP/database tool
  results, pasted images, and `@file` mentions.
- **Speed:** about a second per prompt or file; a 10-page PDF takes ~10 seconds.

## Configuration

Set as environment variables. For the hooks, put them in the `env` section of the Claude Code settings
file, then re-run `phi-protect setup`.

| Variable | Default | Meaning |
|---|---|---|
| `PHI_MODE` | `warn` | `warn`: flag and let the user decide. `block`: enforce; PHI and anything uncheckable is blocked, and resends and `[phi-ok]` are ignored |
| `PHI_SERVICE_URL` | local service | Where the hooks reach the service, e.g. a shared on-prem server |
| `PHI_HOST`, `PHI_PORT` | `127.0.0.1`, `8765` | Where the service listens |
| `PHI_SCORE_THRESHOLD` | `0.5` | Minimum model confidence (0–1); rule-based detection always applies |
| `PHI_MAX_CONCURRENT_SCANS` | `1` | Model scans run at the same time |
| `PHI_MAX_FILE_BYTES`, `PHI_MAX_FILE_TEXT_CHARS`, `PHI_MAX_PDF_PAGES` | 25 MB, 50,000, 50 | File limits |

Tested on Linux and WSL, including Windows-side hooks bridged into WSL through `cmd` and PowerShell.
Native macOS and Windows installs are not yet tested.

## Development

Architecture, layers and conventions are in [CLAUDE.md](CLAUDE.md).

```bash
uv sync                              # install dependencies
uv run python -m phi_protect.main    # run the service on 127.0.0.1:8765
```

**HTTP API** (used by the hooks; all processing is local):

| Endpoint | Input | Returns |
|---|---|---|
| `POST /scan` | JSON `{"text": "..."}` | `has_phi`, detected entities, `deidentified_text` |
| `POST /scan-file` | multipart `file` | `decision` (`allow` / `block` / `cannot_verify`), `reason`, `entity_counts` |
| `POST /deidentify-file` | multipart `file` | De-identified PDF or text; 422 with `reason` if it cannot be checked |
| `GET /health` | | `{"status": "ok"}` |

De-identified PDFs are rebuilt from page images with labeled black boxes, so no redacted text can be
recovered. Downloads are always named `deidentified.*` because file names can contain PHI.

**Accuracy** is measured on synthetic data only (never add real PHI):

```bash
uv run python -m evaluation.evaluate                                 # synthetic set
uv run python -m evaluation.evaluate evaluation/data/holdout.txt     # team-written held-out set
```

To build the held-out set, copy `evaluation/holdout_template.txt` to `evaluation/data/holdout.txt` and
follow its instructions. Use it for go/no-go checks only; never tune against it.

**Quality gates** (run all before a change is done):

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check --summarize-errors
uv run pytest
```
