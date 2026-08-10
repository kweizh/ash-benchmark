"""Initial-state checks for the ash_event_sourcing_projection_rebuild task.

These run BEFORE the executor starts. They assert that the Elixir/Ash scaffold is
present, compiles offline, and that none of the modules the executor must write
already exist.
"""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/vault"
LIB_DIR = os.path.join(PROJECT_DIR, "lib", "vault")


def _run(args, cwd=PROJECT_DIR, timeout=600):
    env = dict(os.environ)
    env.setdefault("MIX_ENV", "dev")
    env.setdefault("HEX_OFFLINE", "1")
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_elixir_toolchain_available():
    for binary in ("elixir", "mix", "erl"):
        assert shutil.which(binary) is not None, (
            f"`{binary}` was not found in PATH; the Elixir/OTP toolchain is missing."
        )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_mix_project_files_present():
    for relative in ("mix.exs", "mix.lock", os.path.join("config", "config.exs")):
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_mix_lock_pins_ash():
    with open(os.path.join(PROJECT_DIR, "mix.lock"), encoding="utf-8") as handle:
        content = handle.read()
    assert '"ash"' in content, "mix.lock does not pin the `ash` dependency."


def test_ash_dependency_declared_and_fetched():
    with open(os.path.join(PROJECT_DIR, "mix.exs"), encoding="utf-8") as handle:
        mix_exs = handle.read()
    assert ":ash" in mix_exs, "mix.exs does not declare the `ash` dependency."
    assert os.path.isdir(os.path.join(PROJECT_DIR, "deps", "ash")), (
        "The `ash` dependency has not been fetched into deps/."
    )


def test_ash_dependency_precompiled_for_dev():
    build_dir = os.path.join(PROJECT_DIR, "_build", "dev", "lib", "ash", "ebin")
    assert os.path.isdir(build_dir), (
        "ash was not pre-compiled at image build time (missing _build/dev/lib/ash/ebin)."
    )


def test_application_module_present():
    path = os.path.join(LIB_DIR, "application.ex")
    assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_hook_module_present():
    path = os.path.join(LIB_DIR, "ledger", "hook.ex")
    assert os.path.isfile(path), f"Expected scaffold file {path} to exist."
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    assert "defmodule Vault.Ledger.Hook" in source, (
        "The scaffold hook module is not named Vault.Ledger.Hook."
    )
    for callback in ("def set(", "def clear(", "def count(", "def run("):
        assert callback in source, f"Vault.Ledger.Hook is missing `{callback}`."


def test_domain_is_configured_but_not_implemented():
    config_path = os.path.join(PROJECT_DIR, "config", "config.exs")
    with open(config_path, encoding="utf-8") as handle:
        config = handle.read()
    assert "Vault.Ledger" in config, (
        "config/config.exs does not list the Vault.Ledger domain."
    )
    assert not os.path.exists(os.path.join(LIB_DIR, "ledger.ex")), (
        "lib/vault/ledger.ex already exists; the domain must be written by the executor."
    )


def test_solution_modules_absent():
    ledger_dir = os.path.join(LIB_DIR, "ledger")
    assert os.path.isdir(ledger_dir), f"Expected {ledger_dir} to exist."
    existing = sorted(os.listdir(ledger_dir))
    assert existing == ["hook.ex"], (
        "lib/vault/ledger should only contain the scaffold hook module, found: "
        f"{existing}"
    )


def test_project_compiles_offline():
    result = _run(["mix", "compile"])
    assert result.returncode == 0, (
        "`mix compile` failed on the untouched scaffold:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_ash_is_loadable_at_runtime():
    result = _run(
        [
            "mix",
            "run",
            "-e",
            'IO.puts(to_string(Application.spec(:ash, :vsn)))',
        ]
    )
    assert result.returncode == 0, (
        "Could not load the ash application:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert result.stdout.strip().startswith("3."), (
        f"Expected an Ash 3.x runtime, got: {result.stdout.strip()!r}"
    )
