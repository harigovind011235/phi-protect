**PHI Protect — project review and walkthrough**

Reviewed on 11 October 2026 against the supplied source tree and the clarified requirement: an internal tool that strictly prevents employees from putting PHI into coding agents. Application code was not changed. All runtime examples used synthetic data.

**Verdict: changes required before relying on this for enforcement.**

The repository is a working local text detector and redactor. Its README explicitly calls it “step 1.” It does not implement interception of coding-agent traffic, mandatory routing, or blocking. Even when called correctly, confirmed false negatives and allowlist errors can return sensitive text with `has_phi=false`.

The implementation is small and reasonably separated. The principal weaknesses are its policy assumptions, incomplete detection, and the absence of an enforcement boundary—not excessive architectural complexity. A successful HTTP response or passing test suite does not establish that text is safe to send.

**Review scope and evidence**

- Read all application modules, tests, evaluation code, README, project configuration, and lockfile metadata.
- Applied security/PHI, backend correctness, maintainability, and test-scenario review lenses.
- No repository-specific AGENTS.md or CLAUDE.md was available. No sibling backend service exists to compare architectural conventions against. This is a whole-project review, not a PR comparison; Git history was unavailable in this workspace.
- `ruff check .`: passed.
- `pytest -q`: all 10 tests passed, with a Starlette warning about the deprecated httpx TestClient integration.
- The sandbox stalled even an empty FastAPI TestClient. Running the existing tests outside that sandbox completed in 4.28 seconds. This is not reported as an application defect.
- Ran the existing 272-record synthetic evaluation with cached models, Hugging Face offline settings, two CPU computation threads, and a writable temporary copy of the domain-suffix cache.
- Added temporary review probes outside the repository to inspect strict span coverage, allowlist behavior, merge decisions, and HTTP validation errors. These were checks, not application changes.
- No real PHI or hardcoded credentials were identified in reviewed source. The application has no explicit request-body logging or third-party inference calls. This observation does not certify deployment logging or all dependency behavior.

**What the measurements actually say**

| Measure | Observed result | Meaning |
|---|---:|---|
| PHI-containing synthetic prompts flagged | 144/144 | Every positive prompt contained at least one blocking finding. Nothing was actually blocked by an integration. |
| Clean synthetic prompts incorrectly flagged | 8/128 | All eight were repetitions of a prompt mentioning the Luhn algorithm, where “Luhn” was treated as a person. |
| Annotated spans reaching the evaluator's coverage threshold | 569/576 | Approximately 98.8%; the evaluator accepts 80% character coverage. |
| Annotated spans completely covered | 569/576 | Coincidentally the same count on this dataset; the weak threshold did not inflate this particular recall result. |
| Positive prompts with every annotated span completely covered | 137/144 | Seven had residual annotated characters. |
| Positive prompts with an actual name remaining | 4/144 | “Le”, “Robert”, “Michael”, and “Ian” remained. Three other incomplete spans left only “PhD” or “DDS”. |
| Findings overlapping an annotated span | 548/617 | The evaluator's approximate precision is 88.8%; this is not exact entity classification or exact boundary precision. |
| Mean time reported by evaluation | About 61 ms | Short synthetic inputs, this machine and configuration; includes initialization amortized over the run. Not a long-document or concurrent-load benchmark. |

The dataset has 18 positive templates and 16 clean templates, each sampled eight times. Repeated templates and some identical clean examples limit its independence and breadth. These numbers do not predict performance on arbitrary employee files, logs, prompts, languages, or attachments.

**Issues, ordered by practical importance**

**1. Critical product gap: scanning is optional; prevention is absent.**

Evidence: `phi_detector/app.py:24–31` exposes only `/health` and `/scan`; `README.md:5` identifies this as the first step.

There is no client integration, request interception, traffic gateway, managed endpoint policy, or delivery path in this repository. An employee can send content directly to a coding agent without involving this service. The `has_phi` field is only a returned boolean. Evaluation output saying “blocked” actually means “flagged.”

For the intended product, define and implement the boundary every supported outbound agent payload must cross. Include user prompts, files selected or read by the agent, terminal/tool output, attachments, and other supported context sources. Define what happens on detector timeout, error, oversize input, unsupported content, and direct-route bypass. “Fail closed” means these conditions prevent transmission rather than falling back to sending the original.

Verification: demonstrate that each supported payload path cannot send content without a policy decision, and that unavailable scanning or bypass attempts cannot transmit it. This is a separate delivery milestone, not a small addition to `/scan`.

**2. High: allowlist rules erase legitimate patient findings.**

Evidence: `phi_detector/allowlist.py:83–115`; filtering happens in `phi_detector/engine.py:81–85` before redaction and decision-making.

Confirmed examples:

| Synthetic input | Observed result | Cause |
|---|---|---|
| `MRN: D0120` | False; unchanged | A patient record ID matching the shape of a dental procedure code is globally exempted. Both model and rule findings were discarded. |
| `Claim number: D0120` | False; unchanged | The same exemption overrides a labeled claim identifier. |
| `Patient Dr. Smith has tooth pain.` | False; unchanged | A doctor title is treated as proof that the person cannot be the patient. |
| `NPI 1234567890; ID ZX987654321` | False; unchanged | The provider-label lookback crosses into a separate identifier and exempts it too. |

A value's shape or nearby word is not enough to prove that it is harmless. Narrow exemptions to their actual field and context; preserve explicit patient/claim/MRN findings, and treat ambiguous roles conservatively. Review each exemption against its intended policy rather than adding more global exceptions.

Verification: pair every legitimate exemption with a collision case where the same value occurs as a patient identifier. Add adjacent provider/patient fields and patients who hold professional titles.

**3. High: ordinary address formats pass unchanged.**

Evidence: `phi_detector/recognizers.py:20–43,99–126` uses capitalized address patterns and case-sensitive regex settings. The NER mapping in `phi_detector/engine.py:14–20` supplies no general address fallback.

`Send to 123 main street, springfield, il 62704.` returns false and remains unchanged. The title-case equivalent is detected and redacted. `Address: PO Box 1234` also passes unchanged.

Make casing support deliberate and add missing supported address formats such as PO boxes. Retest false positives on source code and ordinary prose; simply making every broad pattern case-insensitive can introduce new false alarms.

Verification: case variants, punctuation, multiline address fields, unit numbers, PO boxes, and pasted structured formats should meet the declared address policy.

**4. High: model misses can leave names in returned text.**

Evidence: `phi_detector/recognizers.py:85–95`, `phi_detector/engine.py:78–90`, and the evaluation run described above.

Four positive evaluation prompts retained actual names even though other entities made their `has_phi` value true. Separately, `Patient Le needs treatment.` returned false with no findings. This is a confirmed detection limitation, not merely an untested possibility.

The pretrained model's published description concerns radiology and biomedical documents. Its performance cannot be assumed to transfer unchanged to coding contexts such as source code, logs, X12 records, CSVs, and fragments. See the [Stanford model card](https://huggingface.co/StanfordAIMI/stanford-deidentifier-base).

Add representative holdout examples and structure-aware extraction for formats the product explicitly supports. Treat redaction as an assistance feature until residual-risk criteria are defined and validated. Do not automatically forward returned text merely because it is called `deidentified_text`. Improving this model alone cannot prove the absence of every identifying detail in arbitrary content.

Verification: assess names in isolation as well as alongside other identifiers; measure residual sensitive values per complete outbound payload, not just whether any entity was found.

**5. High policy mismatch: dates are explicitly non-blocking.**

Evidence: `phi_detector/engine.py:40–41,87–90`; this behavior is documented in `README.md:31` and encoded in the tests.

`DOB: 03/14/1985` returns `has_phi=false` while replacing the DOB in the returned text. A future consumer that sends the original whenever this flag is false would send that DOB. This follows the current README but conflicts with interpreting `has_phi=false` as “no sensitive patient data.”

Separate detection from policy: for example, distinguish sensitive findings from the action to take. Establish whether strict policy rejects patient-linked dates or permits only a reviewed transformed payload. A release date and a patient DOB should not be conflated simply because the model labels both DATE_TIME.

Verification: test patient DOB, service date, release date, and the actual bytes delivered by the future integration for every decision outcome.

**6. Medium: overlap resolution can downgrade a blocking finding.**

Evidence: `phi_detector/engine.py:94–115` selects the surviving label primarily by generic-ID status and score. The final blocking decision uses only surviving labels.

A deterministic function probe with overlapping MEMBER_ID (score 0.85) and DATE_TIME (score 0.99) keeps DATE_TIME alone. The resulting finding would be non-blocking. This is confirmed at the merge-function level; the tested real date-shaped member IDs did not trigger it end to end.

Preserve blocking evidence independently of the display label selected for a merged span, or apply an explicit conservative policy to mixed overlaps. Detector scores from different systems should not implicitly override the blocking policy.

Verification: overlapping blocking/non-blocking labels must preserve the required block regardless of input order or relative confidence. Also check chained overlaps and specific-vs-generic labels.

**7. Medium: evaluation metrics do not establish safe redaction.**

Evidence: `evaluation/evaluate.py:9,13–21,51–63,71–75`.

An entity with 80% of its characters removed is counted as found. Any overlapping prediction is counted as a true positive, regardless of entity type or excess redaction. A whole-document prediction covering one short entity can therefore count as a correct finding despite destroying useful content. Synthetic-only data and repeated templates further restrict the interpretation.

For strict prevention, add complete sensitive-span removal, residual sensitive characters, payload escape rate, and amount of harmless text removed. Keep detection sensitivity, blocking policy, and redaction quality separate. Entity-type confusion is a different measure from locating text that needs removal.

Verification: deliberately partial redaction and excessive whole-document redaction should fail their respective quality gates. Reserve a separate dataset for acceptance testing; do not tune only against the same templates.

**8. Medium: invalid requests echo their raw input in error responses.**

Evidence: `phi_detector/app.py:20–21` uses normal FastAPI validation with no custom sanitized validation handler.

ASGI request probes confirmed that a list supplied instead of text, and text beyond the 200,000-character limit, both return 422 errors containing the original synthetic marker. The oversize response contained approximately 200 KB of input. This returns data to the calling client; it is not evidence of third-party exfiltration. It creates a sensitive response surface that a future client, proxy, or diagnostic logger could persist.

Use a validation error response that omits input values while retaining error codes and field names. Preserve that policy across integration error handling.

Verification: send marked synthetic sensitive content through invalid, oversize, malformed, and downstream-error paths; assert it is absent from error bodies and captured logs.

**How the project works, in plain language**

The service accepts a piece of text and searches for substrings that look sensitive. It uses two complementary methods. Rules look for recognizable shapes or labels, such as an email address or a value following “Member ID.” A pretrained named-entity-recognition model reads the surrounding language and predicts names, dates, phone numbers, and generic IDs. Named-entity recognition means locating and classifying pieces of text; it is not a conversational coding agent.

Presidio coordinates these detectors. A spaCy English model supplies language preprocessing and context. The application removes Presidio's normal spaCy entity recognizer and substitutes its Stanford model recognizer for the relevant learned detections. The model runs on the CPU through Transformers and PyTorch. The application does not train it.

At startup, `get_analyzer()` loads the preprocessing pipeline, default Presidio recognizers, custom regex recognizers, and Stanford model. Its cache reuses that analyzer within a process. Each separate server process would load its own instance. Initial model retrieval requires access to model artifacts; subsequent inference can run with cached assets. This review used offline model settings. A dependency can also access/cache public domain-suffix lists for email recognition; local inference should not be confused with an enforced no-network policy.

For each request:

1. FastAPI validates that `text` is a string no longer than 200,000 characters.
2. Empty/whitespace input returns unchanged without detection.
3. Presidio gathers findings for the requested entity types and applies the configured score threshold, default 0.5.
4. The allowlist discards findings the application considers harmless.
5. Overlapping findings are combined; neighboring same-type findings separated only by spaces are also joined.
6. Remaining spans are replaced with numbered placeholders.
7. `has_phi` becomes true if any merged finding is not DATE_TIME.

A finding contains a type, start offset, end offset, and score. Offsets refer to the original text; the end is exclusive. They are Python string positions, which a future JavaScript client must interpret carefully for characters represented differently in UTF-16. Scores come from multiple detectors and are not one calibrated probability that a request contains PHI.

The placeholder system reuses the same label for repeated, case-insensitive matches of the same entity type within one request. Different requests reset the numbering. There is no persistent identity map or response-restoration mechanism. The project uses its own text replacement code, not a Presidio anonymizer pipeline.

The original input is processed in memory and the route returns the transformed text. There is no database, employee account system, web UI, audit store, queue, or coding-agent connector in the reviewed source.

**Where to read the code**

| File | Responsibility | Why it matters |
|---|---|---|
| `phi_detector/app.py` | Startup and HTTP interface | Shows the actual product boundary and input contract. |
| `phi_detector/engine.py` | Detection orchestration, decision, merging, replacement | Contains the main behavior and the meaning of `has_phi`. |
| `phi_detector/recognizers.py` | Custom model and pattern detectors | Defines what shapes and language patterns are recognized. |
| `phi_detector/allowlist.py` | Suppression of findings | Trades fewer false alarms for a risk of missed sensitive values. |
| `tests/test_engine.py` | Ten selected behavior tests | Checks basic functionality, not comprehensive prevention. |
| `evaluation/generate.py` | Synthetic text and ground-truth generation | Defines what the accuracy exercise covers. |
| `evaluation/evaluate.py` | Dataset scoring | Defines what the displayed accuracy numbers mean. |
| `pyproject.toml` and `uv.lock` | Runtime/dev dependencies | Reproduce Python dependencies; model weights are loaded separately. |

The HTTP handler delegates to the engine through typed request/result structures. This is appropriate for this project's size. There is no need to introduce repositories, service hierarchies, or additional infrastructure layers just to satisfy an architectural pattern.

**Useful design choices to preserve**

Local CPU inference, a readable separation of responsibilities, typed result dataclasses, a thin HTTP handler, synthetic evaluation data, startup model initialization, an input-size limit, reusable placeholders, and existing tests are good foundations. No code changes are needed merely because a coding agent wrote the project; changes should address demonstrable requirements and failure modes.

**Additional engineering work before a controlled rollout**

- Validate the score threshold as a finite number in its intended range; treat invalid configuration as startup failure. Raising it reduces detections, which matters for a prevention policy.
- Pin the model revision and validate the expected labels. `PHI_NER_MODEL` permits replacement, but the mapping remains tied to the current model's labels. Python dependency locking does not pin model weights.
- Define supported languages, formats, identifier categories, and maximum payloads. The implementation is English/US-oriented. IP addresses and URLs are not requested entity types; arbitrary contextual identification is not comprehensively covered.
- Establish CPU concurrency, memory, latency, and timeout budgets for long input and simultaneous requests. The 61 ms short-sample mean does not validate the 200,000-character endpoint limit under load.
- Document deployment exposure. The documented uvicorn command uses its normal loopback default, and there is no authentication in the app. If it becomes a shared network service, define access control and transport protection as part of that deployment.
- Retain metadata-only operational evidence where needed. The evaluator prints synthetic excerpts; do not substitute real patient data into that workflow.

**Test scenarios that matter next**

| Scenario | Protects against | Current coverage | Priority |
|---|---|---|---|
| Direct route to coding agent bypasses scanner | Unenforced policy | No integration | Highest |
| Scanner down, timeout, malformed response, unsupported content | Sending unchecked content | No integration | Highest |
| Files and tool outputs join a prompt after initial scanning | Unchecked context reaching a model | No integration | Highest |
| MRN/claim values resembling exempt procedure codes | Allowlist-caused misses | Missing | High |
| Patient has doctor title; patient ID follows provider field | Role/context confusion | Missing | High |
| Lowercase and PO-box addresses | Format-dependent misses | Missing | High |
| Short names in isolation, X12 fields, email fragments | Model misses masked by other findings | Dataset contains some failures; no regression gate | High |
| DOB/service date versus release date, including transmitted payload | Misuse of non-blocking flag | Only release-date decision covered | High |
| Blocking/non-blocking overlap with reversed scores | Policy weakened by merging | Only specific/generic overlap covered | Medium |
| Invalid/oversize requests and error logging | Sensitive input reflection/persistence | Missing | Medium |
| Long documents, Unicode, model-window boundaries, concurrent requests | Truncation, offsets, resource failures | Missing | Medium |
| Partial redaction and excessive redaction | Misleading quality metrics | Missing | Medium |

**Practical next steps**

First define the exact agent products and outbound content paths to control, and the required action for sensitive or unscannable content. Then implement and verify a mandatory enforcement boundary with failure behavior. In parallel, correct the confirmed allowlist/address/policy defects and capture them as regression cases. Establish a representative held-out acceptance suite measuring escaped sensitive content and false blocks. Only then consider a controlled rollout with operational monitoring that avoids retaining payloads.

Running the current scanner for local experimentation follows the README: `uv sync`, then `uv run uvicorn phi_detector.app:app --port 8765`. Tests run with `uv run pytest`; lint with `uv run ruff check .`; the existing dataset is evaluated with `uv run python -m evaluation.evaluate`. Use synthetic data for those exercises. Starting this service alone does not protect a coding-agent session.
