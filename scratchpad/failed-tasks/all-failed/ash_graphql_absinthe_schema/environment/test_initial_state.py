import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/tracker"

SCAFFOLD_FILES = [
    "mix.exs",
    "mix.lock",
    "config/config.exs",
    "lib/tracker/application.ex",
    "lib/tracker/delivery.ex",
    "lib/tracker/delivery/user.ex",
    "lib/tracker/delivery/user_role.ex",
    "lib/tracker/delivery/project.ex",
    "lib/tracker/delivery/ticket.ex",
    "lib/tracker/delivery/ticket_status.ex",
    "lib/tracker/delivery/label.ex",
    "lib/tracker/delivery/ticket_label.ex",
    "lib/tracker/delivery/errors/sprint_frozen.ex",
    "lib/tracker/delivery/seed.ex",
]


def _run(args, timeout=600):
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_elixir_toolchain_available():
    assert shutil.which("elixir") is not None, "elixir binary not found in PATH."
    assert shutil.which("mix") is not None, "mix binary not found in PATH."


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_scaffold_files_exist():
    for relative in SCAFFOLD_FILES:
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_graphql_schema_module_is_not_provided():
    path = os.path.join(PROJECT_DIR, "lib/tracker/graphql_schema.ex")
    assert not os.path.exists(path), (
        f"{path} must not exist in the initial state; the executor has to create it."
    )


def test_dependencies_are_vendored_and_pinned():
    for dep in ["ash", "ash_graphql", "absinthe", "absinthe_plug", "simple_sat"]:
        path = os.path.join(PROJECT_DIR, "deps", dep)
        assert os.path.isdir(path), f"Expected dependency directory {path} to be vendored."

    with open(os.path.join(PROJECT_DIR, "mix.lock")) as handle:
        lock = handle.read()

    assert '"ash": {:hex, :ash, "3.31.0"' in lock, "mix.lock must pin ash 3.31.0."
    assert '"ash_graphql": {:hex, :ash_graphql, "1.10.0"' in lock, (
        "mix.lock must pin ash_graphql 1.10.0."
    )
    assert '"absinthe": {:hex, :absinthe, "1.11.0"' in lock, (
        "mix.lock must pin absinthe 1.11.0."
    )


def test_project_compiles_offline():
    result = _run(["mix", "compile"])
    assert result.returncode == 0, (
        "The scaffold project must compile offline.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_ash_domain_and_seed_module_work():
    script = (
        "Tracker.Delivery.Seed.seed!();"
        'IO.puts("TICKETS=" <> Integer.to_string(length(Ash.read!(Tracker.Delivery.Ticket))));'
        'IO.puts("PROJECTS=" <> Integer.to_string(length(Ash.read!(Tracker.Delivery.Project, authorize?: false))))'
    )
    result = _run(["mix", "run", "-e", script])
    assert result.returncode == 0, (
        "Seeding the pre-existing Ash domain must succeed.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "TICKETS=6" in result.stdout, (
        f"Expected the fixture set to contain 6 tickets, got:\n{result.stdout}"
    )
    assert "PROJECTS=2" in result.stdout, (
        f"Expected the fixture set to contain 2 projects, got:\n{result.stdout}"
    )


def test_graphql_schema_module_is_not_compiled_yet():
    script = (
        'IO.puts("LOADED=" <> to_string(Code.ensure_loaded?(Module.concat(["Tracker.GraphqlSchema"]))))'
    )
    result = _run(["mix", "run", "-e", script])
    assert result.returncode == 0, (
        f"mix run failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "LOADED=false" in result.stdout, (
        "Tracker.GraphqlSchema must not exist in the initial state; "
        f"got:\n{result.stdout}"
    )
