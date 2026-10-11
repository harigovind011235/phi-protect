"""`phi-protect` command line: set up the Claude Code hooks, manage the service, run the hook.

Only `setup` and `serve` load the NER model; the hook calls the running service, so it starts fast.
"""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from phi_protect.cli import claude_settings, service_process, wsl
from phi_protect.cli.clipboard import copy_to_clipboard
from phi_protect.cli.hook import WARN, HookContext, failed_unexpectedly, handle_event
from phi_protect.cli.prompt_override import PromptOverrides
from phi_protect.cli.self_test_sample import SELF_TEST_TEXT
from phi_protect.cli.service_client import ServiceClient, ServiceError
from phi_protect.config.settings import Settings, create_settings

START_WAIT_SECONDS = 90
OVERRIDE_FILE = service_process.STATE_DIR / "prompt-override.json"
FAIL_CLOSED_NOTE = (
    "Note: update Claude Code to 2.1.295 or later (`claude update`) for {where} and run setup "
    "again, so that a crashed hook also blocks instead of letting content through."
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "hook":
        return _hook()
    return args.handler(args, create_settings())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phi-protect", description="Keeps PHI out of AI tools.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler, description in [
        ("setup", _setup, "download the model, add the Claude Code hooks, start the service"),
        ("uninstall", _uninstall, "remove the Claude Code hooks and stop the service"),
        ("start", _start, "start the service in the background"),
        ("stop", _stop, "stop the background service"),
        ("status", _status, "show whether the service is running and where hooks are installed"),
        ("serve", _serve, "run the service in the foreground"),
        ("deidentify", _deidentify, "write a de-identified copy of a file"),
        ("hook", None, "used by Claude Code; reads a hook event from stdin"),
    ]:
        command = commands.add_parser(name, help=description)
        command.set_defaults(handler=handler)
        if name in ("setup", "uninstall"):
            command.add_argument(
                "--project", type=Path, help="only this project folder (default: all projects)"
            )
            command.add_argument(
                "--windows",
                action="store_true",
                help="from WSL: also cover Claude Code running on Windows (VS Code, desktop app)",
            )
        if name == "deidentify":
            command.add_argument("file", type=Path)
            command.add_argument("-o", "--output", type=Path, help="where to write the copy")
    return parser


def _hook() -> int:
    # Read before the settings, so a broken configuration still gets the intended mode.
    mode = os.environ.get("PHI_MODE", WARN)
    try:
        settings = create_settings()
        mode = settings.mode
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        context = HookContext(
            client=ServiceClient(settings.client_url),
            start_service=_starter(settings),
            copy_text=copy_to_clipboard,
            overrides=PromptOverrides(OVERRIDE_FILE),
            mode=mode,
        )
        outcome = handle_event(event, context)
    except Exception as error:  # last line of defence: warn mode continues, block mode blocks
        outcome = failed_unexpectedly(error, mode)
    # UTF-8 bytes regardless of the console encoding (Windows defaults to a legacy code page,
    # where non-English text would crash the hook and let the content through).
    sys.stdout.buffer.write(outcome.stdout.encode("utf-8"))
    sys.stderr.buffer.write(outcome.stderr.encode("utf-8"))
    return outcome.exit_code


def _setup(args: argparse.Namespace, settings: Settings) -> int:
    from phi_protect.composition import create_container

    targets = _hook_targets(args, settings)
    if targets is None:
        return 1
    print("1/4 Loading the PHI detection model (the first run downloads about 0.4 GB)...")
    container = create_container(settings)
    print("2/4 Running a self-test...")
    if not asyncio.run(container.scan_service.scan_text(SELF_TEST_TEXT)).has_phi:
        print("Self-test failed: no PHI found in a known example. Nothing was installed.")
        return 1

    print("3/4 Adding the Claude Code hooks")
    for target in targets:
        backup = claude_settings.install_hooks(target.path, target.command, target.fail_closed)
        print(f"    {target.label}: {target.path}")
        if backup:
            print(f"    Previous settings saved to {backup}")

    print("4/4 Starting the service in the background...")
    if not _start_and_wait(settings):
        print(f"    The service did not start; see {service_process.LOG_FILE}")
        return 1
    print("\nDone. Start a new Claude Code session; prompts and file reads are now checked.")
    if settings.mode == WARN:
        print("Mode: warn. Likely PHI is flagged and you decide; set PHI_MODE=block to enforce.")
        return 0
    for target in targets:
        if not target.fail_closed:
            print(FAIL_CLOSED_NOTE.format(where=target.label))
    return 0


def _uninstall(args: argparse.Namespace, settings: Settings) -> int:
    targets = _hook_targets(args, settings)
    if targets is None:
        return 1
    for target in targets:
        removed = claude_settings.uninstall_hooks(target.path)
        state = "Hooks removed from" if removed else "No PHI Protect hooks found in"
        print(f"{state} {target.path}")
    if service_process.stop():
        print("Service stopped")
    return 0


def _start(_: argparse.Namespace, settings: Settings) -> int:
    if not _start_and_wait(settings):
        print(f"The service did not start; see {service_process.LOG_FILE}")
        return 1
    print(f"Running at {settings.client_url}")
    return 0


def _stop(_: argparse.Namespace, settings: Settings) -> int:
    print(
        "Service stopped"
        if service_process.stop()
        else "The service was not started by phi-protect"
    )
    return 0


def _status(_: argparse.Namespace, settings: Settings) -> int:
    running = ServiceClient(settings.client_url).is_running()
    print(f"Service: {'running' if running else 'not running'} at {settings.client_url}")
    places = [
        ("all projects", claude_settings.settings_path(None)),
        ("this folder", claude_settings.settings_path(Path.cwd())),
    ]
    windows_home = wsl.windows_home() if wsl.is_wsl() else None
    if windows_home:
        places.append(("Claude Code on Windows", windows_home / ".claude" / "settings.json"))
    for label, path in places:
        state = "installed" if claude_settings.hooks_installed(path) else "not installed"
        print(f"Hooks for {label}: {state} ({path})")
    print(f"Log: {service_process.LOG_FILE}")
    return 0 if running else 1


def _serve(_: argparse.Namespace, settings: Settings) -> int:
    import uvicorn

    from phi_protect.composition import create_container
    from phi_protect.handler.app import create_app

    uvicorn.run(create_app(create_container(settings)), host=settings.host, port=settings.port)
    return 0


def _deidentify(args: argparse.Namespace, settings: Settings) -> int:
    if not _start_and_wait(settings):
        print("The PHI Protect service is not running; see `phi-protect status`")
        return 1
    try:
        content, media_type = ServiceClient(settings.client_url).deidentify_file(
            args.file.read_bytes()
        )
    except ServiceError as error:
        print(f"Could not de-identify {args.file}: {error}")
        return 1
    extension = "pdf" if "pdf" in media_type else "txt"
    output = args.output or args.file.with_name(f"{args.file.stem}.deidentified.{extension}")
    output.write_bytes(content)
    print(f"Wrote {output}. Review it before sharing: detection can miss values.")
    return 0


@dataclass(frozen=True)
class HookTarget:
    label: str
    path: Path
    command: str
    fail_closed: bool


def _hook_targets(args: argparse.Namespace, settings: Settings) -> list[HookTarget] | None:
    """Where hooks go: this environment, plus Windows-side Claude Code when asked from WSL."""
    if args.windows and not wsl.is_wsl():
        print("--windows works from WSL only. On Windows itself, install and run setup there.")
        return None
    python = Path(sys.executable)
    # A crashed hook blocks only when enforcing; a crashed helper should not stop the user.
    enforce = settings.mode != WARN
    targets = [
        HookTarget(
            "Claude Code here" if args.project is None else "this project",
            claude_settings.settings_path(args.project),
            claude_settings.hook_command(python),
            enforce and claude_settings.supports_fail_closed(claude_settings.claude_version()),
        )
    ]
    if not args.windows:
        return targets
    windows_home = wsl.windows_home()
    if windows_home is None:
        print("Could not find your Windows home folder from WSL.")
        return None
    targets.append(
        HookTarget(
            "Claude Code on Windows",
            windows_home / ".claude" / "settings.json",
            wsl.bridge_command(python, claude_settings.HOOK_MODULE),
            enforce and claude_settings.supports_fail_closed(wsl.windows_claude_version()),
        )
    )
    return targets


def _start_and_wait(settings: Settings) -> bool:
    client = ServiceClient(settings.client_url)
    if client.is_running():
        return True
    _starter(settings)()
    return client.wait_until_running(START_WAIT_SECONDS)


def _starter(settings: Settings) -> Callable[[], bool]:
    """Only a local service is started automatically; a remote (on-prem) one runs elsewhere."""
    return (lambda: False) if settings.service_url else service_process.start_in_background


if __name__ == "__main__":
    sys.exit(main())
