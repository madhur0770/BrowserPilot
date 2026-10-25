import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]


class PolicySyncTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "browserpilot" / "policy.json").read_text(encoding="utf-8"))
        self.config = yaml.safe_load((ROOT / "mcp_agent.config.yaml").read_text(encoding="utf-8"))
        self.args = self.config["mcp"]["servers"]["playwright"]["args"]

    def test_playwright_version_is_pinned_and_matches_policy(self):
        package = next(a for a in self.args if a.startswith("@playwright/mcp@"))
        self.assertEqual(package, f"@playwright/mcp@{self.policy['playwright_mcp_version']}")
        self.assertNotIn("latest", package)

    def test_blocked_origins_in_config_match_policy(self):
        index = self.args.index("--blocked-origins")
        self.assertEqual(self.args[index + 1].split(";"), self.policy["blocked_origins"])

    def test_browser_runs_headless_and_isolated(self):
        self.assertIn("--headless", self.args)
        self.assertIn("--isolated", self.args)

    def test_readme_mentions_pinned_version(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(self.policy["playwright_mcp_version"], readme)


class RepositoryHygieneTests(unittest.TestCase):
    def test_secrets_example_contains_only_placeholders(self):
        data = yaml.safe_load((ROOT / "mcp_agent.secrets.yaml.example").read_text(encoding="utf-8"))
        self.assertEqual(data["openai"]["api_key"], "YOUR_OPENAI_API_KEY")

    def test_real_secrets_file_is_git_ignored(self):
        self.assertIn("mcp_agent.secrets.yaml", (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    def test_no_credential_like_strings_in_tracked_text(self):
        pattern = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----")
        skip = {".git", "node_modules", "__pycache__"}
        for path in ROOT.rglob("*"):
            if path.is_file() and not skip.intersection(path.relative_to(ROOT).parts) and path.suffix in {".py", ".md", ".yaml", ".yml", ".json", ".mjs", ".html", ".txt", ".example"}:
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8", errors="ignore")), str(path))


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from browserpilot.config import Settings
            s = Settings.from_env()
        self.assertFalse(s.allow_private_network)
        self.assertEqual(s.max_command_chars, 2000)

    def test_env_overrides(self):
        env = {"BROWSERPILOT_ALLOW_PRIVATE_NETWORK": "yes", "BROWSERPILOT_MAX_COMMAND_CHARS": "50",
               "BROWSERPILOT_EXTRA_BLOCKED_ORIGINS": "https://a.example; https://b.example"}
        with mock.patch.dict(os.environ, env, clear=True):
            from browserpilot.config import Settings
            s = Settings.from_env()
        self.assertTrue(s.allow_private_network)
        self.assertEqual(s.max_command_chars, 50)
        self.assertEqual(s.extra_blocked_origins, ("https://a.example", "https://b.example"))

    def test_credentials_detection(self):
        import tempfile
        from browserpilot.config import has_llm_credentials
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(has_llm_credentials(Path(tmp)))
            (Path(tmp) / "mcp_agent.secrets.yaml").write_text("openai:\n  api_key: x\n", encoding="utf-8")
            self.assertTrue(has_llm_credentials(Path(tmp)))
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k"}, clear=True):
            self.assertTrue(has_llm_credentials(Path("/nonexistent")))


class ImportIsolationTests(unittest.TestCase):
    def test_core_package_does_not_import_heavy_dependencies(self):
        import subprocess
        code = ("import sys, browserpilot.config, browserpilot.safety, browserpilot.prompts, browserpilot.runner;"
                "bad=[m for m in ('streamlit','mcp_agent','openai') if m in sys.modules];"
                "sys.exit(1 if bad else 0)")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
