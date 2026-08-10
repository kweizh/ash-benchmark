"""Initial-state checks for the ash_postgres_multitenancy_sql_expressions task.

These run BEFORE the executor starts and assert that the scaffold shipped by the image is
present, compiles offline, and does not already contain the solution.
"""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/billing"
LIB_DIR = os.path.join(PROJECT_DIR, "lib", "billing")


def _run(args, cwd=None, timeout=300):
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_elixir_toolchain_available():
    for binary in ("elixir", "mix", "erl"):
        assert shutil.which(binary) is not None, (
            f"{binary} was not found in PATH; the Elixir/OTP toolchain must be preinstalled."
        )

    result = _run(["elixir", "--version"])
    assert result.returncode == 0, f"`elixir --version` failed: {result.stderr}"
    assert "Elixir 1.18" in result.stdout, (
        f"Expected Elixir 1.18.x to be installed, got: {result.stdout!r}"
    )


def test_postgres_tooling_available():
    for binary in ("pg-start", "psql", "pg_isready"):
        assert shutil.which(binary) is not None, (
            f"{binary} was not found in PATH; PostgreSQL must be installed in the image."
        )


def test_postgres_server_starts_and_accepts_connections():
    result = _run(["pg-start"], timeout=180)
    assert result.returncode == 0, (
        f"`pg-start` failed to start the in-container PostgreSQL server: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    ready = _run(["pg_isready", "-h", "127.0.0.1", "-p", "5432"])
    assert ready.returncode == 0, (
        f"PostgreSQL is not accepting connections on 127.0.0.1:5432: {ready.stdout!r}"
    )

    version = _run(
        ["psql", "-h", "127.0.0.1", "-U", "postgres", "-tAc", "show server_version"]
    )
    assert version.returncode == 0, f"`psql` could not query the server: {version.stderr!r}"
    assert version.stdout.strip().startswith("16."), (
        f"Expected PostgreSQL 16.x, got {version.stdout.strip()!r}"
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_project_manifest_files_exist():
    for relative in ("mix.exs", "mix.lock", ".formatter.exs", "config/config.exs"):
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_mix_lock_pins_ash_and_ash_postgres():
    with open(os.path.join(PROJECT_DIR, "mix.lock")) as handle:
        lock = handle.read()

    assert '"ash"' in lock, "mix.lock does not pin the `ash` dependency."
    assert '"ash_postgres"' in lock, "mix.lock does not pin the `ash_postgres` dependency."


def test_dependencies_are_prefetched_and_compiled():
    for dependency in ("ash", "ash_postgres", "ecto_sql", "postgrex"):
        source = os.path.join(PROJECT_DIR, "deps", dependency)
        assert os.path.isdir(source), (
            f"Dependency source {source} is missing; deps must be vendored for offline use."
        )

        built = os.path.join(PROJECT_DIR, "_build", "dev", "lib", dependency, "ebin")
        assert os.path.isdir(built), (
            f"Dependency {dependency} is not compiled at {built}; the image must build deps offline."
        )


def test_scaffold_modules_exist():
    for relative in ("application.ex", "repo.ex", "trace.ex", "metering.ex"):
        path = os.path.join(LIB_DIR, relative)
        assert os.path.isfile(path), f"Expected scaffold module {path} to exist."


def test_repo_module_is_an_ash_postgres_repo():
    with open(os.path.join(LIB_DIR, "repo.ex")) as handle:
        repo = handle.read()

    assert "AshPostgres.Repo" in repo, "Billing.Repo must already be an AshPostgres repo."
    assert "min_pg_version" in repo, "Billing.Repo must already define min_pg_version/0."


def test_trace_helper_is_provided():
    with open(os.path.join(LIB_DIR, "trace.ex")) as handle:
        trace = handle.read()

    for function in ("def record(", "def entries", "def reset"):
        assert function in trace, f"Billing.Trace must already provide `{function}`."


def test_domain_starts_out_without_resources():
    with open(os.path.join(LIB_DIR, "metering.ex")) as handle:
        domain = handle.read()

    assert "use Ash.Domain" in domain, "Billing.Metering must already be an Ash domain."
    assert "resource " not in domain, (
        "Billing.Metering already registers resources; the scaffold must start empty."
    )


def test_repo_connection_settings_are_preconfigured():
    with open(os.path.join(PROJECT_DIR, "config", "config.exs")) as handle:
        config = handle.read()

    assert "billing_dev" in config, "config.exs must preconfigure the `billing_dev` database."
    assert "Billing.Repo" in config, "config.exs must preconfigure Billing.Repo."
    assert "ash_domains" in config, "config.exs must declare the ash_domains list."


def test_solution_modules_are_absent():
    forbidden_dirs = [
        os.path.join(LIB_DIR, "metering"),
        os.path.join(PROJECT_DIR, "priv", "repo", "migrations"),
        os.path.join(PROJECT_DIR, "priv", "repo", "tenant_migrations"),
        os.path.join(PROJECT_DIR, "priv", "resource_snapshots"),
    ]
    for path in forbidden_dirs:
        assert not os.path.exists(path), (
            f"{path} must not exist in the initial state; the executor has to create it."
        )

    assert not os.path.isfile(os.path.join(LIB_DIR, "tenancy.ex")), (
        "lib/billing/tenancy.ex must not exist in the initial state."
    )


def test_scaffold_compiles_offline():
    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    env["HEX_OFFLINE"] = "1"

    result = subprocess.run(
        ["mix", "compile"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    assert result.returncode == 0, (
        f"`mix compile` failed on the untouched scaffold: "
        f"stdout={result.stdout[-3000:]!r} stderr={result.stderr[-3000:]!r}"
    )
