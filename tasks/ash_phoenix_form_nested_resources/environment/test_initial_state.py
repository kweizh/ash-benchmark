import os
import shutil
import subprocess

PROJECT_DIR = "/home/user/catering"
FORMS_FILE = os.path.join(PROJECT_DIR, "lib", "catering", "forms.ex")

RESOURCE_FILES = [
    "lib/catering/orders.ex",
    "lib/catering/orders/order.ex",
    "lib/catering/orders/line_item.ex",
    "lib/catering/orders/modifier.ex",
    "lib/catering/orders/customer.ex",
    "lib/catering/orders/delivery_window.ex",
    "lib/catering/orders/fulfillment.ex",
]


def _run(args, cwd=PROJECT_DIR, timeout=600):
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_elixir_toolchain_available():
    assert shutil.which("elixir") is not None, "elixir was not found in PATH."
    assert shutil.which("mix") is not None, "mix was not found in PATH."


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_mix_project_files_exist():
    for name in ("mix.exs", "mix.lock", "config/config.exs"):
        path = os.path.join(PROJECT_DIR, name)
        assert os.path.isfile(path), f"Expected {path} to exist in the scaffold."


def test_domain_and_resource_files_exist():
    for rel in RESOURCE_FILES:
        path = os.path.join(PROJECT_DIR, rel)
        assert os.path.isfile(path), f"Expected pre-existing resource file {path}."


def test_forms_stub_file_exists():
    assert os.path.isfile(FORMS_FILE), (
        f"Expected the stub module file {FORMS_FILE} to exist in the scaffold."
    )


def test_dependencies_are_pinned_to_the_required_versions():
    lock_path = os.path.join(PROJECT_DIR, "mix.lock")
    with open(lock_path) as handle:
        lock = handle.read()

    assert '"ash": {:hex, :ash, "3.31.0"' in lock, (
        "mix.lock does not pin ash to 3.31.0."
    )
    assert '"ash_phoenix": {:hex, :ash_phoenix, "2.3.24"' in lock, (
        "mix.lock does not pin ash_phoenix to 2.3.24."
    )


def test_dependencies_are_vendored_for_offline_use():
    for dep in ("ash", "ash_phoenix", "phoenix_html", "spark"):
        path = os.path.join(PROJECT_DIR, "deps", dep)
        assert os.path.isdir(path), (
            f"Dependency {dep} is not vendored at {path}; the environment must work offline."
        )


def test_project_compiles_without_network_access():
    result = _run(["mix", "compile"])
    assert result.returncode == 0, (
        "`mix compile` failed in the scaffold:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_domain_resources_are_available_at_runtime():
    script = (
        "IO.puts(inspect(Ash.Resource.Info.attribute(Catering.Orders.Order, :reference).name)); "
        "IO.puts(inspect(Ash.Resource.Info.action(Catering.Orders.Order, :place).type)); "
        "IO.puts(inspect(Ash.Resource.Info.action(Catering.Orders.Order, :revise).type)); "
        "IO.puts(inspect(Ash.Resource.Info.attribute(Catering.Orders.LineItem, :position).name)); "
        "IO.puts(inspect(Ash.Resource.Info.attribute(Catering.Orders.Modifier, :position).name)); "
        "IO.puts(inspect(Ash.Resource.Info.attribute(Catering.Orders.Customer, :email).name))"
    )
    result = _run(["mix", "run", "-e", script])
    assert result.returncode == 0, (
        "Could not introspect the pre-existing Ash resources:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    for expected in (":reference", ":create", ":update", ":position", ":email"):
        assert expected in result.stdout, (
            f"Expected {expected} in the resource introspection output, got:\n{result.stdout}"
        )


def test_ash_phoenix_form_module_is_loadable():
    result = _run(
        ["mix", "run", "-e", "IO.puts(inspect(Code.ensure_loaded?(AshPhoenix.Form)))"]
    )
    assert result.returncode == 0, (
        f"`mix run` failed while loading AshPhoenix.Form:\n{result.stdout}\n{result.stderr}"
    )
    assert "true" in result.stdout, (
        f"AshPhoenix.Form is not loadable in the scaffold, got:\n{result.stdout}"
    )


def test_forms_facade_is_not_implemented_yet():
    script = (
        "funs = [new_order_form: 0, edit_order_form: 1, to_phoenix_form: 1, change: 2, change: 3, "
        "add_nested: 2, add_nested: 3, remove_nested: 2, reorder: 3, move: 3, submitted_params: 1, "
        "hidden_inputs: 2, error_map: 1, raw_error_list: 2, serialize: 1, save: 2]\n"
        "Code.ensure_loaded?(Catering.Forms)\n"
        "missing = Enum.reject(funs, fn {f, a} -> function_exported?(Catering.Forms, f, a) end)\n"
        "IO.puts(\"MISSING=\" <> inspect(missing))\n"
        "outcome =\n"
        "  try do\n"
        "    Catering.Forms.new_order_form()\n"
        "    :returned\n"
        "  rescue\n"
        "    _ -> :raised\n"
        "  end\n"
        "IO.puts(\"OUTCOME=\" <> inspect(outcome))"
    )
    result = _run(["mix", "run", "-e", script])
    assert result.returncode == 0, (
        f"`mix run` failed while probing Catering.Forms:\n{result.stdout}\n{result.stderr}"
    )
    assert "OUTCOME=:raised" in result.stdout, (
        "Catering.Forms.new_order_form/0 already returns a value; the task appears to be "
        f"pre-solved. Output:\n{result.stdout}"
    )
