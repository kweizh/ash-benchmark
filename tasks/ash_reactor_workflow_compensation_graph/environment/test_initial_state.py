import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/orchestra"


def _run(args, cwd=None, timeout=600):
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
            f"`{binary}` was not found in PATH; the Elixir/OTP toolchain is missing."
        )


def test_elixir_version_is_pinned():
    result = _run(["elixir", "--version"])
    assert result.returncode == 0, (
        f"`elixir --version` failed with exit code {result.returncode}: {result.stderr}"
    )
    assert "1.18.4" in result.stdout, (
        f"Expected Elixir 1.18.4 to be installed, got:\n{result.stdout}"
    )


def test_otp_version_is_pinned():
    otp_release_file = "/opt/otp/releases/27/OTP_VERSION"
    assert os.path.isfile(otp_release_file), (
        f"Expected the pinned OTP release file {otp_release_file} to exist."
    )
    with open(otp_release_file) as handle:
        version = handle.read().strip()
    assert version.startswith("27.3.4"), (
        f"Expected OTP 27.3.4 to be installed, got {version!r}."
    )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"The mix project directory {PROJECT_DIR} does not exist."
    )


def test_mix_project_files_exist():
    for relative in ("mix.exs", "mix.lock", "config/config.exs"):
        path = os.path.join(PROJECT_DIR, relative)
        assert os.path.isfile(path), f"Expected {path} to be part of the scaffold."


def test_application_module_is_present():
    path = os.path.join(PROJECT_DIR, "lib", "orchestra", "application.ex")
    assert os.path.isfile(path), (
        f"Expected the pre-existing application module {path} to be part of the scaffold."
    )


def test_ash_domains_are_configured():
    path = os.path.join(PROJECT_DIR, "config", "config.exs")
    with open(path) as handle:
        content = handle.read()
    assert "ash_domains" in content and "Orchestra.Fleet" in content, (
        "config/config.exs is expected to declare "
        "`config :orchestra, ash_domains: [Orchestra.Fleet]`."
    )


def test_dependencies_are_pinned_and_vendored():
    with open(os.path.join(PROJECT_DIR, "mix.exs")) as handle:
        mix_exs = handle.read()
    assert ":ash" in mix_exs, "mix.exs is expected to declare the `ash` dependency."
    assert ":reactor" in mix_exs, "mix.exs is expected to declare the `reactor` dependency."

    for dependency in ("ash", "reactor", "spark", "ets"):
        path = os.path.join(PROJECT_DIR, "deps", dependency)
        assert os.path.isdir(path), (
            f"Expected the dependency {dependency} to be vendored at {path} "
            "so the project builds without network access."
        )


def test_ash_version_is_pinned():
    with open(os.path.join(PROJECT_DIR, "mix.lock")) as handle:
        lock = handle.read()
    assert '"3.31.0"' in lock, "mix.lock is expected to pin ash 3.31.0."


def test_dependencies_are_precompiled():
    for app in ("ash", "reactor"):
        path = os.path.join(PROJECT_DIR, "_build", "dev", "lib", app, "ebin")
        assert os.path.isdir(path), (
            f"Expected {app} to be pre-compiled for the dev environment at {path}."
        )


def test_hex_is_offline():
    assert os.environ.get("HEX_OFFLINE") == "1", (
        "HEX_OFFLINE must be set to 1 so that no dependency resolution hits the network."
    )


def test_project_compiles_offline():
    result = _run(["mix", "compile"], cwd=PROJECT_DIR)
    assert result.returncode == 0, (
        "`mix compile` failed on the untouched scaffold:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_solution_modules_are_not_present_yet():
    lib_dir = os.path.join(PROJECT_DIR, "lib")
    existing = []
    for root, _dirs, files in os.walk(lib_dir):
        for name in files:
            if name.endswith(".ex"):
                existing.append(os.path.relpath(os.path.join(root, name), lib_dir))
    assert existing == ["orchestra/application.ex"], (
        "The scaffold must only ship lib/orchestra/application.ex; "
        f"found: {sorted(existing)}"
    )


def test_domain_module_is_not_implemented_yet():
    script = (
        'IO.puts(if Code.ensure_loaded?(Orchestra.Fleet), do: "loaded", else: "missing")'
    )
    result = _run(["elixir", "-e", script], cwd=PROJECT_DIR)
    assert result.returncode == 0, (
        f"Failed to probe for the domain module: {result.stderr}"
    )
    assert "missing" in result.stdout, (
        "Orchestra.Fleet must not exist before the task is solved."
    )
