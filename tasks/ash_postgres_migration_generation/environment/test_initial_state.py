"""Initial-state checks for the `ash_postgres_migration_generation` Harbor task.

These run BEFORE the executor starts. They assert that the offline Elixir +
Ash/ash_postgres toolchain, the local PostgreSQL 16 server and the empty
`/home/user/logistics` scaffold are all in place, and that none of the modules
the executor must write already exist.
"""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/logistics"
LIB_DIR = os.path.join(PROJECT_DIR, "lib", "logistics")
FREIGHT_DIR = os.path.join(LIB_DIR, "freight")
MIGRATIONS_DIR = os.path.join(PROJECT_DIR, "priv", "repo", "migrations")
SNAPSHOTS_DIR = os.path.join(PROJECT_DIR, "priv", "resource_snapshots")


def _run(args, timeout=180):
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_elixir_toolchain_available():
    for binary in ("elixir", "mix", "erl"):
        assert shutil.which(binary) is not None, (
            f"`{binary}` was not found in PATH; the Elixir/OTP toolchain is missing."
        )


def test_elixir_runs():
    proc = subprocess.run(
        ["elixir", "--version"], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, (
        f"`elixir --version` failed (exit {proc.returncode}): {proc.stderr}"
    )
    assert "Elixir" in proc.stdout, (
        f"`elixir --version` did not report an Elixir version: {proc.stdout!r}"
    )


def test_postgres_client_tools_available():
    for binary in ("psql", "pg_isready", "pg_ctl", "initdb", "pg-start"):
        assert shutil.which(binary) is not None, (
            f"`{binary}` was not found in PATH; the in-container PostgreSQL setup is incomplete."
        )


def test_postgres_data_directory_initialised():
    assert os.path.isfile("/srv/pgdata/PG_VERSION"), (
        "/srv/pgdata/PG_VERSION is missing; the PostgreSQL cluster was not initialised at build time."
    )


def test_postgres_server_accepts_connections():
    start = subprocess.run(
        ["pg-start"], capture_output=True, text=True, timeout=180
    )
    assert start.returncode == 0, (
        "`pg-start` failed to start the local PostgreSQL server: "
        f"stdout={start.stdout!r} stderr={start.stderr!r}"
    )
    ready = subprocess.run(
        ["pg_isready", "-h", "127.0.0.1", "-p", "5432"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert ready.returncode == 0, (
        f"PostgreSQL is not accepting connections on 127.0.0.1:5432: {ready.stdout!r}"
    )


def test_postgres_superuser_login_works():
    proc = subprocess.run(
        [
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tAc",
            "select 1",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PGPASSWORD": "postgres"},
    )
    assert proc.returncode == 0, (
        f"Could not log into PostgreSQL as `postgres`: {proc.stderr!r}"
    )
    assert proc.stdout.strip() == "1", (
        f"Unexpected result from `select 1`: {proc.stdout!r}"
    )


def test_citext_and_uuid_ossp_extensions_are_installable_offline():
    proc = subprocess.run(
        [
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tAc",
            "select name from pg_available_extensions where name in ('citext','uuid-ossp') order by name",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PGPASSWORD": "postgres"},
    )
    assert proc.returncode == 0, f"Could not query pg_available_extensions: {proc.stderr!r}"
    available = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert {"citext", "uuid-ossp"}.issubset(available), (
        f"postgresql-contrib extensions are missing; pg_available_extensions has {sorted(available)}"
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_project_scaffold_files_exist():
    for relative in (
        "mix.exs",
        "mix.lock",
        "config/config.exs",
        "lib/logistics/application.ex",
    ):
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_mix_project_declares_ash_and_ash_postgres():
    with open(os.path.join(PROJECT_DIR, "mix.exs"), encoding="utf-8") as handle:
        content = handle.read()
    assert ":ash," in content, "mix.exs does not declare the `:ash` dependency."
    assert ":ash_postgres," in content, "mix.exs does not declare the `:ash_postgres` dependency."
    assert "app: :logistics" in content, "mix.exs does not declare the OTP app `:logistics`."


def test_mix_lock_pins_ash_postgres():
    with open(os.path.join(PROJECT_DIR, "mix.lock"), encoding="utf-8") as handle:
        content = handle.read()
    for package in ("ash", "ash_postgres", "ecto_sql", "postgrex"):
        assert f'"{package}":' in content, (
            f"mix.lock does not pin `{package}`; dependencies were not resolved at build time."
        )


def test_config_declares_repo_domain_and_connection():
    with open(os.path.join(PROJECT_DIR, "config", "config.exs"), encoding="utf-8") as handle:
        content = handle.read()
    assert "ecto_repos: [Logistics.Repo]" in content, (
        "config/config.exs does not configure `ecto_repos: [Logistics.Repo]`."
    )
    assert "ash_domains: [Logistics.Freight]" in content, (
        "config/config.exs does not configure `ash_domains: [Logistics.Freight]`."
    )
    assert "logistics_dev" in content, (
        "config/config.exs does not configure the `logistics_dev` database."
    )
    assert "127.0.0.1" in content, (
        "config/config.exs does not point the repo at 127.0.0.1."
    )


def test_application_module_supervises_the_repo():
    path = os.path.join(LIB_DIR, "application.ex")
    with open(path, encoding="utf-8") as handle:
        content = handle.read()
    assert "Logistics.Repo" in content, (
        f"{path} does not supervise `Logistics.Repo`."
    )


def test_dependencies_are_prefetched_and_precompiled():
    for package in ("ash", "ash_postgres", "ecto_sql", "postgrex"):
        dep_dir = os.path.join(PROJECT_DIR, "deps", package)
        assert os.path.isdir(dep_dir), (
            f"Dependency source {dep_dir} is missing; deps were not vendored into the image."
        )
        build_dir = os.path.join(PROJECT_DIR, "_build", "dev", "lib", package, "ebin")
        assert os.path.isdir(build_dir), (
            f"Compiled artefacts {build_dir} are missing; deps were not compiled at build time."
        )


def test_hex_is_configured_for_offline_use():
    assert os.environ.get("HEX_OFFLINE") == "1", (
        "HEX_OFFLINE is not set to 1; the environment is not pinned to offline mode."
    )
    assert os.path.isdir("/opt/hex"), "HEX_HOME (/opt/hex) is missing from the image."


def test_repo_module_not_yet_written():
    path = os.path.join(LIB_DIR, "repo.ex")
    assert not os.path.exists(path), (
        f"{path} already exists; the executor is supposed to create the repository module."
    )


def test_domain_module_not_yet_written():
    path = os.path.join(LIB_DIR, "freight.ex")
    assert not os.path.exists(path), (
        f"{path} already exists; the executor is supposed to create the Ash domain."
    )


def test_no_resource_modules_present():
    if not os.path.isdir(FREIGHT_DIR):
        return
    leftovers = [name for name in os.listdir(FREIGHT_DIR) if name.endswith(".ex")]
    assert leftovers == [], (
        f"{FREIGHT_DIR} already contains resource modules {leftovers}; it must start empty."
    )


def test_no_migrations_present():
    assert os.path.isdir(MIGRATIONS_DIR), (
        f"Expected the empty migrations directory {MIGRATIONS_DIR} to exist."
    )
    migrations = [name for name in os.listdir(MIGRATIONS_DIR) if name.endswith(".exs")]
    assert migrations == [], (
        f"{MIGRATIONS_DIR} already contains migrations {migrations}; it must start empty."
    )


def test_no_resource_snapshots_present():
    assert not os.path.exists(SNAPSHOTS_DIR), (
        f"{SNAPSHOTS_DIR} already exists; resource snapshots must be produced by the executor."
    )


def test_target_database_does_not_exist_yet():
    proc = subprocess.run(
        [
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tAc",
            "select count(*) from pg_database where datname = 'logistics_dev'",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PGPASSWORD": "postgres"},
    )
    assert proc.returncode == 0, f"Could not query pg_database: {proc.stderr!r}"
    assert proc.stdout.strip() == "0", (
        "The `logistics_dev` database already exists; the executor must create it via migrations."
    )


def test_mix_can_run_offline():
    proc = _run(["mix", "loadpaths", "--no-deps-check", "--no-compile"])
    assert proc.returncode == 0, (
        "`mix loadpaths` failed in the scaffold project; the offline Mix setup is broken: "
        f"stdout={proc.stdout[-2000:]!r} stderr={proc.stderr[-2000:]!r}"
    )
