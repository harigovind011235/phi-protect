# PHI Protect — Engineering Guide

## What This Service Does

A local service that finds PHI (patient names, DOB, member/claim/MRN numbers, addresses, ...) in text
and files before they reach AI tools, and returns a de-identified version. Built for a US dental RCM
company whose AI tools have no HIPAA BAA. Connectors (the Claude Code hook next, a browser extension
later) call it and block when it says so.

Everything runs locally: the NER model is downloaded once and cached; text is never logged or sent
anywhere.

## Architecture — Clean / Hexagonal (Ports & Adapters)

Four layers; **dependencies point inward only**. The domain knows nothing about Presidio, PyTorch,
PDFium or FastAPI.

```
handler ─▶ usecases ◀─ adapters
                ▲
             domain  (innermost; pure Python)
```

- **`domain/`** (Layer 1) — pure Python, standard library only. Models, detection rules, policy.
  - `models/` — `Finding` (span + type + score + source), `EntityType`, `Decision`.
  - `rules/` — regex rules for structured PHI (labeled IDs/dates/names, addresses, X12, phone, MBI).
    They run alongside any detector, so swapping detectors keeps them.
  - `policy/` — what is PHI and what blocks: allowlist, overlap merging, blocking, placeholders.
- **`usecases/`** (Layer 2) — orchestration. Owns both sets of contracts:
  - `usecases/interfaces/` — **driving ports** (what handlers call): `ScanServiceInterface`, `FileServiceInterface`.
  - `usecases/ports/` — **driven ports** (what adapters implement): `detectors/PhiDetector`, `documents/DocumentFormat`.
  - `dtos/` — `ScanResult`, `FileScanResult`, `DeidentifiedFile`. `errors.py` — `UnverifiableFileError`.
- **`adapters/`** (Layer 3) — implementations of driven ports: `PresidioPhiDetector` (Presidio + spaCy +
  Hugging Face model), `PdfiumPdfFormat`, `PlainTextFormat`.
- **`handler/`** (Layer 4) — FastAPI app + routes. Reads the container off `app.state` and delegates.
- **`cli/`** (Layer 4, second entry point) — the `phi-protect` command and the Claude Code hook. The hook
  is a *client* of the running service over HTTP (`service_client.py`) and never loads the model;
  `service_process.py` runs the service in the background; `claude_settings.py` installs/removes hooks.

**Composition root.** `src/phi_protect/composition.py` is the *only* place adapters are instantiated
and wired to ports. `Container` is a frozen dataclass built once by `create_container(settings)` and
stored on `app.state.container`. No module-level singletons or `lru_cache` tricks.

**Swap test.** To replace the detector (e.g. GLiNER, an ONNX model, a remote GPU service), write a new
adapter against `PhiDetector` and change one line in `composition.py`. Allowlist, merging, blocking and
placeholders do not move, because they are domain policy applied by the use case.

**Adding an adapter:** (1) define/locate its port ABC under `usecases/ports/`, (2) implement it in
`adapters/`, (3) wire it in `create_container()`. For tests, build services or a `Container` with
fakes from `tests/fakes.py` — never patch globals.

## Async Rule

Ports and use cases are `async`. The work is CPU-bound (model inference, PDF rendering), and async does
not make it faster — it keeps the server responsive and lets a future remote detector be a drop-in.
**Anything CPU-heavy lives in an adapter and runs via `asyncio.to_thread`**; running it directly in an
`async def` freezes the whole server. `PresidioPhiDetector` limits concurrent model runs with a
semaphore (`PHI_MAX_CONCURRENT_SCANS`). PDFium is not thread-safe: all PDFium calls go through the
adapter's lock. Domain code stays plain sync Python.

## Project Structure

```
phi_protect/
├── src/phi_protect/
│   ├── main.py                    Entry point — `python -m phi_protect.main` (127.0.0.1:8765)
│   ├── composition.py             Composition root: Container + create_container()
│   ├── config/settings.py         pydantic-settings, PHI_* env vars; ALWAYS use create_settings()
│   ├── domain/                    models/, rules/, policy/
│   ├── usecases/                  interfaces/, ports/, dtos/, errors.py, scan_service.py,
│   │                              file_service.py, phi_search.py (shared: detector + rules + policy)
│   ├── adapters/                  detectors/ (Presidio + HF model), documents/ (PDF, plain text)
│   ├── handler/                   app.py (create_app), dependencies.py, errors.py, routes/
│   └── cli/                       main.py (`phi-protect`), hook.py, service_client.py,
│                                  service_process.py, claude_settings.py, ignore_file.py,
│                                  clipboard.py, wsl.py (Windows-side Claude Code → WSL bridge)
├── tests/                         Mirrors src/: domain/, usecases/, adapters/, handler/, + end to end
└── evaluation/                    Synthetic test set, held-out template, scoring script
```

## HTTP Surface

| Route | Purpose |
|---|---|
| `GET /health` | Liveness |
| `POST /scan` `{"text"}` | `has_phi`, entities, `deidentified_text` |
| `POST /scan-file` (multipart `file`) | `decision`: `allow` / `block` / `cannot_verify` (+ `reason`, `entity_counts`) |
| `POST /deidentify-file` (multipart `file`) | De-identified PDF or text; 422 `cannot_verify` with reason |

## Key Conventions & Invariants

- **Never log, echo or persist submitted content.** Validation errors return field names only; error
  messages never contain file content; downloads are always named `deidentified.*` (file names can be PHI).
- **Never use real PHI anywhere** — tests, evaluation, examples. Synthetic data only (Faker).
- **Fail closed.** Anything that cannot be fully checked (scanned pages, images, forms, annotations,
  encrypted PDFs, unsupported binaries, size limits) is `cannot_verify`, never `allow`.
- **Policy order matters.** The allowlist runs per candidate *before* merging, so it can veto one
  detector's guess but never erase another detector's finding. Only detector findings of types
  `PERSON`, `ID`, `PHONE_NUMBER`, `DATE_TIME` can be allowlisted; rule findings never are.
- **Merging is order-independent.** The merged span covers all members; its label comes from the best
  member: blocking > specific (not generic `ID`) > rule over detector > own score. Rule and detector
  scores are not on the same scale, so never compare them directly.
- **Dates:** unlabeled `DATE_TIME` is replaced but does not block; labeled `PATIENT_DATE` blocks.
- **Keep `HCW` mapped to `PERSON`** in the detector: the Stanford model labels most patients as HCW.
- **`deidentified_text` is a suggestion for a human**, never forwarded automatically by connectors.
- **DTOs cross layer boundaries; domain models do not.** Handlers return DTOs only.
- **Measure every detection change** with `evaluation/evaluate.py`; never tune against the held-out set.

## Claude Code Hook

- Events: `SessionStart` (starts the service if it is not running), `UserPromptSubmit` (scans the
  prompt; exit 2 blocks it and shows the de-identified suggestion to the user), `PreToolUse` on `Read`
  (scans exactly the lines/pages Claude will receive; denies via `permissionDecision: "deny"`).
- **Two modes (`PHI_MODE`).** `warn` (default; a helper): flagged prompts are held back once and go
  through when the same patient data is sent again within 5 minutes (matched on the stable findings,
  not the exact text, because chat apps wrap pastes in random IDs; only a salted fingerprint is kept,
  `prompt_override.py`), or when the prompt contains `[phi-ok]` anywhere; flagged or
  uncheckable files get `permissionDecision: "ask"`; if the check fails the user is warned via
  `systemMessage` and continues. `block` (enforcement): resends and `[phi-ok]` are ignored; deny/block,
  fail closed on any error, and setup
  adds Claude Code's `onFailure: "block"` (2.1.295+) to also cover hook crashes.
- **Messages to Claude carry entity types and counts only**, never values. File names are never sent
  to the service.
- Only wait the full startup time when a start is in progress; otherwise give up after a few seconds.
- **`.phi-protect-ignore`** (`cli/ignore_file.py`): repo paths whose *file reads* are skipped, for
  deliberately fake fixtures. Honoured only when committed to git and unchanged; the nearest one above
  the file applies; patterns are relative to it, `*`/`**`, absolute paths and `..` are rejected, and
  paths are resolved first so symlinks out of an ignored folder are still checked. Prompts are always
  checked. Keep fake names out of `src/` comments; put needed fake PHI in an ignored file.
- **Cross-platform rules:** the hook reads stdin and writes stdout/stderr as UTF-8 *bytes* (a Windows
  console code page would crash on non-English text and fail open); settings files are read/written as
  UTF-8; `claude` is found with `shutil.which` (npm installs `claude.cmd` on Windows); the hook command
  uses forward-slash paths and quotes only values with spaces, so cmd, PowerShell and bash all parse it.
- **WSL bridge** (`setup --windows`, run from WSL): Windows-side settings get `wsl.exe -d <distro> -e
  <WSL python> -m phi_protect.cli.main hook`; the hook converts Windows paths (`C:\…`,
  `\\wsl.localhost\…`) with `wslpath`. Setup must run in every environment where Claude Code runs.
- Test changes in a sandbox project first: `phi-protect setup --project DIR`.

## Settings (PHI_* environment variables)

`PHI_HOST`, `PHI_PORT` (server, default 127.0.0.1:8765), `PHI_SERVICE_URL` (where the hook reaches the
service; set it to an on-prem server later), `PHI_NER_MODEL`, `PHI_NER_MODEL_REVISION` (pinned),
`PHI_SCORE_THRESHOLD` (0–1, detector findings only),
`PHI_MAX_CONCURRENT_SCANS`, `PHI_MAX_FILE_BYTES`, `PHI_MAX_FILE_TEXT_CHARS`, `PHI_MAX_PDF_PAGES`.
Run with `HF_HUB_OFFLINE=1` after the first model download.

## Commands

```bash
uv sync                                    # install deps (first run downloads the model, ~0.4 GB)
uv run python -m phi_protect.main          # serve on http://127.0.0.1:8765

# Quality gates — run all before calling a task done
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check --summarize-errors
uv run pytest

# Detection accuracy
uv run python -m evaluation.evaluate                                 # synthetic set
uv run python -m evaluation.evaluate evaluation/data/holdout.txt     # team-written held-out set
```

## Working Preferences

- **Ask before committing to git.** Prefer editing existing files over creating new ones.
- **Tests must not drive production changes.** Use fakes or restructure the test instead.
- After changes: run **typecheck, tests, and lint** before calling it done.
- Keep code simple — small focused functions, early returns over nesting, no over-engineering, no
  unnecessary comments/docstrings. Ports only where implementations genuinely vary.
- When something goes sideways, **stop and re-plan** rather than pushing through.
