# PHI Protect

Detects PHI in text before it is sent to AI tools, and returns a de-identified version.

The PHI detection service (this repo, step 1) combines:
- Rules for structured identifiers: SSN, phone, email, labeled member/group/claim/MRN IDs, labeled dates (DOB, date of service), names after "patient"/"pt", Medicare MBI, street address (including lowercase and PO boxes), city/ZIP, and X12 address/date segments.
- NER model [`StanfordAIMI/stanford-deidentifier-base`](https://huggingface.co/StanfordAIMI/stanford-deidentifier-base) (MIT) for names, dates and unlabeled IDs, run through Microsoft Presidio.

Known non-PHI (payer names, CDT codes, NPI/taxonomy values, provider names with a "Dr." title, versions) is filtered in `src/phi_protect/domain/policy/allowlist.py`. The allowlist only overrules the model's guesses; labeled identifiers such as `MRN: ...` are never allowlisted.

Everything runs locally. The model (pinned to a fixed revision) is downloaded once from Hugging Face and cached; text is never logged or sent anywhere, and validation errors never echo the submitted text. After the first run, start the service with `HF_HUB_OFFLINE=1` so it cannot reach Hugging Face at all. Presidio's email detector may still fetch the public domain-suffix list; it never sends scanned text.

The code follows clean architecture (domain, use cases, adapters, handler); see [CLAUDE.md](CLAUDE.md) for the layers, conventions and how to add or swap an adapter.

## Getting started

PHI Protect checks every prompt you send and every file Claude reads in Claude Code. If it finds
patient information, it blocks it before anything reaches Claude and shows you a de-identified version.
Everything runs on your machine.

**You need:** Claude Code installed and logged in (2.1.295 or later recommended), about 2.5 GB of free
disk, about 1 GB of free memory, and internet access for the first install only. Supported: Linux,
Windows (x64), WSL, and macOS on Apple Silicon with macOS 14 or later (PyTorch no longer ships builds
for Intel Macs).

**1. Install `uv`** (installs Python tools; skip if `uv --version` works):

- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Then open a new terminal.

**2. Get the project and install the `phi-protect` command** (a few minutes the first time):

```bash
git clone <repo-url> phi_protect
uv tool install ./phi_protect
```

Check it worked with `phi-protect --help`. If the command is not found, run `uv tool update-shell` and
open a new terminal.

**3. Connect it to Claude Code** (about a minute the first time):

```bash
phi-protect setup
```

This downloads the detection model, runs a self-test, adds the PHI Protect hooks to your Claude Code
settings (`~/.claude/settings.json`, backed up first) for all projects, and starts the service in the
background. If it suggests `claude update`, do that and run `phi-protect setup` again.

Setup covers Claude Code running in the same environment you ran it in. **WSL users:** Claude Code
started on the Windows side (VS Code not connected to WSL, the desktop app) uses its own Windows
settings. To cover it too, run this from WSL instead; Windows-side hooks then call your WSL install:

```bash
phi-protect setup --windows
```

Alternatively, open projects in VS Code connected to WSL (`code .` from a WSL terminal; the bottom-left
corner shows "WSL"), so the extension runs inside WSL. On Windows without WSL, run the same commands in
PowerShell; that path is not yet tested.

**4. Check it is running:**

```bash
phi-protect status
```

**5. Try it.** Open a new Claude Code session in any folder (`claude`, or a new session in the IDE
extension or desktop app). The first message after a session starts can take about 10 seconds while the
model loads. The `examples/` folder in this repo has fake files to test with:

| In Claude Code | What happens |
|---|---|
| `Draft an appeal for Maria Lopez, DOB 03/14/1985, member ID XGH884213901` | Blocked; you see a de-identified version to review and resend |
| `Read examples/eob_with_phi.pdf and summarize it` | The read is blocked; Claude tells you why (types of PHI only, never the values) |
| `Read examples/clean_benefits.pdf. What is the frequency limitation for D2740?` | Works normally |
| `Read examples/scanned_page.pdf` | Blocked: images cannot be checked for PHI |

### Everyday use

PHI Protect is a helper: it flags likely patient information and you decide.

- **A prompt was flagged:** it was held back, and you choose:
  - **Send a de-identified version:** it is already on your clipboard (Windows, macOS, WSL; Linux needs
    `wl-copy` or `xclip`). Paste it, check it, send it.
  - **It is a false alarm, send the original:** copy it again and send it within 5 minutes. The same
    patient data sent again goes through as-is (the surrounding text may differ). Only a salted
    fingerprint is kept, never the data, and it works once.
  - **Skip the check up front:** put `[phi-ok]` anywhere in a prompt and it is sent without checking.
- **A file read was flagged:** Claude Code asks for permission. Allow it if it is a false alarm; otherwise
  deny and make a de-identified copy with `phi-protect deidentify path/to/file.pdf`.
- **"PHI Protect could not check …":** the service is not running or failed; your work continues with a
  warning. Run `phi-protect status`, then `phi-protect start`; the log is in `~/.phi-protect/service.log`
  (it never contains your text).
- **Enforcing instead of helping (later):** set `PHI_MODE=block` (e.g. in the `env` section of the Claude
  Code settings) and re-run `phi-protect setup`. Then PHI, and anything that cannot be checked, is blocked.
- **A repo has test fixtures with fake patients:** list those paths in a `.phi-protect-ignore` file at the
  repo root (one pattern per line, e.g. `tests/fixtures/`). Reads of listed files are not checked; prompts
  always are. It only takes effect once committed to git and unchanged, so every exception is reviewed.
  Never list folders that can hold real data. Patterns that match everything (`*`) are rejected.
- **Update to a new version:** `git pull` in the project folder, then `uv tool install --reinstall ./phi_protect`
  and `phi-protect setup`.
- **Remove it:** `phi-protect uninstall` (add `--windows` if you set it up that way; removes only the PHI
  Protect hooks and stops the service), then `uv tool uninstall phi-protect`.

### What it does not cover yet

Shell command output (e.g. `cat claims.csv`), Grep results, database/MCP tool results, pasted images,
and `@file` mentions in prompts. Each check adds about a second to a prompt or file read; large PDFs take
longer. Tested on Linux (WSL), including Windows-side hooks bridged into WSL through `cmd` and
PowerShell; native macOS and native Windows installs are not yet tested.

## Run the service directly

```bash
uv sync
uv run python -m phi_protect.main
```

The service listens on `127.0.0.1:8765` only.

```bash
curl -s localhost:8765/scan -H 'content-type: application/json' \
  -d '{"text": "Appeal for Maria Lopez, member ID XGH884213901"}'
```

Response:

```json
{"has_phi": true, "entities": [...], "deidentified_text": "Appeal for [PERSON_1], member ID [MEMBER_ID_1]"}
```

`has_phi` is true when anything other than an unlabeled date is found. Unlabeled dates (`DATE_TIME`) are replaced but do not block on their own; labeled patient dates (`PATIENT_DATE`, e.g. `DOB: ...`) do block.

`deidentified_text` is a suggestion for the user to review, not something to forward automatically: detection can miss values.

### Files

```bash
curl -s localhost:8765/scan-file -F "file=@eob.pdf"
# {"decision": "block", "file_type": "pdf", "reason": null, "entity_counts": {"PERSON": 1, "MEMBER_ID": 1}}

curl -s localhost:8765/deidentify-file -F "file=@eob.pdf" -o deidentified.pdf
```

`decision` is `allow`, `block` or `cannot_verify`. Supported: PDFs with a text layer and any plain-text file (CSV, JSON, logs, X12, code). The file type is detected from the content, not the name.

`cannot_verify` (with a `reason`) is returned instead of guessing for: scanned pages or large images (x-rays, screenshots), fillable forms, comments/annotations, encrypted or damaged PDFs, other binary formats (Word, Excel, images), files over 25 MB, PDFs over 50 pages, and more than 50,000 characters of text. Connectors should treat it as a block.

The de-identified PDF is rebuilt from page images with labeled black boxes, so it has no text layer and redacted text cannot be recovered from it. The download is always named `deidentified.pdf`/`.txt`, because original file names can contain PHI.

Speed: the NER model reads about 3,500 characters per second on CPU, so a 10-page PDF takes around 10 seconds.

Settings (environment variables): `PHI_NER_MODEL`, `PHI_NER_MODEL_REVISION`, `PHI_SCORE_THRESHOLD` (default 0.5, must be between 0 and 1; applies to model findings), `PHI_MAX_CONCURRENT_SCANS` (default 1), `PHI_MAX_FILE_BYTES`, `PHI_MAX_FILE_TEXT_CHARS`, `PHI_MAX_PDF_PAGES`.

## Measure accuracy

The test set is synthetic (Faker). Never add real PHI to it.

```bash
uv run python -m evaluation.generate
uv run python -m evaluation.evaluate
```

A PHI value only counts as removed if every character of it is redacted. The report also shows how many PHI prompts still contain PHI after redaction, and how much harmless text was redacted.

Held-out set: the team writes realistic fake prompts in `evaluation/data/holdout.txt` (format and rules in `evaluation/holdout_template.txt`). It is for go/no-go checks only; never tune the detector against it.

```bash
uv run python -m evaluation.evaluate evaluation/data/holdout.txt
```

## Quality gates

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check --summarize-errors
uv run pytest
```
