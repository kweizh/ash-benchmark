"""Initial-state checks for the ash_json_api_resource_router task.

These run BEFORE the executor starts working. They assert that the pre-built
Elixir/Ash project is present and offline-ready, and that the JSON:API layer the
executor must build does not exist yet.
"""

import os
import re
import shutil
import subprocess

PROJECT_DIR = "/home/user/kbapi"
LIB_DIR = os.path.join(PROJECT_DIR, "lib")
KNOWLEDGE_DIR = os.path.join(LIB_DIR, "kbapi", "knowledge")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def test_elixir_toolchain_available():
    for binary in ("elixir", "mix", "erl"):
        assert shutil.which(binary) is not None, (
            f"{binary} was not found in PATH; the Elixir/OTP toolchain is missing."
        )


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."
    assert os.path.isfile(os.path.join(PROJECT_DIR, "mix.exs")), (
        f"{PROJECT_DIR}/mix.exs is missing."
    )
    assert os.path.isfile(os.path.join(PROJECT_DIR, "mix.lock")), (
        f"{PROJECT_DIR}/mix.lock is missing; dependencies are not pinned."
    )
    assert os.path.isfile(os.path.join(PROJECT_DIR, "config", "config.exs")), (
        f"{PROJECT_DIR}/config/config.exs is missing."
    )


def test_required_dependencies_are_vendored():
    for dep in ("ash", "ash_json_api", "plug", "open_api_spex", "jason", "simple_sat"):
        dep_dir = os.path.join(PROJECT_DIR, "deps", dep)
        assert os.path.isdir(dep_dir), (
            f"Dependency {dep} is not vendored at {dep_dir}; the image is not offline-ready."
        )


def test_dependencies_are_precompiled():
    build_dir = os.path.join(PROJECT_DIR, "_build", "dev", "lib")
    assert os.path.isdir(build_dir), f"{build_dir} does not exist; dependencies are not compiled."
    for dep in ("ash", "ash_json_api", "plug"):
        assert os.path.isdir(os.path.join(build_dir, dep)), (
            f"Dependency {dep} is not compiled into {build_dir}."
        )


def test_mix_exs_declares_ash_json_api():
    content = _read(os.path.join(PROJECT_DIR, "mix.exs"))
    assert ":ash_json_api" in content, "mix.exs does not declare the :ash_json_api dependency."
    assert ":plug" in content, "mix.exs does not declare the :plug dependency."
    assert ":open_api_spex" in content, "mix.exs does not declare the :open_api_spex dependency."


def test_domain_and_resources_exist():
    expected = [
        os.path.join(LIB_DIR, "kbapi", "knowledge.ex"),
        os.path.join(KNOWLEDGE_DIR, "author.ex"),
        os.path.join(KNOWLEDGE_DIR, "article.ex"),
        os.path.join(KNOWLEDGE_DIR, "tag.ex"),
        os.path.join(KNOWLEDGE_DIR, "article_tag.ex"),
        os.path.join(KNOWLEDGE_DIR, "comment.ex"),
        os.path.join(KNOWLEDGE_DIR, "fixtures.ex"),
    ]
    for path in expected:
        assert os.path.isfile(path), f"Expected pre-existing source file {path} is missing."


def test_fixtures_module_exposes_the_documented_helpers():
    content = _read(os.path.join(KNOWLEDGE_DIR, "fixtures.ex"))
    for fragment in (
        "def reset!",
        "def author_id(",
        "def article_id(",
        "def tag_id(",
        "def comment_id(",
    ):
        assert fragment in content, f"Fixtures module does not define `{fragment}`."


def test_resources_use_the_private_ets_data_layer():
    for name in ("author.ex", "article.ex", "tag.ex", "comment.ex"):
        content = _read(os.path.join(KNOWLEDGE_DIR, name))
        assert "Ash.DataLayer.Ets" in content, f"{name} does not use the ETS data layer."
        assert "private? true" in content, f"{name} does not use a private ETS table."


def test_json_api_layer_is_not_implemented_yet():
    api_dir = os.path.join(LIB_DIR, "kbapi", "api")
    assert not os.path.exists(os.path.join(api_dir, "router.ex")), (
        "lib/kbapi/api/router.ex already exists; the JSON:API layer must not be pre-built."
    )
    assert not os.path.exists(os.path.join(api_dir, "endpoint.ex")), (
        "lib/kbapi/api/endpoint.ex already exists; the JSON:API layer must not be pre-built."
    )

    for root, _dirs, files in os.walk(LIB_DIR):
        for name in files:
            if not name.endswith(".ex"):
                continue
            content = _read(os.path.join(root, name))
            assert "AshJsonApi" not in content, (
                f"{os.path.join(root, name)} already references AshJsonApi; "
                "the JSON:API layer must not be pre-built."
            )
            assert "Ash.Policy.Authorizer" not in content, (
                f"{os.path.join(root, name)} already installs Ash.Policy.Authorizer; "
                "authorization must not be pre-built."
            )


def test_no_extra_actions_are_predefined():
    article = _read(os.path.join(KNOWLEDGE_DIR, "article.ex"))
    for name in ("publish", "reindex", "tally", "feed"):
        assert re.search(rf":{name}\b", article) is None, (
            f"Article resource already defines :{name}; it must be added by the executor."
        )

    comment = _read(os.path.join(KNOWLEDGE_DIR, "comment.ex"))
    for name in ("pending", "approve"):
        assert re.search(rf":{name}\b", comment) is None, (
            f"Comment resource already defines :{name}; it must be added by the executor."
        )


def test_project_compiles_offline():
    env = dict(os.environ)
    env["MIX_ENV"] = "dev"
    result = subprocess.run(
        ["mix", "compile", "--no-deps-check"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    assert result.returncode == 0, (
        "The pre-existing project does not compile:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
