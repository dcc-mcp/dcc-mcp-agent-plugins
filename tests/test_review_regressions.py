"""Regression tests for the independent PR #8 review findings."""

from __future__ import annotations

import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent

from scripts import product_discovery
from scripts.build_geo_site import _llms_txt, build
from scripts.distribution import build_catalog


class IndependentReviewRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = product_discovery.load_product_catalog()

    def _workflow_texts(self) -> dict[str, str]:
        return {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in product_discovery.RELEASED_CORE_WORKFLOW_JOBS
        }

    def _setup_command(self) -> str:
        return product_discovery.RELEASED_CORE_WORKFLOW_COMMANDS[
            ".github/workflows/ci.yml"
        ]["validate"]

    def _assert_workflow_replacement_rejected(
        self,
        relative: str,
        before: str,
        after: str,
    ) -> None:
        workflows = self._workflow_texts()
        mutated = dict(workflows)
        mutated[relative] = mutated[relative].replace(before, after, 1)
        self.assertNotEqual(workflows[relative], mutated[relative])
        with self.assertRaises(ValueError):
            product_discovery.validate_released_core_workflows(self.catalog, mutated)

    def test_required_ci_and_release_check_the_exact_released_cli(self) -> None:
        source = self.catalog["sources"]["released_cli"]
        self.assertEqual("https://github.com/dcc-mcp/dcc-mcp-core", source["repository"])
        self.assertEqual(f"v{source['version']}", source["tag"])
        self.assertEqual(
            "e8d070fd703164a380895af2d6b4e17b3cb2459c",
            source["commit"],
        )
        self.assertEqual(
            source["commit"],
            self.catalog["sources"]["core_catalog"]["commit"],
        )

        setup = "python scripts/setup_released_core.py"
        install = "--with-catalog-dependencies --ensure-cli-dir .released-cli"
        command = "--check --check-core-catalog --check-cli --cli"
        for relative in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(setup, workflow)
                self.assertIn(install, workflow)
                self.assertIn(command, workflow)
                self.assertNotIn("dcc-mcp-core==", workflow)

    def test_every_core_dependent_workflow_uses_one_released_contract(self) -> None:
        workflows = {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                ".github/workflows/ci.yml",
                ".github/workflows/clawhub.yml",
                ".github/workflows/release.yml",
            )
        }
        checker = getattr(product_discovery, "validate_released_core_workflows", None)
        self.assertIsNotNone(checker, "workflow Core pins need one fail-closed validator")
        checker(self.catalog, workflows)
        for commands in product_discovery.RELEASED_CORE_WORKFLOW_COMMANDS.values():
            for command in commands.values():
                self.assertIn("--with-catalog-dependencies", command)

        conflicting_version = dict(workflows)
        conflicting_version[".github/workflows/ci.yml"] += (
            '\nDCC_MCP_CORE_VERSION: "0.20.8"\n'
        )
        with self.assertRaises(ValueError):
            checker(self.catalog, conflicting_version)

        conflicting_commit = dict(workflows)
        wrong_commit = "f" * 40
        conflicting_commit[".github/workflows/release.yml"] += (
            f'\nDCC_MCP_CORE_COMMIT: "{wrong_commit}"\n'
        )
        with self.assertRaises(ValueError):
            checker(self.catalog, conflicting_commit)

    def test_workflow_core_setup_must_be_an_executable_unconditional_step(self) -> None:
        workflows = {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in product_discovery.RELEASED_CORE_WORKFLOW_JOBS
        }
        checker = product_discovery.validate_released_core_workflows
        setup_command = product_discovery.RELEASED_CORE_WORKFLOW_COMMANDS[
            ".github/workflows/ci.yml"
        ]["validate"]
        setup_step = f"      - run: {setup_command}\n"

        reviewer_counterexample = dict(workflows)
        reviewer_counterexample[".github/workflows/ci.yml"] = reviewer_counterexample[
            ".github/workflows/ci.yml"
        ].replace(
            setup_step,
            "      - run: |\n"
            "          # python scripts/setup_released_core.py\n"
            "          python -m pip install 'dcc-mcp-core>=0.20.8,<0.20.9'\n",
            1,
        )
        self.assertNotEqual(
            workflows[".github/workflows/ci.yml"],
            reviewer_counterexample[".github/workflows/ci.yml"],
        )
        with self.assertRaises(ValueError):
            checker(self.catalog, reviewer_counterexample)

        bypasses = {
            "comment-only": (
                setup_step,
                "      - run: '# python scripts/setup_released_core.py'\n",
            ),
            "later-decoy": (
                setup_step,
                "      - run: echo validation already started\n" + setup_step,
            ),
            "conditional-setup": (
                setup_step,
                "      - if: ${{ false }}\n" + f"        run: {setup_command}\n",
            ),
            "conditional-decoy": (
                setup_step,
                (
                    "      - run: pip install dcc-mcp-core~=0.20.8\n"
                    "      - if: ${{ false }}\n"
                    f"        run: {setup_command}\n"
                ),
            ),
            "competing-install-after-setup": (
                setup_step,
                setup_step + "      - run: uv pip install dcc_mcp_core\n",
            ),
            "comment-vx-decoy": (
                setup_step,
                (
                    "      - run: |\n"
                    "          # python scripts/setup_released_core.py\n"
                    "          vx run pip install dcc-mcp-core\n"
                ),
            ),
        }
        for name, (before, after) in bypasses.items():
            with self.subTest(bypass=name):
                mutated = dict(workflows)
                mutated[".github/workflows/ci.yml"] = mutated[
                    ".github/workflows/ci.yml"
                ].replace(before, after, 1)
                self.assertNotEqual(
                    workflows[".github/workflows/ci.yml"],
                    mutated[".github/workflows/ci.yml"],
                )
                with self.assertRaises(ValueError):
                    checker(self.catalog, mutated)

    def test_workflow_rejects_bash_continued_core_install(self) -> None:
        setup_command = self._setup_command()
        setup_step = f"      - run: {setup_command}\n"
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            setup_step,
            setup_step
            + "      - run: |\n"
            + "          p\\\n"
            + "          ip install dcc-mcp-core==0.20.8\n",
        )

    def test_workflow_rejects_cross_shell_continued_core_install(self) -> None:
        setup_command = self._setup_command()
        setup_step = f"      - run: {setup_command}\n"
        continuations = {
            "pwsh": ("`", "pwsh"),
            "cmd": ("^", "cmd"),
        }
        for name, (continuation, shell) in continuations.items():
            with self.subTest(shell=name):
                self._assert_workflow_replacement_rejected(
                    ".github/workflows/ci.yml",
                    setup_step,
                    setup_step
                    + f"      - shell: {shell}\n"
                    + "        run: |\n"
                    + f"          p{continuation}\n"
                    + "          ip.exe install dcc-mcp-core==0.20.8\n",
                )

    def test_workflow_rejects_environment_indirected_core_install(self) -> None:
        setup_command = self._setup_command()
        setup_step = f"      - run: {setup_command}\n"
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            setup_step,
            setup_step
            + "      - env:\n"
            + "          STALE_CORE_INSTALL: python -m pip install dcc-mcp-core==0.20.8\n"
            + "        run: $STALE_CORE_INSTALL\n",
        )

    def test_workflow_rejects_variable_command_core_install(self) -> None:
        setup_command = self._setup_command()
        setup_step = f"      - run: {setup_command}\n"
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            setup_step,
            setup_step
            + "      - run: |\n"
            + "          core_installer=pip\n"
            + '          "$core_installer" install dcc-mcp-core==0.20.8\n',
        )

    def test_workflow_rejects_unreachable_required_job(self) -> None:
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            "  validate:\n",
            "  validate:\n    if: ${{ false }}\n",
        )

    def test_workflow_rejects_unreachable_required_trigger(self) -> None:
        self._assert_workflow_replacement_rejected(
            ".github/workflows/release.yml",
            '    tags: ["v*"]\n',
            "    tags: []\n",
        )

    def test_workflow_rejects_core_install_action_surface(self) -> None:
        setup_command = self._setup_command()
        setup_step = f"      - run: {setup_command}\n"
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            setup_step,
            setup_step + "      - uses: attacker/dcc-mcp-core-install@0123456789abcdef\n",
        )

    def test_workflow_rejects_python_api_stale_core_install_after_setup(self) -> None:
        setup_command = self._setup_command()
        setup_step = f"      - run: {setup_command}\n"
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            setup_step,
            setup_step
            + "      - run: >-\n"
            + "          python -c \"import subprocess; "
            + "subprocess.check_call(['python','-m','pip','install',"
            + "'dcc-mcp-core==0.20.8'])\"\n",
        )

    def test_workflow_rejects_unmodeled_stale_core_job(self) -> None:
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            "  validate:\n",
            "  stale-core:\n"
            + "    runs-on: ubuntu-latest\n"
            + "    steps:\n"
            + "      - run: python -m pip install dcc-mcp-core==0.20.8\n"
            + "  validate:\n",
        )

    def test_workflow_rejects_local_composite_action_after_setup(self) -> None:
        setup_command = self._setup_command()
        setup_step = f"      - run: {setup_command}\n"
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            setup_step,
            setup_step + "      - uses: ./.github/actions/project-bootstrap\n",
        )

    def test_workflow_rejects_required_branch_redirected_away_from_main(self) -> None:
        self._assert_workflow_replacement_rejected(
            ".github/workflows/ci.yml",
            "  push:\n    branches: [main]\n",
            "  push:\n    branches: [never-runs-on-main]\n",
        )

    def test_workflow_rejects_adjacent_topology_and_trigger_decoys(self) -> None:
        cases = {
            "unmodeled-noop-job": (
                ".github/workflows/ci.yml",
                "  validate:\n",
                "  unmodeled-noop:\n"
                + "    runs-on: ubuntu-latest\n"
                + "    steps:\n"
                + "      - run: echo no-op\n"
                + "  validate:\n",
            ),
            "unmodeled-reusable-workflow": (
                ".github/workflows/ci.yml",
                "  validate:\n",
                "  unmodeled-reusable:\n"
                + "    uses: ./.github/workflows/project-bootstrap.yml\n"
                + "  validate:\n",
            ),
            "required-path-redirect": (
                ".github/workflows/clawhub.yml",
                '      - "scripts/setup_released_core.py"\n',
                '      - "scripts/unrelated.py"\n',
            ),
            "required-path-expansion": (
                ".github/workflows/clawhub.yml",
                '      - ".github/workflows/clawhub.yml"\n',
                '      - ".github/workflows/clawhub.yml"\n'
                + '      - ".github/actions/**"\n',
            ),
        }
        for name, (relative, before, after) in cases.items():
            with self.subTest(bypass=name):
                self._assert_workflow_replacement_rejected(relative, before, after)

    def test_workflow_rejects_adjacent_indirection_and_execution_control_decoys(self) -> None:
        setup_command = self._setup_command()
        setup_step = f"      - run: {setup_command}\n"
        cases = {
            "shell-function": (
                setup_step,
                setup_step
                + "      - run: |\n"
                + "          install_core() {\n"
                + "            core_installer=pip\n"
                + '            "$core_installer" install dcc-mcp-core==0.20.8\n'
                + "          }\n"
                + "          install_core\n",
            ),
            "eval": (
                setup_step,
                setup_step
                + "      - run: |\n"
                + "          stale_core='python -m pip install dcc-mcp-core==0.20.8'\n"
                + '          eval "$stale_core"\n',
            ),
            "trap": (
                setup_step,
                setup_step
                + "      - run: trap 'python -m pip install dcc-mcp-core==0.20.8' EXIT\n",
            ),
            "versioned-pip-executable": (
                setup_step,
                setup_step
                + "      - shell: pwsh\n"
                + "        run: pip3.12.exe install -r requirements.txt\n",
            ),
            "setup-execution-controls": (
                setup_step,
                "      - if: ${{ always() }}\n"
                + "        shell: bash\n"
                + "        working-directory: .\n"
                + "        env:\n"
                + '          SAFE: "1"\n'
                + "        continue-on-error: false\n"
                + "        timeout-minutes: 5\n"
                + f"        run: {setup_command}\n",
            ),
            "job-default-shell": (
                "  validate:\n",
                "  validate:\n"
                + "    defaults:\n"
                + "      run:\n"
                + "        shell: echo {0}\n",
            ),
            "job-environment": (
                "  validate:\n",
                "  validate:\n"
                + "    env:\n"
                + "      CORE_INSTALLER: pip\n",
            ),
            "job-continue-on-error": (
                "  validate:\n",
                "  validate:\n    continue-on-error: true\n",
            ),
            "job-timeout": (
                "  validate:\n    runs-on: ubuntu-latest\n    timeout-minutes: 15\n",
                "  validate:\n    runs-on: ubuntu-latest\n    timeout-minutes: 0\n",
            ),
            "workflow-environment": (
                "jobs:\n",
                "env:\n"
                + "  CORE_INSTALLER: pip\n"
                + "jobs:\n",
            ),
            "workflow-default-shell": (
                "jobs:\n",
                "defaults:\n"
                + "  run:\n"
                + "    shell: echo {0}\n"
                + "jobs:\n",
            ),
        }
        for name, (before, after) in cases.items():
            with self.subTest(bypass=name):
                self._assert_workflow_replacement_rejected(
                    ".github/workflows/ci.yml",
                    before,
                    after,
                )

    def test_released_core_runtime_rejects_conflicting_version_or_commit(self) -> None:
        source = self.catalog["sources"]["released_cli"]
        checker = getattr(product_discovery, "validate_released_core_runtime", None)
        self.assertIsNotNone(checker, "installed Core needs exact version and commit validation")
        checker(
            self.catalog,
            installed_version=source["version"],
            resolved_commit=source["commit"],
        )

        with self.assertRaises(ValueError):
            checker(
                self.catalog,
                installed_version="0.20.8",
                resolved_commit=source["commit"],
            )
        with self.assertRaises(ValueError):
            checker(
                self.catalog,
                installed_version=source["version"],
                resolved_commit="f" * 40,
            )

    def test_non_catalog_commands_do_not_import_optional_yaml(self) -> None:
        result = subprocess.run(
            [sys.executable, "-S", "-c", "import scripts.sync_product_discovery"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_released_source_snapshot_rejects_version_and_source_co_mutation(self) -> None:
        source = self.catalog["sources"]["released_cli"]
        released_snapshot = {
            "repository": source["repository"],
            "tag": source["tag"],
            "commit": source["commit"],
        }
        checker = getattr(product_discovery, "validate_released_source_snapshot", None)
        self.assertIsNotNone(checker, "an authoritative release-source checker is required")
        checker(self.catalog, released_snapshot)

        mutation = deepcopy(self.catalog)
        mutated_source = mutation["sources"]["released_cli"]
        mutated_source["version"] = "99.99.99"
        mutated_source["tag"] = "v99.99.99"
        mutated_source["commit"] = "f" * 40
        mutation["sources"]["core_catalog"]["commit"] = "f" * 40
        product_discovery.validate_product_catalog(mutation)

        with self.assertRaises(ValueError):
            checker(mutation, released_snapshot)

    def test_immutable_catalog_rejects_a_coordinated_source_product_rename(self) -> None:
        immutable_snapshot = {
            "entries": [
                {
                    "name": product["adapter"],
                    "dcc": [product["id"]],
                    "url": product["repository"],
                    "tags": ["adapter"],
                    **(
                        {"install": {"type": "test"}}
                        if product["catalog_install_available"]
                        else {}
                    ),
                }
                for product in self.catalog["products"]
            ]
        }
        renamed = deepcopy(self.catalog)
        renamed["sources"]["released_cli"]["dcc_types"][0] = "3dsmax-renamed"
        renamed["products"][0]["id"] = "3dsmax-renamed"

        # The enriched source and product can remain internally consistent.
        product_discovery.validate_product_catalog(renamed)
        checker = getattr(product_discovery, "validate_core_catalog_snapshot", None)
        self.assertIsNotNone(checker, "an immutable authoritative checker is required")
        checker(self.catalog, immutable_snapshot)
        with self.assertRaises(ValueError):
            checker(renamed, immutable_snapshot)

    def test_built_llms_txt_preserves_the_complete_ui_routing_contract(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            build(output, ROOT)
            llms = (output / "llms.txt").read_text(encoding="utf-8")

        route = self.catalog["ui_routing"]
        self.assertIn("typed DCC-MCP tools", llms)
        self.assertIn("provider=dcc-cua", llms)
        self.assertIn("hard provider boundary", llms)
        self.assertIn("canonical/default", llms)
        self.assertIn("human-only", llms.casefold())
        for search_term in route["search_terms"]:
            with self.subTest(search_term=search_term):
                self.assertIn(search_term, llms)
        for scope in route["scope"]:
            with self.subTest(scope=scope):
                self.assertIn(scope, llms)
        for field in route["required_attestation"]:
            with self.subTest(attestation=field):
                self.assertIn(f"{field}=", llms)
        for action in route["action_contract"]:
            with self.subTest(action=action):
                self.assertIn(action, llms)
        for fallback in route["forbidden_fallbacks"]:
            with self.subTest(fallback=fallback):
                self.assertIn(fallback, llms)
        for challenge in route["human_handoff"]:
            with self.subTest(challenge=challenge):
                self.assertIn(challenge, llms)

    def test_llms_ui_text_is_derived_from_ui_routing(self) -> None:
        catalog = deepcopy(build_catalog(ROOT))
        catalog["ui_routing"]["canonical_provider"] = "review-provider"
        catalog["ui_routing"]["forbidden_fallbacks"] = ["Review Fallback"]
        catalog["ui_routing"]["human_handoff"] = ["review challenge"]

        llms = _llms_txt(catalog)
        self.assertIn("provider=review-provider", llms)
        self.assertIn("Review Fallback", llms)
        self.assertIn("review challenge", llms)

    def test_alias_fields_are_arrays_of_non_empty_strings(self) -> None:
        invalid_values = (
            ("aliases", "Blender"),
            ("contextual_aliases", "Maya"),
            ("aliases", [""]),
            ("contextual_aliases", ["  "]),
            ("aliases", [7]),
        )
        for field, value in invalid_values:
            mutation = deepcopy(self.catalog)
            mutation["products"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                product_discovery.validate_product_catalog(mutation)

        for field in ("aliases", "contextual_aliases"):
            mutation = deepcopy(self.catalog)
            del mutation["products"][0][field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                product_discovery.validate_product_catalog(mutation)

    def test_adapter_and_repository_duplicates_use_normalized_identity(self) -> None:
        mutation = deepcopy(self.catalog)
        first = mutation["products"][0]
        second = mutation["products"][1]
        second["adapter"] = first["adapter"].upper()
        second["repository"] = first["repository"].upper() + "/"

        with self.assertRaises(ValueError):
            product_discovery.validate_product_catalog(mutation)


if __name__ == "__main__":
    unittest.main()
