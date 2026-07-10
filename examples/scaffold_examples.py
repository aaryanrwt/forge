"""Scaffold 20 developer workflow examples with structured JSON configs."""
from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = {
    "fix_python_bug": {
        "goal": "Detect syntax errors in python code and apply fix",
        "description": "Scans workspace files, runs pytest, captures the syntax/assertion traceback, and applies code edit",
        "tasks": ["scan_files", "run_tests", "apply_code_edit", "verify_zero_exit_code"]
    },
    "generate_fastapi": {
        "goal": "Generate a new FastAPI CRUD service",
        "description": "Generates router endpoints, initializes Pydantic request models, compiles and tests accessibility",
        "tasks": ["write_pydantic_models", "write_routers", "verify_compilation", "test_http_get"]
    },
    "create_dockerfile": {
        "goal": "Build Dockerfile for application sandbox",
        "description": "Analyzes dependencies, writes Dockerfile configuration, executes docker build and runs container check",
        "tasks": ["generate_dockerfile", "docker_build", "docker_run_smoke_test"]
    },
    "refactor_repository": {
        "goal": "Update packages imports and export classes",
        "description": "Adjusts import statements across folders after modifying module structure",
        "tasks": ["find_imports", "replace_import_paths", "run_tests"]
    },
    "migrate_sqlite": {
        "goal": "Run SQLite table migrations and schema updates",
        "description": "Applies DDL schema scripts to update column counts, inserts dummy rows and checks counts",
        "tasks": ["run_ddl_migrations", "verify_sqlite_columns"]
    },
    "generate_readme": {
        "goal": "Auto-document package files inside README",
        "description": "Inspects src/ class definitions and automatically writes a markdown guide",
        "tasks": ["read_source_files", "generate_markdown_readme"]
    },
    "review_pull_request": {
        "goal": "Analyze PR changes for code style guide compliance",
        "description": "Compares git diff and inspects for compliance with styling parameters",
        "tasks": ["git_diff_main", "verify_style_guide"]
    },
    "analyze_logs": {
        "goal": "Scan logs to trace system exceptions",
        "description": "Parses error logs, extracts traceback strings and identifies failed execution keys",
        "tasks": ["read_logs", "extract_traceback", "write_incident_report"]
    },
    "generate_tests": {
        "goal": "Create unit tests to match target coverage",
        "description": "Analyzes file definitions and generates missing pytest test files",
        "tasks": ["read_source_code", "generate_pytest_unit_tests"]
    },
    "convert_flask_to_fastapi": {
        "goal": "Modernize Python backend code from Flask to FastAPI",
        "description": "Rewrites Flask route decorators and request variables to FastAPI routers",
        "tasks": ["read_flask_app", "rewrite_fastapi_endpoints"]
    },
    "convert_django_to_fastapi": {
        "goal": "Migrate Django models to Pydantic and Tortoise ORM",
        "description": "Transforms Django database fields into Pydantic models",
        "tasks": ["read_django_models", "generate_pydantic_schemas"]
    },
    "git_automation": {
        "goal": "Clone repo, run status, checkout branch and commit changes",
        "description": "Automates standard developer git version control operations",
        "tasks": ["git_clone", "git_checkout_branch", "git_commit_changes"]
    },
    "ci_generator": {
        "goal": "Build GitHub Actions CI workflow script",
        "description": "Creates a YAML script inside .github/workflows for automated lint/test execution",
        "tasks": ["generate_github_actions_yaml", "verify_yaml_syntax"]
    },
    "code_migration": {
        "goal": "Upgrade Python 3.8 typing to Python 3.11+",
        "description": "Converts typing.List and typing.Dict to generic list and dict types",
        "tasks": ["scan_typing_syntax", "convert_to_generic_types"]
    },
    "terraform_validation": {
        "goal": "Run terraform validation and safety checks",
        "description": "Executes terraform init and validate to check infrastructure syntax",
        "tasks": ["terraform_init", "terraform_validate"]
    },
    "kubernetes_yaml_linter": {
        "goal": "Lints Kubernetes manifests for security metrics",
        "description": "Runs checks on deployment manifests to ensure no runAsUser root properties",
        "tasks": ["read_k8s_yaml", "verify_security_rules"]
    },
    "github_issue_resolver": {
        "goal": "Locate and resolve simple bug issues",
        "description": "Reads issue text, scans related files, applies fix and verifies",
        "tasks": ["read_issue_body", "scan_related_source", "apply_code_edit"]
    },
    "rest_api_scanner": {
        "goal": "Probe running API ports for security vulnerabilities",
        "description": "Performs TCP scans on local ports to ensure no open admin endpoints",
        "tasks": ["scan_ports", "verify_admin_restrictions"]
    },
    "cli_generator": {
        "goal": "Generate Typer CLI parameters for a script",
        "description": "Scaffolds a CLI wrapper around an existing core function module",
        "tasks": ["generate_typer_cli", "verify_cli_help_flag"]
    },
    "json_validator": {
        "goal": "Validate JSON payloads against schema rules",
        "description": "Checks structured JSON files against a schema payload",
        "tasks": ["read_json_payload", "verify_json_schema"]
    }
}


def scaffold_all() -> None:
    examples_dir = Path("./examples")
    examples_dir.mkdir(exist_ok=True)
    
    for name, data in EXAMPLES.items():
        dir_path = examples_dir / name
        dir_path.mkdir(exist_ok=True)
        
        # Write workflow.json
        with open(dir_path / "workflow.json", "w") as f:
            json.dump(data, f, indent=2)
            
    print(f"Successfully scaffolded {len(EXAMPLES)} developer workflow examples under /examples!")


if __name__ == "__main__":
    scaffold_all()
