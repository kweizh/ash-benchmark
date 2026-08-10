"""Initial-state checks for the ash_bulk_actions_stream_pipeline task."""

import os
import re
import shutil
import subprocess

PROJECT_DIR = "/home/user/ingest"
MIX_EXS = os.path.join(PROJECT_DIR, "mix.exs")
MIX_LOCK = os.path.join(PROJECT_DIR, "mix.lock")
CONFIG_EXS = os.path.join(PROJECT_DIR, "config", "config.exs")
DOMAIN_EX = os.path.join(PROJECT_DIR, "lib", "ingest", "pipeline.ex")
METER_EX = os.path.join(PROJECT_DIR, "lib", "ingest", "pipeline", "meter.ex")


def _run_mix(args, timeout=300):
    env = dict(os.environ)
    env.setdefault("MIX_ENV", "dev")
    return subprocess.run(
        ["mix"] + args,
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
    for path in (MIX_EXS, MIX_LOCK, CONFIG_EXS, DOMAIN_EX, METER_EX):
        assert os.path.isfile(path), f"Expected scaffold file {path} is missing."


def test_mix_exs_pins_ash_3_31_0():
    with open(MIX_EXS, encoding="utf-8") as handle:
        content = handle.read()
    assert re.search(r':ash,\s*"==\s*3\.31\.0"', content), (
        "mix.exs must pin the Ash dependency to == 3.31.0."
    )


def test_mix_lock_contains_ash_3_31_0():
    with open(MIX_LOCK, encoding="utf-8") as handle:
        content = handle.read()
    assert '"ash"' in content, "mix.lock does not contain a locked ash dependency."
    assert "3.31.0" in content, "mix.lock does not lock ash at version 3.31.0."


def test_config_registers_the_domain():
    with open(CONFIG_EXS, encoding="utf-8") as handle:
        content = handle.read()
    assert "ash_domains" in content and "Ingest.Pipeline" in content, (
        "config/config.exs must register Ingest.Pipeline in :ash_domains."
    )


def test_dependencies_are_prefetched_offline():
    deps_dir = os.path.join(PROJECT_DIR, "deps", "ash")
    assert os.path.isdir(deps_dir), (
        "The ash dependency is not vendored under /home/user/ingest/deps; the image "
        "must ship prefetched dependencies because there is no network access."
    )
    assert os.environ.get("HEX_OFFLINE") == "1", (
        "HEX_OFFLINE must be set to 1 so that dependency resolution never hits the network."
    )


def test_project_compiles():
    result = _run_mix(["compile"])
    assert result.returncode == 0, (
        "`mix compile` failed in the scaffold project:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_meter_resource_is_usable():
    script = (
        'meter = Ash.create!(Ingest.Pipeline.Meter, %{code: "PROBE", scale_bp: 11_000, active: true});'
        'true = meter.scale_bp == 11_000;'
        'true = Ingest.Pipeline.Meter in Ash.Domain.Info.resources(Ingest.Pipeline);'
        'true = Ash.Resource.Info.data_layer(Ingest.Pipeline.Meter) == Ash.DataLayer.Ets;'
        'IO.puts("METER_OK")'
    )
    result = _run_mix(["run", "-e", script])
    assert result.returncode == 0 and "METER_OK" in result.stdout, (
        "The provided Ingest.Pipeline.Meter resource is not usable:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_ash_version_is_3_31_0():
    script = (
        '{:ok, vsn} = :application.get_key(:ash, :vsn);'
        'IO.puts("ASH_VSN " <> List.to_string(vsn))'
    )
    result = _run_mix(["run", "-e", script])
    assert result.returncode == 0, (
        f"Could not determine the compiled Ash version:\nSTDERR:\n{result.stderr}"
    )
    assert "ASH_VSN 3.31.0" in result.stdout, (
        f"Expected Ash 3.31.0 to be compiled into the project, got: {result.stdout.strip()}"
    )


def test_solution_modules_are_not_present_yet():
    script = (
        "mods = [Ingest.Pipeline.Reading, Ingest.Pipeline.MeterRollup, "
        "Ingest.Pipeline.Ingestion, Ingest.Pipeline.Store];"
        "missing = Enum.reject(mods, &Code.ensure_loaded?/1);"
        'IO.puts("MISSING " <> Enum.map_join(missing, ",", &inspect/1))'
    )
    result = _run_mix(["run", "-e", script])
    assert result.returncode == 0, (
        f"Could not inspect the scaffold modules:\nSTDERR:\n{result.stderr}"
    )
    for module in (
        "Ingest.Pipeline.Reading",
        "Ingest.Pipeline.MeterRollup",
        "Ingest.Pipeline.Ingestion",
        "Ingest.Pipeline.Store",
    ):
        assert module in result.stdout, (
            f"{module} already exists in the scaffold; the task must start unsolved."
        )
