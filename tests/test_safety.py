import unittest

from browserpilot.config import Settings
from browserpilot.safety import CommandRejected, extract_urls, validate_command

STRICT = Settings(allow_private_network=False, max_command_chars=200)
PERMISSIVE = Settings(allow_private_network=True, max_command_chars=200)


class ValidateCommandTests(unittest.TestCase):
    def test_accepts_plain_instruction_and_strips_whitespace(self):
        self.assertEqual(validate_command("  Go to https://example.com and summarise  ", STRICT),
                         "Go to https://example.com and summarise")

    def test_rejects_empty_and_whitespace(self):
        for value in ("", "   \n", None):
            with self.assertRaises(CommandRejected):
                validate_command(value, STRICT)

    def test_rejects_overlong_instruction(self):
        with self.assertRaises(CommandRejected) as ctx:
            validate_command("x" * 201, STRICT)
        self.assertIn("too long", str(ctx.exception))

    def test_rejects_non_web_schemes(self):
        for text in ("open file:///etc/passwd", "visit ftp://example.com/x", "run javascript:alert(1)",
                     "open data:text/html,<h1>x</h1>", "go to chrome://settings"):
            with self.subTest(text=text), self.assertRaises(CommandRejected):
                validate_command(text, STRICT)

    def test_rejects_local_and_private_targets(self):
        for url in ("http://localhost:8501", "https://127.0.0.1/admin", "http://[::1]:80/", "http://0.0.0.0:3000",
                    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.4.2/", "http://169.254.169.254/latest/meta-data",
                    "http://metadata.google.internal/", "http://printer.local/", "http://db.internal/"):
            with self.subTest(url=url), self.assertRaises(CommandRejected):
                validate_command(f"Open {url} and read it", STRICT)

    def test_allows_public_hosts_and_public_ips(self):
        for url in ("https://example.com/a?b=1", "http://93.184.216.34/", "https://sub.domain.example.org"):
            with self.subTest(url=url):
                validate_command(f"Open {url}", STRICT)

    def test_private_targets_allowed_only_when_explicitly_enabled(self):
        self.assertEqual(validate_command("Open http://localhost:8501", PERMISSIVE), "Open http://localhost:8501")

    def test_non_web_schemes_stay_blocked_even_with_private_network_enabled(self):
        with self.assertRaises(CommandRejected):
            validate_command("open file:///etc/passwd", PERMISSIVE)

    def test_trailing_punctuation_is_not_part_of_url(self):
        self.assertEqual(extract_urls("See https://example.com/page."), ["https://example.com/page"])
        self.assertEqual(extract_urls("(https://example.com)"), ["https://example.com"])


if __name__ == "__main__":
    unittest.main()
