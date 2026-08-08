"""Initial-state verification for the Ash cart pricing calculation engine task.

These checks run BEFORE the executor starts working. They assert that the
offline Elixir/Ash scaffold is present and buildable, and that none of the
modules the executor must author already exist.
"""

import os
import re
import shutil
import subprocess

PROJECT_DIR = "/home/user/cart_pricing"
MIX_EXS = os.path.join(PROJECT_DIR, "mix.exs")
MIX_LOCK = os.path.join(PROJECT_DIR, "mix.lock")

SOLUTION_FILES = [
    "lib/cart_pricing/sales.ex",
    "lib/cart_pricing/sales/cart.ex",
    "lib/cart_pricing/sales/cart_item.ex",
    "lib/cart_pricing/sales/coupon.ex",
    "lib/cart_pricing/sales/calculations/discounted_line_total.ex",
    "lib/cart_pricing/sales/calculations/cart_quote.ex",
]

SOLUTION_MODULES = [
    "CartPricing.Sales",
    "CartPricing.Sales.Cart",
    "CartPricing.Sales.CartItem",
    "CartPricing.Sales.Coupon",
    "CartPricing.Sales.Calculations.DiscountedLineTotal",
    "CartPricing.Sales.Calculations.CartQuote",
]


def _run(args: list[str], cwd: str = PROJECT_DIR, timeout: int = 900):
    env = dict(os.environ)
    env.setdefault("MIX_HOME", "/opt/mix")
    env.setdefault("HEX_HOME", "/opt/hex")
    env["HEX_OFFLINE"] = "1"
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_elixir_toolchain_available():
    assert shutil.which("elixir") is not None, "elixir was not found in PATH."
    assert shutil.which("mix") is not None, "mix was not found in PATH."
    assert shutil.which("erl") is not None, "erl (Erlang/OTP) was not found in PATH."


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_mix_project_files_exist():
    for rel in ["mix.exs", "mix.lock", "config/config.exs", "lib/cart_pricing.ex", "test/test_helper.exs"]:
        path = os.path.join(PROJECT_DIR, rel)
        assert os.path.isfile(path), f"Expected scaffold file {path} to exist."


def test_mix_project_declares_cart_pricing_app():
    with open(MIX_EXS, encoding="utf-8") as handle:
        content = handle.read()
    assert "app: :cart_pricing" in content, "mix.exs does not declare the :cart_pricing OTP application."


def test_ash_v3_is_locked_and_vendored():
    with open(MIX_LOCK, encoding="utf-8") as handle:
        lock = handle.read()
    match = re.search(r'"ash":\s*\{:hex,\s*:ash,\s*"(\d+)\.(\d+)\.(\d+)', lock)
    assert match is not None, "mix.lock does not pin the :ash dependency."
    assert match.group(1) == "3", f"Expected Ash major version 3, found {match.group(0)}."
    assert os.path.isdir(os.path.join(PROJECT_DIR, "deps", "ash")), (
        "The ash dependency source is not vendored under deps/ash."
    )


def test_dependencies_are_precompiled_for_dev_and_test():
    for mix_env in ["dev", "test"]:
        ebin = os.path.join(PROJECT_DIR, "_build", mix_env, "lib", "ash", "ebin")
        assert os.path.isdir(ebin), (
            f"Ash is not precompiled for MIX_ENV={mix_env} (missing {ebin})."
        )


def test_project_compiles_offline():
    result = _run(["mix", "compile"])
    assert result.returncode == 0, (
        f"'mix compile' failed in the scaffold.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_test_env_compiles_offline():
    env_result = subprocess.run(
        ["mix", "compile"],
        cwd=PROJECT_DIR,
        env={**os.environ, "MIX_ENV": "test", "HEX_OFFLINE": "1"},
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert env_result.returncode == 0, (
        "'MIX_ENV=test mix compile' failed in the scaffold.\n"
        f"stdout:\n{env_result.stdout}\nstderr:\n{env_result.stderr}"
    )


def test_solution_files_are_absent():
    for rel in SOLUTION_FILES:
        path = os.path.join(PROJECT_DIR, rel)
        assert not os.path.exists(path), (
            f"{path} already exists; the executor is expected to create it."
        )


def test_solution_modules_are_not_defined():
    snippet = (
        "defined = Enum.filter(["
        + ", ".join(SOLUTION_MODULES)
        + "], &Code.ensure_loaded?/1); "
        + 'IO.puts("MODULE_PROBE:" <> Enum.map_join(defined, ",", &inspect/1))'
    )
    result = _run(["mix", "run", "--no-start", "-e", snippet])
    assert result.returncode == 0, (
        f"Failed to inspect module availability.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    probe = re.search(r"^MODULE_PROBE:(.*)$", result.stdout, re.MULTILINE)
    assert probe is not None, (
        f"Module probe produced no output.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    already_defined = probe.group(1).strip()
    assert already_defined == "", (
        f"These modules are already defined in the scaffold: {already_defined}"
    )


def test_no_verification_suite_is_preinstalled():
    verification_dir = os.path.join(PROJECT_DIR, "test", "verification")
    assert not os.path.exists(verification_dir), (
        f"{verification_dir} must not exist before evaluation."
    )
