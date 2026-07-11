"""Integration tests for the Typer CLI commands."""

from __future__ import annotations

import os

from typer.testing import CliRunner

from forge.cli.main import app

runner = CliRunner()


def test_cli_config_command() -> None:
    res = runner.invoke(app, ["config"])
    assert res.exit_code == 0
    assert "Database URL" in res.stdout
    assert "LLM Provider" in res.stdout


def test_cli_doctor_command() -> None:
    res = runner.invoke(app, ["doctor", "--system"])
    assert res.exit_code == 0
    assert "Forge Diagnostic Checkup" in res.stdout
    assert "System Info" in res.stdout
    assert "Database & Config" in res.stdout
    assert "LLM Provider Connectivity" in res.stdout
    assert "Path Executables" in res.stdout
    assert "Plugins Sandbox" in res.stdout


def test_cli_run_goal_command() -> None:
    # Running a simple echo command
    res = runner.invoke(app, ["run", "echo hello"])
    assert res.exit_code == 0
    assert "Goal execution run completed" in res.stdout


def test_cli_plugin_subcommands() -> None:
    # List plugins
    res_list = runner.invoke(app, ["plugin", "list"])
    assert res_list.exit_code == 0

    # Scaffold plugin
    # Output to a temporary directory in workspace
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        res_create = runner.invoke(
            app, ["plugin", "create", "test-scaffold", "--output-dir", tmpdir]
        )
        assert res_create.exit_code == 0
        assert "Scaffolded plugin 'test-scaffold'" in res_create.stdout
        assert os.path.exists(os.path.join(tmpdir, "test-scaffold", "forge_plugin.json"))
