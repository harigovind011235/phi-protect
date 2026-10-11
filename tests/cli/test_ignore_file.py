import subprocess
from pathlib import Path

import pytest

from phi_protect.cli.hook import handle_event
from phi_protect.cli.ignore_file import is_ignored, read_patterns
from tests.cli.test_hook import FakeClient, make_context, read_event


def git(repo: Path, *args: str) -> None:
    identity = ["-c", "user.email=test@example.com", "-c", "user.name=Test"]
    subprocess.run(["git", *identity, *args], cwd=repo, check=True, capture_output=True)


def make_repo(root: Path, patterns: str, commit: bool = True) -> Path:
    git(root, "init")
    (root / "tests" / "fixtures").mkdir(parents=True)
    (root / "tests" / "fixtures" / "patients.csv").write_text("name\nMaria Lopez\n")
    (root / "examples").mkdir()
    (root / "examples" / "eob.pdf").write_bytes(b"%PDF-1.4")
    (root / "data.csv").write_text("name\nKevin Ng\n")
    (root / ".phi-protect-ignore").write_text(patterns)
    if commit:
        git(root, "add", ".")
        git(root, "commit", "-m", "init")
    return root


def test_committed_patterns_are_honored(tmp_path):
    repo = make_repo(tmp_path, "# fake patients only\ntests/fixtures/\nexamples/*.pdf\n")
    assert is_ignored(repo / "tests" / "fixtures" / "patients.csv")
    assert is_ignored(repo / "examples" / "eob.pdf")
    assert not is_ignored(repo / "data.csv")


def test_uncommitted_ignore_file_is_not_honored(tmp_path):
    repo = make_repo(tmp_path, "tests/fixtures/\n", commit=False)
    assert not is_ignored(repo / "tests" / "fixtures" / "patients.csv")


def test_locally_edited_ignore_file_is_not_honored(tmp_path):
    repo = make_repo(tmp_path, "tests/fixtures/\n")
    with (repo / ".phi-protect-ignore").open("a") as ignore_file:
        ignore_file.write("data.csv\n")
    assert not is_ignored(repo / "data.csv")
    assert not is_ignored(repo / "tests" / "fixtures" / "patients.csv")


@pytest.mark.parametrize("pattern", ["*", "**", "../outside.csv", "/data.csv"])
def test_too_broad_or_escaping_patterns_are_rejected(tmp_path, pattern):
    (tmp_path / ".phi-protect-ignore").write_text(f"{pattern}\n")
    assert read_patterns(tmp_path / ".phi-protect-ignore") == []


def test_symlink_to_data_outside_the_ignored_folder_is_still_checked(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "real.csv").write_text("name\nKevin Ng\n")
    (tmp_path / "repo").mkdir()
    repo = make_repo(tmp_path / "repo", "tests/fixtures/\n")
    (repo / "tests" / "fixtures" / "link.csv").symlink_to(outside / "real.csv")
    assert not is_ignored(repo / "tests" / "fixtures" / "link.csv")


def test_without_git_nothing_is_ignored(tmp_path):
    (tmp_path / ".phi-protect-ignore").write_text("notes.txt\n")
    (tmp_path / "notes.txt").write_text("Maria Lopez")
    assert not is_ignored(tmp_path / "notes.txt")


def test_hook_skips_ignored_files_without_scanning(tmp_path):
    repo = make_repo(tmp_path, "tests/fixtures/\n")
    file_scan = {"decision": "block", "entity_counts": {"PERSON": 1}, "reason": None}
    client = FakeClient(file_scan=file_scan)
    ignored = handle_event(
        read_event(repo / "tests" / "fixtures" / "patients.csv"), make_context(client)
    )
    checked = handle_event(read_event(repo / "data.csv"), make_context(client))
    assert ignored.stdout == ""
    assert "deny" in checked.stdout
    assert len(client.scanned_files) == 1
