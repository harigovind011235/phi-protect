# PHI Protect — Engineering Guide

## What This Is

Catches PHI (patient names, DOB, SSN, member/claim/MRN numbers, addresses, ...) in Claude Code prompts
and file reads before they reach Claude, and offers a de-identified version. Built for a US dental RCM
team whose AI tools have no HIPAA BAA. Two parts:

- **Service** (FastAPI): detects PHI in text and files, returns findings and de-identified copies.
- **`phi-protect` CLI + Claude Code hooks**: call the service on every prompt and file read. Default
  mode is a helper (flag, user decides); enforcement is one setting away (`PHI_MODE=block`).

Everything runs locally: the NER model is downloaded once and cached; content is never logged or sent.

## Architecture — Clean / Hexagonal (Ports & Adapters)

Dependencies point inward only. The domain knows nothing about Presidio, PyTorch, PDFium or FastAPI.

```
handler, cli ─▶ usecases ◀─ adapters
                    ▲
                 domain  (innermost; pure Python)
```

- **`domain/`** — standard library only.
  - `models/`: `Finding` (span, type, score, source: rule or detector), `EntityType`, `Decision`.
  - `rules/`: regex rules for structured PHI (labeled IDs, SSN, dates and names, addresses, phone,
    MBI, X12 segments). They run alongside any detector, so swapping detectors keeps them.
  - `policy/`: allowlist, overlap merging, blocking, placeholders.
- **`usecases/`** — orchestration; owns both sets of contracts.
  - `interfaces/` (driving ports, called by handlers): `ScanServiceInterface`, `FileServiceInterface`.
  - `ports/` (driven ports, implemented by adapters): `detectors/PhiDetector`, `documents/DocumentFormat`.
  - `dtos/`, `errors.py` (`UnverifiableFileError`), `phi_search.py` (detector + rules + policy, shared).
- **`adapters/`** — `PresidioPhiDetector` (Presidio + spaCy + Hugging Face model), `PdfiumPdfFormat`,
  `PlainTextFormat`.
- **`handler/`** — FastAPI app and routes; reads the container off `app.state` and delegates.
- **`cli/`** — second entry point. The hook is an HTTP *client* of the running service and never loads
  the model, so each check starts fast. Only `setup` and `serve` load it.

**Composition root.** `composition.py` is the only place adapters are created and wired. `Container` is
a frozen dataclass built once by `create_container(settings)`. No module-level singletons or `lru_cache`.

**Swap test.** To replace the detector (GLiNER, ONNX, a remote GPU service), write an adapter against
`PhiDetector` and change one line in `composition.py`; domain policy does not move.

**Adding an adapter:** (1) define or reuse a port under `usecases/ports/`, (2) implement it in
`adapters/`, (3) wire it in `create_container()`. Tests use fakes from `tests/fakes.py`; never patch
globals.

## Async Rule

Ports and use cases are `async`; domain code is plain sync Python. The work is CPU-bound, so async does
not make it faster; it keeps the server responsive and lets a remote detector drop in.
**CPU-heavy work lives in an adapter and runs via `asyncio.to_thread`**; running it directly in an
`async def` freezes the server. `PresidioPhiDetector` caps concurrent model runs
(`PHI_MAX_CONCURRENT_SCANS`). PDFium is not thread-safe, so all PDFium calls go through the adapter's lock.

## Project Structure

```
phi_protect/
├── src/phi_protect/
│   ├── main.py                Service entry point (`python -m phi_protect.main`, 127.0.0.1:8765)
│   ├── composition.py         Container + create_container()
│   ├── config/settings.py     PHI_* settings; always use create_settings()
│   ├── domain/                models/, rules/, policy/
│   ├── usecases/              interfaces/, ports/, dtos/, errors.py, scan_service.py, file_service.py,
│   │                          phi_search.py
│   ├── adapters/              detectors/, documents/
│   ├── handler/               app.py, dependencies.py, errors.py, routes/
│   └── cli/                   main.py (`phi-protect`), hook.py, service_client.py, service_process.py,
│                              claude_settings.py, ignore_file.py, prompt_override.py, clipboard.py,
│                              wsl.py, self_test_sample.py
├── tests/                     Mirrors src/ (domain, usecases, adapters, handler, cli) + end to end
├── evaluation/                Synthetic test set, held-out template, scoring script
└── examples/                  Fake files for trying PHI Protect by hand
```

## Key Invariants

- **Never log, echo or persist content.** Validation errors return field names only; error messages
  never contain file content; downloads are named `deidentified.*`; file names are never sent to the
  service (they can be PHI).
- **Never use real PHI anywhere** — tests, evaluation, examples, comments. Synthetic data only.
- **The service never guesses.** Anything it cannot fully check (scans, images, forms, annotations,
  encrypted PDFs, unsupported binaries, size limits) is `cannot_verify`, never `allow`.
- **Policy order.** The allowlist runs per candidate *before* merging, so it can veto one detector's
  guess but never erase another finding. Only detector findings of type `PERSON`, `ID`, `PHONE_NUMBER`
  or `DATE_TIME` can be allowlisted; rule findings never are.
- **Merging is order-independent.** The merged span covers all members; the label comes from the best
  member: blocking > specific (not generic `ID`) > rule over detector > own score. Rule and detector
  scores are on different scales; never compare them directly.
- **Dates:** unlabeled `DATE_TIME` is replaced but does not block; labeled `PATIENT_DATE` blocks.
- **Keep `HCW` mapped to `PERSON`** in the detector: the Stanford model labels most patients as HCW.
- **DTOs cross layer boundaries; domain models do not.**
- **Measure every detection change** with `evaluation/evaluate.py`; never tune against the held-out set.

## Claude Code Hook

Events: `SessionStart` starts the service if it is not running. `UserPromptSubmit` scans the prompt.
`PreToolUse` on `Read` scans exactly the lines or pages Claude will receive. On a flagged prompt the
de-identified version goes to the clipboard (Windows `clip.exe`, macOS `pbcopy`, Linux
`wl-copy`/`xclip`). Messages carry entity types and counts only, never values.

| | `warn` (default, helper) | `block` (enforcement) |
|---|---|---|
| Flagged prompt | Held back (exit 2); goes through if the same patient data is resent within 5 min, or if it contains `[phi-ok]` | Blocked; resends and `[phi-ok]` ignored |
| Flagged or uncheckable file | `permissionDecision: "ask"` | `permissionDecision: "deny"` |
| Check fails (service down, error) | Continue; warn via `systemMessage` | Block |
| Hook crash | Continue | Setup adds `onFailure: "block"` (Claude Code 2.1.295+) |

- **Resend matching** uses the stable findings, not the exact text: chat apps wrap pastes in random IDs,
  and the model's generic `ID`/`DATE_TIME` guesses change with them. Only a salted fingerprint is kept
  (`prompt_override.py`), single use. Local state lives in `~/.phi-protect/` (service log, PID,
  fingerprint), never content.
- **Startup wait:** wait the full startup time only when a start is in progress; otherwise give up after
  a few seconds.
- **`.phi-protect-ignore`** (`ignore_file.py`): repo paths whose file reads are skipped, for fake
  fixtures. Honoured only when committed and unchanged; the nearest one above the file applies;
  `*`/`**`, absolute paths and `..` are rejected; paths are resolved so symlinks out of an ignored folder
  are still checked. This repo ignores `tests/` and `evaluation/` but *not* `examples/`, which exist to
  demonstrate detection. Keep fake names out of `src/`; put needed fake PHI in an ignored file
  (`self_test_sample.py`).
- **Cross-platform:** hook stdin/stdout/stderr are UTF-8 *bytes* (a Windows code page would crash on
  non-English text); settings files are UTF-8; `claude` is found with `shutil.which` (`claude.cmd` on
  Windows); hook commands use forward slashes and quote only values with spaces, so cmd, PowerShell and
  bash all parse them.
- **WSL bridge** (`setup --windows`, run from WSL): Windows-side settings get `wsl.exe -d <distro> -e
  <WSL python> -m phi_protect.cli.main hook`, and the hook converts Windows paths with `wslpath`. Setup
  must run in every environment where Claude Code runs.
- Try hook changes in a sandbox first: `phi-protect setup --project DIR`, then reinstall the tool
  (`uv tool install --reinstall .`).

## Settings (PHI_* environment variables)

| Variable | Default | |
|---|---|---|
| `PHI_MODE` | `warn` | `warn` or `block` (see the hook table) |
| `PHI_HOST`, `PHI_PORT` | `127.0.0.1`, `8765` | Where the service listens |
| `PHI_SERVICE_URL` | local | Where the hook reaches the service (e.g. on-prem later) |
| `PHI_NER_MODEL`, `PHI_NER_MODEL_REVISION` | Stanford de-identifier, pinned | Detector model |
| `PHI_SCORE_THRESHOLD` | `0.5` | Detector findings only; rules always apply |
| `PHI_MAX_CONCURRENT_SCANS` | `1` | Concurrent model runs |
| `PHI_MAX_FILE_BYTES`, `PHI_MAX_FILE_TEXT_CHARS`, `PHI_MAX_PDF_PAGES` | 25 MB, 50,000, 50 | File limits |

The background service sets `HF_HUB_OFFLINE=1` itself; set it manually when running the service by hand
after the model is cached.

## Commands

```bash
uv sync                                    # install dependencies
uv run python -m phi_protect.main          # run the service (first start downloads the model, ~0.4 GB)

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
