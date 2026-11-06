import os, shutil, subprocess, tempfile, unittest
from pathlib import Path
from helpers import ROOT, TINY, git
import check  # noqa: E402
ORG = check.hub_org()  # hub.toml's organization: a fork with its own is its own store

class RecordTests(unittest.TestCase):
    """The real scripts/record in a temporary repository holding the tiny fixture as datasets/tiny, committed."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        for s in ("record", "check.py"):
            shutil.copy(ROOT / "scripts" / s, self.repo / "scripts")
        shutil.copy(ROOT / "hub.toml", self.repo)
        shutil.copytree(TINY, self.repo / "datasets" / "tiny")
        git(self.repo, "init", "-q"); git(self.repo, "add", "-A"); git(self.repo, "commit", "-qm", "tiny")
        self.tree = check.tree_hash(self.repo / "datasets" / "tiny" / "recipe")

    def run_script(self, *args, input=None):
        return subprocess.run(["bash", "scripts/record", *map(str, args)], cwd=self.repo, input=input, capture_output=True, text=True)

    def test_record_writes_the_format_and_refuses_a_credential(self):
        out = f"train.txt 3 rows, eval.txt 1 row\nfile train.txt 18 {'c' * 64}\ncommit: {'a' * 40}\n"
        r = self.run_script("tiny", "a" * 40, "0", "podman", "laptop", "2026-11-05T00:00:00Z", input=out)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "results/tiny/1.0.0.txt"), r.stderr)
        path = self.repo / "results/tiny/1.0.0.txt"
        self.assertEqual(path.read_text(), f"---\ndataset: tiny\nversion: 1.0.0\nhub: {ORG}/tiny\nbranch: candidate-{self.tree}\n"
                         f"commit: {'a' * 40}\ntree: {self.tree}\ntools: hello@1.0.1\nrunner: podman\nhost: laptop\n"
                         f"started: 2026-11-05T00:00:00Z\nexit: 0\n---\n{out}")
        self.assertEqual(check.parse_record(path)["files"], [("train.txt", 18, "c" * 64)])
        r = self.run_script("tiny", "b" * 40, "0", "podman", "laptop", "now", input="hf_" + "b" * 34)
        self.assertEqual(r.returncode, 1); self.assertIn("credential", r.stderr)
        self.assertIn("a" * 40, path.read_text())  # the refused output wrote nothing

    def test_record_keeps_every_tool(self):
        skill = self.repo / "datasets/tiny/SKILL.md"
        skill.write_text(skill.read_text().replace("tools: hello@1.0.1", "tools: hello@1.0.1 datascience@1.0.0"))
        r = self.run_script("tiny", "a" * 40, "0", "podman", "laptop", "now", input="")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.repo / "results/tiny/1.0.0.txt").read_text()
        self.assertIn("\ntools: hello@1.0.1 datascience@1.0.0\nrunner: podman\n", text)
        self.assertEqual(check.parse_record(self.repo / "results/tiny/1.0.0.txt")["tools"], "hello@1.0.1 datascience@1.0.0")

    def test_record_refuses_a_commit_that_is_not_forty_hex_and_an_exit_that_is_not_a_number(self):
        self.assertEqual(self.run_script("tiny", "main", "0", "podman", "h", "now", input="").returncode, 2)
        self.assertEqual(self.run_script("tiny", "a" * 40, "ok", "podman", "h", "now", input="").returncode, 2)
        self.assertFalse((self.repo / "results").exists())

if __name__ == "__main__":
    unittest.main()
