"""Initial-state verification for the ash_policy_bypass_rbac_hierarchy task."""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/orgguard"
MIX_EXS = os.path.join(PROJECT_DIR, "mix.exs")
MIX_LOCK = os.path.join(PROJECT_DIR, "mix.lock")
CONFIG_EXS = os.path.join(PROJECT_DIR, "config", "config.exs")
DOMAIN_EX = os.path.join(PROJECT_DIR, "lib", "orgguard", "access.ex")

ELIXIR_SNIPPET_RESOURCE_COUNT = (
    "IO.puts(:erlang.integer_to_binary("
    "length(Ash.Domain.Info.resources(OrgGuard.Access))))"
)

ELIXIR_SNIPPET_MODULES = (
    'IO.puts(Enum.map_join([OrgGuard.Access.Document, OrgGuard.Access.User, '
    "OrgGuard.Access.OrgUnit, OrgGuard.Access.RoleAssignment], \",\", "
    "fn m -> if Code.ensure_loaded?(m), do: \"loaded\", else: \"missing\" end))"
)


def _run_mix(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.setdefault("MIX_ENV", "dev")
    env["HEX_OFFLINE"] = "1"
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_elixir_toolchain_available():
    assert shutil.which("elixir") is not None, "elixir binary not found in PATH."
    assert shutil.which("mix") is not None, "mix binary not found in PATH."


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_mix_project_files_exist():
    assert os.path.isfile(MIX_EXS), f"{MIX_EXS} does not exist."
    assert os.path.isfile(MIX_LOCK), f"{MIX_LOCK} does not exist (deps must be pinned)."
    assert os.path.isfile(CONFIG_EXS), f"{CONFIG_EXS} does not exist."


def test_otp_app_is_orgguard():
    with open(MIX_EXS, encoding="utf-8") as handle:
        content = handle.read()
    assert "app: :orgguard" in content, "mix.exs does not declare the :orgguard OTP application."


def test_ash_and_sat_solver_are_pinned():
    with open(MIX_LOCK, encoding="utf-8") as handle:
        lock = handle.read()
    assert '"ash": {:hex, :ash, "3.31.0"' in lock, "mix.lock does not pin ash 3.31.0."
    assert '"simple_sat"' in lock, "mix.lock does not pin a SAT solver (simple_sat)."


def test_dependencies_are_vendored():
    for dep in ("ash", "simple_sat", "spark", "jason"):
        dep_dir = os.path.join(PROJECT_DIR, "deps", dep)
        assert os.path.isdir(dep_dir), f"Dependency {dep} is not vendored at {dep_dir}."


def test_dependencies_are_precompiled_for_dev_and_test():
    for mix_env in ("dev", "test"):
        build_dir = os.path.join(PROJECT_DIR, "_build", mix_env, "lib", "ash", "ebin")
        assert os.path.isdir(build_dir), (
            f"ash is not precompiled for MIX_ENV={mix_env} (missing {build_dir})."
        )


def test_domain_module_file_exists():
    assert os.path.isfile(DOMAIN_EX), f"Domain module file {DOMAIN_EX} does not exist."
    with open(DOMAIN_EX, encoding="utf-8") as handle:
        content = handle.read()
    assert "defmodule OrgGuard.Access" in content, (
        f"{DOMAIN_EX} does not define the OrgGuard.Access domain module."
    )


def test_project_compiles_offline():
    result = _run_mix(["mix", "compile", "--no-deps-check"])
    assert result.returncode == 0, (
        "The scaffold project does not compile offline.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_ash_version_is_available_at_runtime():
    result = _run_mix(
        ["mix", "run", "-e", 'IO.puts(to_string(Application.spec(:ash, :vsn)))']
    )
    assert result.returncode == 0, (
        f"Could not boot the project to read the ash version.\nstderr:\n{result.stderr}"
    )
    assert "3.31.0" in result.stdout, (
        f"Expected ash 3.31.0 to be available, got stdout: {result.stdout!r}"
    )


def test_domain_has_no_resources_yet():
    result = _run_mix(["mix", "run", "-e", ELIXIR_SNIPPET_RESOURCE_COUNT])
    assert result.returncode == 0, (
        f"Could not introspect the OrgGuard.Access domain.\nstderr:\n{result.stderr}"
    )
    assert result.stdout.strip().splitlines()[-1] == "0", (
        "The OrgGuard.Access domain already declares resources; the initial state must be empty. "
        f"stdout: {result.stdout!r}"
    )


def test_resource_modules_are_not_defined_yet():
    result = _run_mix(["mix", "run", "-e", ELIXIR_SNIPPET_MODULES])
    assert result.returncode == 0, (
        f"Could not check for resource modules.\nstderr:\n{result.stderr}"
    )
    last_line = result.stdout.strip().splitlines()[-1]
    assert last_line == "missing,missing,missing,missing", (
        "Resource modules must not exist in the initial state, but some are already defined: "
        f"{last_line!r}"
    )
