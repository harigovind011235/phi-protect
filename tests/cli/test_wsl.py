from pathlib import Path

from phi_protect.cli import wsl


def fake_commands(monkeypatch, outputs: dict[str, str]):
    monkeypatch.setattr(wsl, "is_wsl", lambda: True)
    monkeypatch.setattr(wsl, "_run", lambda command: outputs.get(command[0], ""))


def test_windows_paths_become_wsl_paths(monkeypatch):
    fake_commands(monkeypatch, {"wslpath": "/mnt/c/Users/hari/eob.pdf\n"})
    assert wsl.to_local_path("C:\\Users\\hari\\eob.pdf") == Path("/mnt/c/Users/hari/eob.pdf")


def test_linux_paths_and_non_wsl_systems_are_unchanged(monkeypatch):
    fake_commands(monkeypatch, {"wslpath": "/should/not/be/used"})
    assert wsl.to_local_path("/home/hari/eob.pdf") == Path("/home/hari/eob.pdf")
    monkeypatch.setattr(wsl, "is_wsl", lambda: False)
    assert wsl.to_local_path("C:\\eob.pdf") == Path("C:\\eob.pdf")


def test_windows_home_is_found_through_cmd(monkeypatch):
    fake_commands(monkeypatch, {"cmd.exe": "C:\\Users\\hari\r\n", "wslpath": "/mnt/c/Users/hari\n"})
    assert wsl.windows_home() == Path("/mnt/c/Users/hari")


def test_windows_home_is_none_when_cmd_fails(monkeypatch):
    fake_commands(monkeypatch, {})
    assert wsl.windows_home() is None


def test_bridge_command_runs_the_wsl_install(monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    command = wsl.bridge_command(
        Path("/home/hari/.local/share/uv/tools/phi-protect/bin/python"), "m"
    )
    assert command == (
        "wsl.exe -d Ubuntu -e /home/hari/.local/share/uv/tools/phi-protect/bin/python -m m hook"
    )


def test_bridge_command_quotes_paths_with_spaces(monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    assert '-e "/home/my user/python"' in wsl.bridge_command(Path("/home/my user/python"), "m")
