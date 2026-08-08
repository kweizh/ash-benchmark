"""Initial-state verification for the ash_soft_delete_archive_cascade task.

These checks run BEFORE the executor starts working. They assert that the
prepared Mix project, the offline Ash dependency set and the empty domain shell
are all in place, and that none of the artifacts the executor has to build
already exist.
"""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/forum"
LIB_DIR = os.path.join(PROJECT_DIR, "lib", "forum")
CONTENT_DIR = os.path.join(LIB_DIR, "content")
ARCHIVE_DIR = os.path.join(LIB_DIR, "archive")

RESOURCE_FILES = [
    os.path.join(CONTENT_DIR, "post.ex"),
    os.path.join(CONTENT_DIR, "comment.ex"),
    os.path.join(CONTENT_DIR, "reaction.ex"),
]

SHARED_MODULE_FILES = [
    os.path.join(ARCHIVE_DIR, "preparations", "archive_scope.ex"),
    os.path.join(ARCHIVE_DIR, "changes", "cascade_archive.ex"),
    os.path.join(ARCHIVE_DIR, "changes", "cascade_restore.ex"),
]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_elixir_toolchain_available():
    for binary in ("elixir", "mix"):
        assert shutil.which(binary) is not None, (
            f"`{binary}` was not found in PATH; the Elixir toolchain is missing."
        )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_mix_project_files_exist():
    for relative in ("mix.exs", "mix.lock", "config/config.exs", "test/test_helper.exs"):
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected project file {path} to exist."


def test_mix_project_declares_forum_app():
    content = _read(os.path.join(PROJECT_DIR, "mix.exs"))
    assert "app: :forum" in content, (
        "mix.exs must declare the OTP application `:forum`."
    )
    assert ":ash" in content, "mix.exs must declare the `:ash` dependency."


def test_mix_lock_pins_ash_3_31_0():
    content = _read(os.path.join(PROJECT_DIR, "mix.lock"))
    assert '"ash": {:hex, :ash, "3.31.0"' in content, (
        "mix.lock must pin ash to version 3.31.0."
    )
    assert '"simple_sat"' in content, (
        "mix.lock must pin the simple_sat SAT solver dependency."
    )


def test_config_registers_the_domain():
    content = _read(os.path.join(PROJECT_DIR, "config", "config.exs"))
    assert "ash_domains: [Forum.Content]" in content, (
        "config/config.exs must register `ash_domains: [Forum.Content]`."
    )


def test_domain_shell_exists_without_resources():
    domain_path = os.path.join(LIB_DIR, "content.ex")
    assert os.path.isfile(domain_path), (
        f"Expected the domain shell {domain_path} to exist."
    )
    content = _read(domain_path)
    assert "defmodule Forum.Content do" in content, (
        "lib/forum/content.ex must define the `Forum.Content` module."
    )
    for resource in ("Forum.Content.Post", "Forum.Content.Comment", "Forum.Content.Reaction"):
        assert resource not in content, (
            f"{resource} must not be registered in the domain yet; the executor adds it."
        )


def test_resource_modules_are_not_implemented_yet():
    for path in RESOURCE_FILES:
        assert not os.path.exists(path), (
            f"{path} must not exist in the initial state; the executor creates it."
        )


def test_shared_archive_modules_are_not_implemented_yet():
    for path in SHARED_MODULE_FILES:
        assert not os.path.exists(path), (
            f"{path} must not exist in the initial state; the executor creates it."
        )


def test_ash_dependency_is_vendored_and_precompiled():
    assert os.path.isdir(os.path.join(PROJECT_DIR, "deps", "ash")), (
        "The `ash` dependency source must already be fetched into deps/ash."
    )
    assert os.path.isdir(os.path.join(PROJECT_DIR, "deps", "simple_sat")), (
        "The `simple_sat` dependency source must already be fetched into deps/simple_sat."
    )
    for mix_env in ("dev", "test"):
        beam_dir = os.path.join(PROJECT_DIR, "_build", mix_env, "lib", "ash", "ebin")
        assert os.path.isdir(beam_dir), (
            f"Ash must be pre-compiled for MIX_ENV={mix_env} (missing {beam_dir})."
        )


def test_project_compiles_offline():
    for mix_env in ("dev", "test"):
        env = dict(os.environ)
        env["MIX_ENV"] = mix_env
        result = subprocess.run(
            ["mix", "compile"],
            cwd=PROJECT_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"`mix compile` failed for MIX_ENV={mix_env}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_test_task_runs_on_the_empty_suite():
    env = dict(os.environ)
    env["MIX_ENV"] = "test"
    result = subprocess.run(
        ["mix", "test"],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        "`mix test` must succeed on the prepared project:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
