from __future__ import annotations

import unittest
import shutil
import uuid
from pathlib import Path

from workflow import (
    _diff_snapshot_files,
    _expected_test_targets_from_go_files,
    _merge_effective_files,
    _module_prefixes_from_paths,
    _snapshot_files,
)


class TestArtifactAccounting(unittest.TestCase):
    def _new_case_dir(self) -> Path:
        base = Path("project_migrations") / "_tmp_unit_tests"
        base.mkdir(parents=True, exist_ok=True)
        case = base / f"case_{uuid.uuid4().hex[:8]}"
        case.mkdir(parents=True, exist_ok=True)
        return case

    def test_regression_subdir_expected_target(self) -> None:
        go_files = ["retryexec/source.go"]
        expected = _expected_test_targets_from_go_files(go_files)
        self.assertEqual(expected, ["retryexec/source_test.go"])

    def test_multi_file_expected_targets(self) -> None:
        go_files = ["a.go", "b.go", "internal/c.go", "internal/c_test.go"]
        expected = _expected_test_targets_from_go_files(go_files)
        self.assertEqual(expected, ["a_test.go", "b_test.go", "internal/c_test.go"])

    def test_fallback_diff_when_no_declared(self) -> None:
        root = self._new_case_dir()
        try:
            before = _snapshot_files(
                root,
                include=lambda rel: rel.endswith("_test.go"),
            )
            p = root / "retryexec" / "source_test.go"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("package retryexec\n", encoding="utf-8")
            after = _snapshot_files(
                root,
                include=lambda rel: rel.endswith("_test.go"),
            )
            diff = _diff_snapshot_files(before, after)
            self.assertEqual(diff, ["retryexec/source_test.go"])
            effective = _merge_effective_files([], diff)
            self.assertEqual(effective, ["retryexec/source_test.go"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_merge_declared_and_diff_conflict(self) -> None:
        declared = ["retryexec/source_test.go", "a_test.go"]
        diff = ["a_test.go", "b_test.go"]
        effective = _merge_effective_files(declared, diff)
        self.assertEqual(effective, ["a_test.go", "b_test.go", "retryexec/source_test.go"])

    def test_scope_ignores_non_go_and_translate_test_files(self) -> None:
        root = self._new_case_dir()
        try:
            (root / "mod" / "a.go").parent.mkdir(parents=True, exist_ok=True)
            (root / "mod" / "a.go").write_text("package mod\n", encoding="utf-8")
            (root / "mod" / "a_test.go").write_text("package mod\n", encoding="utf-8")
            (root / "mod" / "readme.txt").write_text("x", encoding="utf-8")
            prefixes = _module_prefixes_from_paths(["mod/a.go"])
            snap = _snapshot_files(
                root,
                include=lambda rel: rel.endswith(".go")
                and not rel.endswith("_test.go")
                and any(rel == p or rel.startswith(p + "/") or p == "" for p in prefixes),
            )
            self.assertEqual(sorted(snap.keys()), ["mod/a.go"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
