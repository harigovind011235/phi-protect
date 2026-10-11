from pathlib import Path

from evaluation.evaluate import load_marked_prompts, parse_marked_prompt


def test_marked_prompt_becomes_text_and_spans():
    sample = parse_marked_prompt("appeal for {{phi:Maria Lopez}}, dob {{phi:03/14/1985}}")
    assert sample["text"] == "appeal for Maria Lopez, dob 03/14/1985"
    assert [sample["text"][e["start"] : e["end"]] for e in sample["entities"]] == [
        "Maria Lopez",
        "03/14/1985",
    ]
    assert sample["has_phi"]


def test_unmarked_prompt_is_clean():
    assert not parse_marked_prompt("What does CARC 45 mean?")["has_phi"]


def test_instructions_are_skipped_and_multiline_prompts_kept(tmp_path: Path):
    path = tmp_path / "holdout.txt"
    path.write_text("instructions {{phi:ignored}}\n---\nline one\nline two\n---\n\n---\nsecond\n")
    assert [s["text"] for s in load_marked_prompts(path)] == ["line one\nline two", "second"]
