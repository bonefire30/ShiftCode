from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class TestSecretSafety(unittest.TestCase):
    def test_safe_committed_files_do_not_contain_obvious_api_keys(self) -> None:
        paths = [
            ROOT / "README.md",
            ROOT / ".env.example",
            ROOT / "llm_profiles.py",
            ROOT / "security.py",
        ]
        paths.extend((ROOT / "docs").glob("**/*.md"))
        paths.extend((ROOT / "tests").glob("*.py"))
        secret_re = re.compile(r"\bsk-[A-Za-z0-9._\-]{12,}\b|Authorization:\s*Bearer", re.IGNORECASE)

        findings: list[str] = []
        for path in paths:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), 1):
                if "secret_re = re.compile" in line:
                    continue
                if "sanitize_secret_text(" in line and "[REDACTED]" in text:
                    continue
                if secret_re.search(line):
                    findings.append(f"{path.relative_to(ROOT).as_posix()}:{line_no}")

        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
