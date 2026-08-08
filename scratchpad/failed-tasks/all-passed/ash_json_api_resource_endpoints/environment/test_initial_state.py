"""Initial-state checks for the ash_json_api_resource_endpoints task.

These run BEFORE the executor starts working. They assert that the scaffold
project exists, that every dependency is already vendored and compiled, and
that none of the work the executor is supposed to do has been done yet.
"""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/catalog"
LIB_DIR = os.path.join(PROJECT_DIR, "lib")
DEPS_DIR = os.path.join(PROJECT_DIR, "deps")

REQUIRED_DEPS = [
    "ash",
    "ash_json_api",
    "open_api_spex",
    "plug",
    "bandit",
    "jason",
    "picosat_elixir",
]


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def test_elixir_toolchain_available() -> None:
    assert shutil.which("elixir") is not None, "elixir was not found in PATH."
    assert shutil.which("mix") is not None, "mix was not found in PATH."


def test_elixir_runs() -> None:
    result = subprocess.run(
        ["elixir", "--version"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "`elixir --version` failed with exit code "
        f"{result.returncode}: {result.stdout}{result.stderr}"
    )


def test_project_directory_exists() -> None:
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_mix_project_files_exist() -> None:
    for relative in ("mix.exs", "mix.lock", "config/config.exs"):
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_application_module_exists() -> None:
    path = os.path.join(LIB_DIR, "catalog", "application.ex")
    assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_mix_exs_declares_required_dependencies() -> None:
    content = _read(os.path.join(PROJECT_DIR, "mix.exs"))
    for dep in REQUIRED_DEPS:
        assert f":{dep}," in content, f"mix.exs does not declare the {dep} dependency."


def test_dependencies_are_vendored() -> None:
    assert os.path.isdir(DEPS_DIR), f"Vendored dependency directory {DEPS_DIR} is missing."
    for dep in REQUIRED_DEPS:
        path = os.path.join(DEPS_DIR, dep)
        assert os.path.isdir(path), f"Dependency source {path} is missing from the image."


def test_dependencies_are_precompiled_for_dev_and_test() -> None:
    for mix_env in ("dev", "test"):
        for dep in ("ash", "ash_json_api"):
            path = os.path.join(PROJECT_DIR, "_build", mix_env, "lib", dep, "ebin")
            assert os.path.isdir(path), (
                f"Dependency {dep} is not precompiled for MIX_ENV={mix_env} ({path} missing)."
            )


def test_json_api_media_type_is_configured() -> None:
    content = _read(os.path.join(PROJECT_DIR, "config", "config.exs"))
    assert "application/vnd.api+json" in content, (
        "config/config.exs does not register the application/vnd.api+json media type."
    )


def test_no_domain_or_resource_modules_yet() -> None:
    unexpected = []
    for root, _dirs, files in os.walk(LIB_DIR):
        for name in files:
            if not name.endswith(".ex"):
                continue
            path = os.path.join(root, name)
            if os.path.relpath(path, LIB_DIR) == os.path.join("catalog", "application.ex"):
                continue
            unexpected.append(path)
    assert not unexpected, (
        "The scaffold must only contain lib/catalog/application.ex, but found: "
        f"{sorted(unexpected)}"
    )


def test_scaffold_has_no_json_api_wiring() -> None:
    offenders = []
    for root, _dirs, files in os.walk(LIB_DIR):
        for name in files:
            if not name.endswith(".ex"):
                continue
            path = os.path.join(root, name)
            content = _read(path)
            if "AshJsonApi" in content or "Ash.Resource" in content or "Ash.Domain" in content:
                offenders.append(path)
    assert not offenders, (
        "The scaffold must not contain any Ash domain, resource or JSON:API wiring, "
        f"but these files already do: {sorted(offenders)}"
    )


def test_application_supervises_nothing_yet() -> None:
    content = _read(os.path.join(LIB_DIR, "catalog", "application.ex"))
    assert "Bandit" not in content and "Plug.Cowboy" not in content, (
        "The scaffold application must not start an HTTP server yet."
    )
