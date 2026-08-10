import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/sla_lab"

ELIXIR_TIMEOUT = 300


def run_elixir(code: str) -> subprocess.CompletedProcess:
    """Run a snippet of Elixir inside the project with `mix run -e`."""
    env = dict(os.environ)
    env.setdefault("MIX_ENV", "dev")
    return subprocess.run(
        ["mix", "run", "--no-compile", "-e", code],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=ELIXIR_TIMEOUT,
        env=env,
    )


def test_elixir_toolchain_available():
    assert shutil.which("elixir") is not None, "elixir binary not found in PATH."
    assert shutil.which("mix") is not None, "mix binary not found in PATH."


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_project_files_exist():
    expected = [
        "mix.exs",
        "mix.lock",
        "config/config.exs",
        "lib/sla_lab/ops.ex",
        "lib/sla_lab/ops/carrier.ex",
        "lib/sla_lab/ops/shipment.ex",
        "lib/sla_lab/ops/seed.ex",
    ]
    for relative in expected:
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected project file {path} does not exist."


def test_ash_dependency_is_pinned_and_prefetched():
    lock_path = os.path.join(PROJECT_DIR, "mix.lock")
    with open(lock_path) as handle:
        lock = handle.read()
    assert '"ash"' in lock, "mix.lock does not pin the ash dependency."
    assert "3.31.0" in lock, "mix.lock does not pin ash 3.31.0."
    assert os.path.isdir(os.path.join(PROJECT_DIR, "deps", "ash")), \
        "The ash dependency source was not pre-fetched into deps/."
    assert os.path.isdir(os.path.join(PROJECT_DIR, "_build", "dev", "lib", "ash")), \
        "The ash dependency was not pre-compiled for the dev environment."


def test_project_compiles_and_ash_version_matches():
    result = run_elixir(
        'IO.puts("ASH_VERSION=" <> to_string(Application.spec(:ash, :vsn)))'
    )
    assert result.returncode == 0, (
        "`mix run` failed in the scaffold project:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "ASH_VERSION=3.31.0" in result.stdout, (
        f"Expected ash 3.31.0 to be loaded, got:\n{result.stdout}\n{result.stderr}"
    )


def test_resources_are_registered_with_the_domain():
    result = run_elixir(
        'IO.inspect(Enum.sort(Ash.Domain.Info.resources(SlaLab.Ops)))'
    )
    assert result.returncode == 0, (
        f"Could not introspect SlaLab.Ops:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "SlaLab.Ops.Carrier" in result.stdout, "SlaLab.Ops.Carrier is not part of the domain."
    assert "SlaLab.Ops.Shipment" in result.stdout, "SlaLab.Ops.Shipment is not part of the domain."


def test_shipment_attributes_are_present():
    result = run_elixir(
        'IO.inspect(Enum.sort(Enum.map(Ash.Resource.Info.attributes(SlaLab.Ops.Shipment), & &1.name)))'
    )
    assert result.returncode == 0, (
        f"Could not introspect the Shipment resource:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    for attribute in [
        ":reference",
        ":origin_zone",
        ":destination_zone",
        ":promised_hours",
        ":actual_hours",
        ":priority",
    ]:
        assert attribute in result.stdout, (
            f"Expected attribute {attribute} on SlaLab.Ops.Shipment, got:\n{result.stdout}"
        )


def test_seed_fixture_module_works():
    result = run_elixir(
        'seeded = SlaLab.Ops.Seed.seed!(); '
        'IO.puts("CARRIERS=" <> to_string(map_size(seeded.carriers))); '
        'IO.puts("SHIPMENTS=" <> to_string(map_size(seeded.shipments)))'
    )
    assert result.returncode == 0, (
        f"SlaLab.Ops.Seed.seed!/0 failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "CARRIERS=3" in result.stdout, f"Expected 3 seeded carriers, got:\n{result.stdout}"
    assert "SHIPMENTS=10" in result.stdout, f"Expected 10 seeded shipments, got:\n{result.stdout}"


def test_custom_expressions_are_not_registered_yet():
    config_path = os.path.join(PROJECT_DIR, "config", "config.exs")
    with open(config_path) as handle:
        config = handle.read()
    assert "custom_expressions" not in config, (
        "config/config.exs already registers custom expressions; the task has already been solved."
    )

    result = run_elixir(
        'IO.puts("ROUTE_KEY=" <> inspect(Ash.Filter.custom_expression(:route_key, ["a", "b"]))); '
        'IO.puts("RATIO_BPS=" <> inspect(Ash.Filter.custom_expression(:ratio_bps, [1, 2])))'
    )
    assert result.returncode == 0, (
        f"Could not query the custom expression registry:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "ROUTE_KEY=nil" in result.stdout, (
        f"route_key is already a registered custom expression:\n{result.stdout}"
    )
    assert "RATIO_BPS=nil" in result.stdout, (
        f"ratio_bps is already a registered custom expression:\n{result.stdout}"
    )


def test_solution_modules_do_not_exist_yet():
    for relative in [
        "lib/sla_lab/expressions/route_key.ex",
        "lib/sla_lab/expressions/ratio_bps.ex",
        "lib/sla_lab/expressions/penalty_points.ex",
        "lib/sla_lab/ops/validations/ratio_within.ex",
    ]:
        path = os.path.join(PROJECT_DIR, relative)
        assert not os.path.exists(path), f"{path} already exists; the task has already been solved."


def test_shipment_has_no_expression_calculations_yet():
    result = run_elixir(
        'IO.inspect(Enum.map(Ash.Resource.Info.calculations(SlaLab.Ops.Shipment), & &1.name)); '
        'IO.puts("ON_ROUTE=" <> inspect(Ash.Resource.Info.action(SlaLab.Ops.Shipment, :on_route)))'
    )
    assert result.returncode == 0, (
        f"Could not introspect the Shipment resource:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert ":sla_ratio_bps" not in result.stdout, (
        "The :sla_ratio_bps calculation already exists; the task has already been solved."
    )
    assert "ON_ROUTE=nil" in result.stdout, (
        "The :on_route read action already exists; the task has already been solved."
    )


def test_carrier_has_no_aggregates_yet():
    result = run_elixir(
        'IO.inspect(Enum.map(Ash.Resource.Info.aggregates(SlaLab.Ops.Carrier), & &1.name))'
    )
    assert result.returncode == 0, (
        f"Could not introspect the Carrier resource:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert ":breach_count" not in result.stdout, (
        "The :breach_count aggregate already exists; the task has already been solved."
    )
