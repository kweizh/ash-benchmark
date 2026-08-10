"""Initial-state verification for the ash_keyset_pagination_feed_api task.

Checks that the offline Elixir/Ash scaffold at /home/user/feedapi is present,
compiles without network access, and that the read/pagination layer the executor
must build does not exist yet.
"""

import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/feedapi"

SCAFFOLD_FILES = [
    "mix.exs",
    "mix.lock",
    "config/config.exs",
    "lib/feed/timeline.ex",
    "lib/feed/timeline/author.ex",
    "lib/feed/timeline/activity.ex",
    "lib/feed/timeline/reaction.ex",
]


def _mix(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.setdefault("MIX_ENV", "dev")
    env["HEX_OFFLINE"] = "1"
    return subprocess.run(
        ["mix", *args],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_elixir_toolchain_available():
    assert shutil.which("elixir") is not None, "elixir was not found in PATH."
    assert shutil.which("mix") is not None, "mix was not found in PATH."


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_scaffold_files_exist():
    for rel in SCAFFOLD_FILES:
        path = os.path.join(PROJECT_DIR, rel)
        assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_ash_version_is_pinned():
    with open(os.path.join(PROJECT_DIR, "mix.exs")) as handle:
        mix_exs = handle.read()
    assert ":ash" in mix_exs, "mix.exs does not declare the :ash dependency."
    assert "3.31.0" in mix_exs, "mix.exs does not pin Ash to version 3.31.0."

    with open(os.path.join(PROJECT_DIR, "mix.lock")) as handle:
        mix_lock = handle.read()
    assert '"ash"' in mix_lock, "mix.lock does not contain a locked :ash dependency."
    assert '"jason"' in mix_lock, "mix.lock does not contain a locked :jason dependency."


def test_domain_is_configured():
    with open(os.path.join(PROJECT_DIR, "config/config.exs")) as handle:
        config = handle.read()
    assert "ash_domains" in config, "config/config.exs does not configure :ash_domains."
    assert "Feed.Timeline" in config, "config/config.exs does not register the Feed.Timeline domain."


def test_dependencies_are_vendored_for_offline_use():
    for dep in ("ash", "jason", "spark", "ecto"):
        path = os.path.join(PROJECT_DIR, "deps", dep)
        assert os.path.isdir(path), f"Dependency {dep} is not vendored at {path}."


def test_project_compiles_offline():
    result = _mix("compile")
    assert result.returncode == 0, (
        "`mix compile` failed on the untouched scaffold.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_write_side_code_interfaces_work():
    script = (
        'Feed.Timeline.create_author!(%{id: "seed", handle: "seed"});'
        'a = Feed.Timeline.publish_activity!(%{id: "seed1", body: "b", kind: :post,'
        ' visibility: :public, score: 3,'
        " published_at: ~U[2026-03-01 00:00:00.000000Z], author_id: \"seed\"});"
        'Feed.Timeline.create_reaction!(%{id: "seedr", kind: :like, activity_id: "seed1"});'
        'IO.puts("SEED_OK " <> a.id)'
    )
    result = _mix("run", "-e", script)
    assert result.returncode == 0, (
        "The scaffold write-side code interfaces did not run.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "SEED_OK seed1" in result.stdout, (
        f"Expected the seeding script to report SEED_OK. stdout:\n{result.stdout}"
    )


def test_read_layer_modules_are_absent():
    for rel in ("lib/feed/cursor.ex", "lib/feed/api.ex"):
        path = os.path.join(PROJECT_DIR, rel)
        assert not os.path.exists(path), (
            f"{path} already exists; the read/pagination layer must not be pre-built."
        )


def test_feed_read_actions_are_absent():
    script = (
        "actions = [:feed, :feed_offset, :public_feed, :hot_feed, :heat_feed,"
        " :strict_feed, :uncounted_feed, :flexible_feed, :author_feed];"
        " present = Enum.filter(actions, fn name ->"
        " Ash.Resource.Info.action(Feed.Timeline.Activity, name) != nil end);"
        ' IO.puts("PRESENT_ACTIONS " <> inspect(present));'
        ' IO.puts("REACTION_COUNT " <>'
        " inspect(Ash.Resource.Info.aggregate(Feed.Timeline.Activity, :reaction_count) != nil));"
        ' IO.puts("HEAT " <>'
        " inspect(Ash.Resource.Info.calculation(Feed.Timeline.Activity, :heat) != nil))"
    )
    result = _mix("run", "-e", script)
    assert result.returncode == 0, (
        "Could not introspect the Activity resource on the scaffold.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "PRESENT_ACTIONS []" in result.stdout, (
        "The feed read actions already exist on the scaffold; "
        f"stdout:\n{result.stdout}"
    )
    assert "REACTION_COUNT false" in result.stdout, (
        f"The :reaction_count aggregate already exists on the scaffold. stdout:\n{result.stdout}"
    )
    assert "HEAT false" in result.stdout, (
        f"The :heat calculation already exists on the scaffold. stdout:\n{result.stdout}"
    )
