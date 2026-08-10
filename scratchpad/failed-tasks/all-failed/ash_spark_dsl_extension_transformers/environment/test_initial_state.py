import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = "/home/user/lifecycle"

PROBE = r"""
facts = %{
  "ash_vsn" => to_string(Application.spec(:ash, :vsn)),
  "spark_vsn" => to_string(Application.spec(:spark, :vsn)),
  "domain" => Code.ensure_loaded?(Lifecycle.Records),
  "event_resource" => Code.ensure_loaded?(Lifecycle.Records.ArchivalEvent),
  "stamp_note" => Code.ensure_loaded?(Lifecycle.Records.StampNote),
  "archival_extension" => Code.ensure_loaded?(Lifecycle.Archival),
  "hooks_extension" => Code.ensure_loaded?(Lifecycle.Archival.Hooks),
  "info" => Code.ensure_loaded?(Lifecycle.Archival.Info),
  "document" => Code.ensure_loaded?(Lifecycle.Records.Document),
  "contract" => Code.ensure_loaded?(Lifecycle.Records.Contract),
  "event_actions" =>
    Lifecycle.Records.ArchivalEvent
    |> Ash.Resource.Info.actions()
    |> Enum.map(&to_string(&1.name))
    |> Enum.sort(),
  "event_attributes" =>
    Lifecycle.Records.ArchivalEvent
    |> Ash.Resource.Info.attributes()
    |> Enum.map(&to_string(&1.name))
    |> Enum.sort(),
  "registered_resources" =>
    Lifecycle.Records
    |> Ash.Domain.Info.resources()
    |> Enum.map(&inspect/1)
    |> Enum.sort()
}

IO.puts("HARBOR_FACTS " <> Jason.encode!(facts))
"""


def _run(args, **kwargs):
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
        **kwargs,
    )


@pytest.fixture(scope="module")
def facts():
    compiled = _run(["mix", "compile"])
    assert compiled.returncode == 0, (
        "`mix compile` failed in the scaffold project:\n"
        f"stdout:\n{compiled.stdout}\nstderr:\n{compiled.stderr}"
    )

    probe_path = "/tmp/harbor_initial_probe.exs"
    with open(probe_path, "w", encoding="utf-8") as handle:
        handle.write(PROBE)

    result = _run(["mix", "run", probe_path])
    assert result.returncode == 0, (
        "`mix run` of the introspection probe failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    line = next(
        (
            raw
            for raw in result.stdout.splitlines()
            if raw.startswith("HARBOR_FACTS ")
        ),
        None,
    )
    assert line is not None, (
        "The introspection probe did not print a HARBOR_FACTS line.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return json.loads(line[len("HARBOR_FACTS ") :])


def test_elixir_toolchain_available():
    assert shutil.which("elixir") is not None, "`elixir` was not found in PATH."
    assert shutil.which("mix") is not None, "`mix` was not found in PATH."


def test_hex_offline_is_enabled():
    assert os.environ.get("HEX_OFFLINE") == "1", (
        "HEX_OFFLINE is expected to be set to '1' so that the build stays offline."
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


@pytest.mark.parametrize(
    "relative_path",
    [
        "mix.exs",
        "mix.lock",
        "config/config.exs",
        "lib/lifecycle/records.ex",
        "lib/lifecycle/records/archival_event.ex",
        "lib/lifecycle/records/stamp_note.ex",
    ],
)
def test_scaffold_files_exist(relative_path):
    path = os.path.join(PROJECT_DIR, relative_path)
    assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_dependencies_are_vendored():
    for dep in ("ash", "spark", "jason"):
        path = os.path.join(PROJECT_DIR, "deps", dep)
        assert os.path.isdir(path), (
            f"Dependency {dep} is not vendored at {path}; the project must build offline."
        )


def test_pinned_dependency_versions(facts):
    assert facts["ash_vsn"] == "3.31.0", (
        f"Expected Ash 3.31.0 to be available, found {facts['ash_vsn']}."
    )
    assert facts["spark_vsn"] == "2.7.2", (
        f"Expected Spark 2.7.2 to be available, found {facts['spark_vsn']}."
    )


def test_existing_domain_and_resources_are_present(facts):
    assert facts["domain"], "Lifecycle.Records domain is missing from the scaffold."
    assert facts["event_resource"], (
        "Lifecycle.Records.ArchivalEvent is missing from the scaffold."
    )
    assert facts["stamp_note"], (
        "Lifecycle.Records.StampNote is missing from the scaffold."
    )


def test_archival_event_shape(facts):
    assert "record" in facts["event_actions"], (
        "Lifecycle.Records.ArchivalEvent should already expose a `:record` action, "
        f"found actions {facts['event_actions']}."
    )
    for attribute in ("subject_id", "subject_type", "reason_code", "occurred_at"):
        assert attribute in facts["event_attributes"], (
            f"Lifecycle.Records.ArchivalEvent should already declare `{attribute}`, "
            f"found attributes {facts['event_attributes']}."
        )


def test_domain_registers_only_the_event_resource(facts):
    assert facts["registered_resources"] == ["Lifecycle.Records.ArchivalEvent"], (
        "The scaffold domain should start out registering only "
        f"Lifecycle.Records.ArchivalEvent, found {facts['registered_resources']}."
    )


def test_solution_modules_are_absent(facts):
    for key, module in (
        ("archival_extension", "Lifecycle.Archival"),
        ("hooks_extension", "Lifecycle.Archival.Hooks"),
        ("info", "Lifecycle.Archival.Info"),
        ("document", "Lifecycle.Records.Document"),
        ("contract", "Lifecycle.Records.Contract"),
    ):
        assert not facts[key], (
            f"{module} must not exist in the starting scaffold; it is part of the task."
        )
