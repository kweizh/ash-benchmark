import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/ledger"
LIB_DIR = os.path.join(PROJECT_DIR, "lib")

SOLUTION_MODULES = [
    "Ledger.Money",
    "Ledger.Money.Type",
    "Ledger.Money.Usd",
    "Ledger.Billing.Invoice",
    "Ledger.Billing.Payment",
]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _source_files() -> list:
    collected = []
    for root, _dirs, files in os.walk(LIB_DIR):
        for name in files:
            if name.endswith(".ex") or name.endswith(".exs"):
                collected.append(os.path.join(root, name))
    return collected


def test_elixir_toolchain_available():
    assert shutil.which("elixir") is not None, "elixir was not found in PATH."
    assert shutil.which("mix") is not None, "mix was not found in PATH."


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_mix_project_files_exist():
    for relative in ["mix.exs", "mix.lock", "config/config.exs"]:
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected {path} to exist in the initial project."


def test_ash_dependency_declared_and_locked():
    mix_exs = _read(os.path.join(PROJECT_DIR, "mix.exs"))
    assert ":ash" in mix_exs, "mix.exs does not declare the :ash dependency."
    assert ":jason" in mix_exs, "mix.exs does not declare the :jason dependency."

    mix_lock = _read(os.path.join(PROJECT_DIR, "mix.lock"))
    assert '"ash"' in mix_lock, "mix.lock does not pin the ash dependency."


def test_money_libraries_are_not_available():
    mix_exs = _read(os.path.join(PROJECT_DIR, "mix.exs"))
    assert "ash_money" not in mix_exs, "ash_money must not be available in this task."
    assert "ex_money" not in mix_exs, "ex_money must not be available in this task."

    deps_dir = os.path.join(PROJECT_DIR, "deps")
    assert os.path.isdir(deps_dir), f"Expected vendored dependencies at {deps_dir}."
    vendored = os.listdir(deps_dir)
    assert "ash" in vendored, "The ash dependency has not been vendored into deps/."
    assert "ash_money" not in vendored, "ash_money must not be vendored into deps/."
    assert "ex_money" not in vendored, "ex_money must not be vendored into deps/."


def test_dependencies_are_precompiled_for_dev_and_test():
    for env in ["dev", "test"]:
        path = os.path.join(PROJECT_DIR, "_build", env, "lib", "ash", "ebin")
        assert os.path.isdir(path), f"Expected precompiled ash beam files at {path}."


def test_domain_module_exists_without_resources():
    domain_path = os.path.join(LIB_DIR, "ledger", "billing.ex")
    assert os.path.isfile(domain_path), f"Expected the empty domain module at {domain_path}."
    source = _read(domain_path)
    assert "defmodule Ledger.Billing do" in source, "Ledger.Billing domain module is missing."
    assert "use Ash.Domain" in source, "Ledger.Billing does not use Ash.Domain."
    assert "resource " not in source, "The initial domain must not register any resources yet."


def test_domain_is_registered_in_config():
    config = _read(os.path.join(PROJECT_DIR, "config", "config.exs"))
    assert "ash_domains" in config, "config/config.exs does not configure ash_domains."
    assert "Ledger.Billing" in config, "config/config.exs does not register Ledger.Billing."


def test_solution_sources_are_absent():
    for path in _source_files():
        source = _read(path)
        for module in SOLUTION_MODULES:
            assert f"defmodule {module} do" not in source, (
                f"{path} already defines {module}; the solution must not be present initially."
            )


def test_project_compiles_and_solution_modules_are_undefined():
    script = ";".join(
        f'IO.puts("MODULE {module} " <> to_string(Code.ensure_loaded?({module})))'
        for module in SOLUTION_MODULES
    )
    result = subprocess.run(
        ["mix", "run", "--no-start", "-e", script],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        "The initial project must compile offline. "
        f"stdout={result.stdout[-2000:]} stderr={result.stderr[-2000:]}"
    )
    for module in SOLUTION_MODULES:
        assert f"MODULE {module} false" in result.stdout, (
            f"{module} is already defined in the initial project."
        )
