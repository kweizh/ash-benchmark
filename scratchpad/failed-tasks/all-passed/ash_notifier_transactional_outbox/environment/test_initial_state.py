"""Initial-state checks for the Ash transactional-outbox task.

These run BEFORE the executor starts and verify that the pre-built environment is
complete (Elixir toolchain, vendored + compiled Ash dependency, scaffolded ledger
project) and that the eventing subsystem the executor must build is NOT present yet.
"""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/outbox"


def _run_elixir(expression: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["mix", "run", "--no-start", "-e", expression],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )


def test_elixir_toolchain_available() -> None:
    for binary in ("elixir", "mix", "erl"):
        assert shutil.which(binary) is not None, (
            f"`{binary}` was not found in PATH; the Elixir/OTP toolchain is missing."
        )


def test_project_directory_exists() -> None:
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_mix_project_files_exist() -> None:
    for relative in ("mix.exs", "mix.lock", "config/config.exs"):
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected project file {path} is missing."


def test_scaffolded_ledger_sources_exist() -> None:
    expected = (
        "lib/outbox/application.ex",
        "lib/outbox/ledger.ex",
        "lib/outbox/ledger/account.ex",
        "lib/outbox/ledger/transfer.ex",
        "lib/outbox/ledger/sufficient_funds.ex",
    )
    for relative in expected:
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected scaffold source {path} is missing."


def test_ash_dependency_is_vendored_and_compiled() -> None:
    ash_dir = os.path.join(PROJECT_DIR, "deps", "ash")
    assert os.path.isdir(ash_dir), (
        f"Ash is not vendored at {ash_dir}; the image must work offline."
    )
    build_dir = os.path.join(PROJECT_DIR, "_build")
    assert os.path.isdir(build_dir), (
        f"{build_dir} is missing; dependencies must be pre-compiled at image build time."
    )


def test_mix_lock_pins_ash() -> None:
    lock_path = os.path.join(PROJECT_DIR, "mix.lock")
    with open(lock_path, encoding="utf-8") as handle:
        lock = handle.read()
    assert '"ash"' in lock, "mix.lock does not pin the `ash` dependency."


def test_config_registers_only_the_ledger_domain() -> None:
    config_path = os.path.join(PROJECT_DIR, "config", "config.exs")
    with open(config_path, encoding="utf-8") as handle:
        config = handle.read()
    assert "Outbox.Ledger" in config, (
        "config/config.exs does not register the Outbox.Ledger domain."
    )
    assert "Outbox.Eventing" not in config, (
        "config/config.exs already registers Outbox.Eventing; the task is pre-solved."
    )


def test_eventing_subsystem_is_not_present_yet() -> None:
    unexpected = (
        "lib/outbox/eventing.ex",
        "lib/outbox/eventing",
        "lib/outbox/ledger/bulk_ops.ex",
    )
    for relative in unexpected:
        path = os.path.join(PROJECT_DIR, relative)
        assert not os.path.exists(path), (
            f"{path} already exists; the executor is supposed to create it."
        )


def test_ledger_resources_have_no_notifier_yet() -> None:
    for relative in ("lib/outbox/ledger/account.ex", "lib/outbox/ledger/transfer.ex"):
        path = os.path.join(PROJECT_DIR, relative)
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        assert "notifiers" not in source, (
            f"{path} already declares notifiers; the task is pre-solved."
        )


def test_project_compiles_offline() -> None:
    result = subprocess.run(
        ["mix", "compile"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, (
        "`mix compile` failed in the scaffold project:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_ash_version_is_three() -> None:
    result = _run_elixir(
        'IO.puts("ASH_VERSION=" <> to_string(Application.spec(:ash, :vsn)))'
    )
    assert result.returncode == 0, (
        f"Could not query the Ash version:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    marker = "ASH_VERSION="
    assert marker in result.stdout, f"Unexpected output while querying Ash: {result.stdout}"
    version = result.stdout.split(marker, 1)[1].split()[0]
    assert version.startswith("3."), f"Expected Ash 3.x, found {version}."


def test_ledger_resources_are_loadable_and_eventing_is_absent() -> None:
    expression = (
        'IO.puts("ACCOUNT=" <> to_string(Code.ensure_loaded?(Outbox.Ledger.Account)));'
        'IO.puts("TRANSFER=" <> to_string(Code.ensure_loaded?(Outbox.Ledger.Transfer)));'
        'IO.puts("EVENT=" <> to_string(Code.ensure_loaded?(Outbox.Eventing.Event)));'
        'IO.puts("DISPATCHER=" <> to_string(Code.ensure_loaded?(Outbox.Eventing.Dispatcher)))'
    )
    result = _run_elixir(expression)
    assert result.returncode == 0, (
        f"Could not load the scaffold modules:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "ACCOUNT=true" in result.stdout, "Outbox.Ledger.Account is not compiled."
    assert "TRANSFER=true" in result.stdout, "Outbox.Ledger.Transfer is not compiled."
    assert "EVENT=false" in result.stdout, (
        "Outbox.Eventing.Event already exists; the task is pre-solved."
    )
    assert "DISPATCHER=false" in result.stdout, (
        "Outbox.Eventing.Dispatcher already exists; the task is pre-solved."
    )
