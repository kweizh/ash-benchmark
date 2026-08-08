"""Initial-state checks for the `ash_manual_relationship_read_actions` task.

These run BEFORE the executor starts working. They assert that the pre-built
Elixir/Ash scaffold is present and offline-ready, and that none of the pieces the
executor has to build already exist.
"""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/thread_graph"

SCAFFOLD_FILES = [
    "mix.exs",
    "mix.lock",
    ".formatter.exs",
    "config/config.exs",
    "lib/thread_graph/forum.ex",
    "lib/thread_graph/forum/load_counter.ex",
    "lib/thread_graph/forum/author.ex",
    "lib/thread_graph/forum/thread.ex",
    "lib/thread_graph/forum/message.ex",
    "lib/thread_graph/forum/message_link.ex",
]


def _run_elixir(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    return subprocess.run(
        ["mix", "run", "--no-start", "-e", code],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )


def test_elixir_toolchain_available():
    for binary in ("erl", "elixir", "mix"):
        assert shutil.which(binary) is not None, (
            f"`{binary}` was not found in PATH; the Erlang/Elixir toolchain is missing."
        )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_scaffold_files_exist():
    for relative in SCAFFOLD_FILES:
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_ash_dependency_is_vendored_and_locked():
    lock_path = os.path.join(PROJECT_DIR, "mix.lock")
    with open(lock_path, encoding="utf-8") as handle:
        lock = handle.read()
    assert '"ash"' in lock, "mix.lock does not pin the `ash` dependency."
    assert os.path.isdir(os.path.join(PROJECT_DIR, "deps", "ash")), (
        "deps/ash is missing; dependencies were not fetched at image build time."
    )


def test_dependencies_precompiled_for_dev_and_test():
    for mix_env in ("dev", "test"):
        build_dir = os.path.join(PROJECT_DIR, "_build", mix_env, "lib", "ash", "ebin")
        assert os.path.isdir(build_dir), (
            f"{build_dir} is missing; `ash` was not pre-compiled for MIX_ENV={mix_env}."
        )


def test_hex_is_configured_for_offline_use():
    assert os.environ.get("HEX_OFFLINE") == "1", (
        "HEX_OFFLINE is not set to 1; the image would try to reach the network."
    )
    assert os.environ.get("MIX_HOME"), "MIX_HOME is not set globally."
    assert os.environ.get("HEX_HOME"), "HEX_HOME is not set globally."


def test_project_compiles():
    result = subprocess.run(
        ["mix", "compile"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ, "MIX_ENV": "dev"},
    )
    assert result.returncode == 0, (
        "The scaffold project does not compile.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_load_counter_helper_is_usable():
    code = (
        "ThreadGraph.Forum.LoadCounter.reset();"
        "ThreadGraph.Forum.LoadCounter.bump(:probe);"
        "ThreadGraph.Forum.LoadCounter.bump(:probe);"
        'IO.puts("COUNT=" <> Integer.to_string(ThreadGraph.Forum.LoadCounter.count(:probe)))'
    )
    result = _run_elixir(code)
    assert result.returncode == 0, (
        f"Could not run ThreadGraph.Forum.LoadCounter.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "COUNT=2" in result.stdout, (
        f"ThreadGraph.Forum.LoadCounter did not count correctly. stdout:\n{result.stdout}"
    )


def test_base_resources_are_registered_in_the_domain():
    code = (
        "resources = Ash.Domain.Info.resources(ThreadGraph.Forum);"
        'IO.puts("RESOURCES=" <> Enum.map_join(Enum.sort(resources), ",", &inspect/1))'
    )
    result = _run_elixir(code)
    assert result.returncode == 0, (
        f"Could not introspect the ThreadGraph.Forum domain.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    for resource in (
        "ThreadGraph.Forum.Author",
        "ThreadGraph.Forum.Thread",
        "ThreadGraph.Forum.Message",
        "ThreadGraph.Forum.MessageLink",
    ):
        assert resource in result.stdout, (
            f"{resource} is not registered in the ThreadGraph.Forum domain. "
            f"stdout:\n{result.stdout}"
        )


def test_manual_relationships_and_actions_are_not_implemented_yet():
    code = (
        "rels = Enum.map(Ash.Resource.Info.relationships(ThreadGraph.Forum.Thread), & &1.name) ++"
        " Enum.map(Ash.Resource.Info.relationships(ThreadGraph.Forum.Message), & &1.name);"
        "acts = Enum.map(Ash.Resource.Info.actions(ThreadGraph.Forum.Thread), & &1.name) ++"
        " Enum.map(Ash.Resource.Info.actions(ThreadGraph.Forum.Message), & &1.name);"
        "aggs = Enum.map(Ash.Resource.Info.aggregates(ThreadGraph.Forum.Message), & &1.name);"
        'IO.puts("NAMES=" <> Enum.map_join(rels ++ acts ++ aggs, ",", &Atom.to_string/1))'
    )
    result = _run_elixir(code)
    assert result.returncode == 0, (
        f"Could not introspect the scaffold resources.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    line = next(
        (ln for ln in result.stdout.splitlines() if ln.startswith("NAMES=")),
        "",
    )
    names = set(line[len("NAMES=") :].split(","))
    for forbidden in (
        "recent_messages",
        "ancestor_messages",
        "linked_messages",
        "cross_board_highlights",
        "fork",
        "reply_count",
    ):
        assert forbidden not in names, (
            f"`{forbidden}` already exists in the scaffold; the task is pre-solved."
        )


def test_domain_code_interface_is_not_defined_yet():
    code = (
        "exports = ThreadGraph.Forum.__info__(:functions) |> Enum.map(&elem(&1, 0)) |> Enum.uniq();"
        'IO.puts("EXPORTS=" <> Enum.map_join(exports, ",", &Atom.to_string/1))'
    )
    result = _run_elixir(code)
    assert result.returncode == 0, (
        f"Could not introspect the ThreadGraph.Forum domain module.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    line = next(
        (ln for ln in result.stdout.splitlines() if ln.startswith("EXPORTS=")),
        "",
    )
    exports = set(line[len("EXPORTS=") :].split(","))
    for forbidden in ("highlights", "highlights!", "fork_thread", "fork_thread!"):
        assert forbidden not in exports, (
            f"ThreadGraph.Forum already exports `{forbidden}`; the task is pre-solved."
        )
