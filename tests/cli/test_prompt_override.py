from phi_protect.cli import prompt_override
from phi_protect.cli.prompt_override import PromptOverrides

VALUES = ["Maria Lopez", "XGH884213901"]


def test_the_same_patient_data_sent_again_is_confirmed_once(tmp_path):
    overrides = PromptOverrides(tmp_path / "override.json")
    overrides.remember(VALUES)
    assert not overrides.consume(["Kevin Ng"])
    assert overrides.consume(VALUES)
    assert not overrides.consume(VALUES)


def test_order_case_spacing_and_repeats_do_not_matter(tmp_path):
    overrides = PromptOverrides(tmp_path / "override.json")
    overrides.remember(VALUES)
    assert overrides.consume(["xgh884213901", "maria  lopez", "Maria Lopez"])


def test_confirmation_expires(tmp_path, monkeypatch):
    overrides = PromptOverrides(tmp_path / "override.json")
    overrides.remember(VALUES)
    later = prompt_override.time.time() + prompt_override.OVERRIDE_WINDOW_SECONDS + 1
    monkeypatch.setattr(prompt_override.time, "time", lambda: later)
    assert not overrides.consume(VALUES)


def test_only_a_fingerprint_is_stored(tmp_path):
    path = tmp_path / "override.json"
    PromptOverrides(path).remember(VALUES)
    stored = path.read_text()
    assert "Maria" not in stored and "XGH884213901" not in stored


def test_nothing_remembered_means_nothing_confirmed(tmp_path):
    assert not PromptOverrides(tmp_path / "missing.json").consume(VALUES)
