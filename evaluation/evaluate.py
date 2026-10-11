"""Scores the detector on a labeled prompt set.

Usage:
    uv run python -m evaluation.evaluate                                # synthetic set
    uv run python -m evaluation.evaluate evaluation/data/holdout.txt    # team-written held-out set
"""

import asyncio
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from phi_protect.composition import create_container
from phi_protect.config.settings import create_settings
from phi_protect.usecases.dtos import ScanResult
from phi_protect.usecases.interfaces import ScanServiceInterface

SYNTHETIC_DATA = Path(__file__).parent / "data" / "synthetic.jsonl"
MAX_EXAMPLES = 15
PROMPT_SEPARATOR = "---"
PHI_MARKER = re.compile(r"\{\{phi:(.+?)\}\}")


def parse_marked_prompt(marked: str) -> dict:
    text, entities, cursor = "", [], 0
    for match in PHI_MARKER.finditer(marked):
        text += marked[cursor : match.start()]
        value = match.group(1)
        entities.append({"type": "PHI", "start": len(text), "end": len(text) + len(value)})
        text += value
        cursor = match.end()
    text += marked[cursor:]
    return {"text": text, "entities": entities, "has_phi": bool(entities)}


def load_marked_prompts(path: Path) -> list[dict]:
    """Prompts separated by '---' lines, PHI marked as {{phi:value}}.

    Text before the first '---' (the instructions) is ignored.
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in path.read_text().splitlines():
        if line.strip() == PROMPT_SEPARATOR:
            blocks.append("\n".join(current).strip("\n"))
            current = []
        else:
            current.append(line)
    blocks.append("\n".join(current).strip("\n"))
    return [parse_marked_prompt(block) for block in blocks[1:] if block.strip()]


def load_samples(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines()]
    return load_marked_prompts(path)


def positions(spans) -> set[int]:
    return {i for span in spans for i in range(span[0], span[1])}


def percent(hit: int, total: int) -> str:
    return f"{hit}/{total} ({100 * hit / total:.1f}%)" if total else "-"


def print_table(title: str, hits: Counter, totals: Counter):
    print(f"\n{title}")
    for key in sorted(totals):
        print(f"  {key:<16} {percent(hits[key], totals[key])}")
    print(f"  {'OVERALL':<16} {percent(sum(hits.values()), sum(totals.values()))}")


async def scan_all(service: ScanServiceInterface, texts: list[str]) -> list[ScanResult]:
    return [await service.scan_text(text) for text in texts]


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else SYNTHETIC_DATA
    samples = load_samples(path)
    gold_totals, gold_hits = Counter(), Counter()
    flag_totals, flag_hits = Counter(), Counter()
    decisions = Counter()
    phi_left_prompts = harmless_chars = harmless_redacted = 0
    misses, false_alarms, wrong_flags = [], [], []

    service = create_container(create_settings()).scan_service
    started = time.perf_counter()
    results = asyncio.run(scan_all(service, [sample["text"] for sample in samples]))
    for sample, result in zip(samples, results, strict=True):
        text, golds = sample["text"], sample["entities"]
        decisions[(sample["has_phi"], result.has_phi)] += 1
        if result.has_phi and not sample["has_phi"]:
            reasons = [f"{f.entity_type}={text[f.start : f.end]!r}" for f in result.entities]
            wrong_flags.append(f"{text[:70]!r} <- {', '.join(reasons)}")

        redacted = positions((f.start, f.end) for f in result.entities)
        gold_positions = positions((g["start"], g["end"]) for g in golds)
        harmless_chars += len(text) - len(gold_positions)
        harmless_redacted += len(redacted - gold_positions)

        phi_left = False
        for gold in golds:
            gold_totals[gold["type"]] += 1
            if all(i in redacted for i in range(gold["start"], gold["end"])):
                gold_hits[gold["type"]] += 1
            else:
                phi_left = True
                misses.append(f"{gold['type']:<15} {text[gold['start'] : gold['end']]!r}")
        phi_left_prompts += phi_left

        for finding in result.entities:
            flag_totals[finding.entity_type] += 1
            if any(i in gold_positions for i in range(finding.start, finding.end)):
                flag_hits[finding.entity_type] += 1
            else:
                false_alarms.append(
                    f"{finding.entity_type:<15} {text[finding.start : finding.end]!r}"
                )
    elapsed_ms = 1000 * (time.perf_counter() - started) / len(samples)

    print(f"Dataset: {path} ({len(samples)} prompts)")
    print_table("PHI values fully removed, by type (higher = fewer leaks)", gold_hits, gold_totals)
    print_table(
        "Flags that touched real PHI, by type (higher = fewer false alarms)", flag_hits, flag_totals
    )

    phi_prompts = decisions[(True, True)] + decisions[(True, False)]
    clean_prompts = decisions[(False, True)] + decisions[(False, False)]
    flagged = percent(decisions[(True, True)], phi_prompts)
    wrongly_flagged = percent(decisions[(False, True)], clean_prompts)
    print("\nPrompt level (what a connector would act on)")
    print(f"  PHI prompts flagged                       {flagged}")
    print(f"  PHI prompts with PHI left after redaction {percent(phi_left_prompts, phi_prompts)}")
    print(f"  Clean prompts wrongly flagged             {wrongly_flagged}")
    print(
        f"  Harmless characters redacted              {percent(harmless_redacted, harmless_chars)}"
    )
    print(f"  Average scan time                         {elapsed_ms:.0f} ms")

    print(f"\nPHI not fully removed ({len(misses)} total)")
    for line in misses[:MAX_EXAMPLES]:
        print(f"  {line}")
    print(f"\nClean prompts wrongly flagged ({len(wrong_flags)} total)")
    for line in wrong_flags[:MAX_EXAMPLES]:
        print(f"  {line}")
    print(f"\nSample false alarms ({len(false_alarms)} total)")
    for line in false_alarms[:MAX_EXAMPLES]:
        print(f"  {line}")


if __name__ == "__main__":
    main()
