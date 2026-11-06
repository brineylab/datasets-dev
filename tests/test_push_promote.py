import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from helpers import ROOT, TINY, git
import check  # noqa: E402
ORG = check.hub_org()  # hub.toml's organization: a fork with its own is its own store

STUBS = ROOT / "tests" / "stubs"
# Each script runs as `python3 -I` does, with the fake huggingface_hub first on sys.path, which -I would not take from PYTHONPATH.
LAUNCH = "import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[2:]; runpy.run_path(sys.argv[0], run_name='__main__')"

class PushPromoteTests(unittest.TestCase):
    """The real scripts in a temporary repository holding the tiny fixture, and the recipe's output in a plain directory;
    the Hub is the fake's JSON file."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        self.repo, self.out, self.hub = self.tmp / "repo", self.tmp / "out", self.tmp / "hub.json"
        (self.repo / "scripts").mkdir(parents=True)
        for s in ("push", "promote", "check.py"):
            shutil.copy(ROOT / "scripts" / s, self.repo / "scripts")
        shutil.copy(ROOT / "hub.toml", self.repo)
        shutil.copytree(TINY, self.repo / "datasets" / "tiny")
        git(self.repo, "init", "-q"); git(self.repo, "add", "-A"); git(self.repo, "commit", "-qm", "tiny")
        self.tree = check.tree_hash(self.repo / "datasets/tiny/recipe")
        self.branch = "candidate-" + self.tree
        subprocess.run([str(TINY / "recipe" / "build"), str(self.out)], check=True)
        (self.out / ".work").mkdir(); (self.out / ".work" / "source.csv").write_text("staged\n")

    def run_script(self, *args):
        env = {**os.environ, "HF_TOKEN": "hf_test", "FAKE_HUB": str(self.hub)}
        return subprocess.run([sys.executable, "-I", "-c", LAUNCH, str(STUBS), *map(str, args)], cwd=self.repo, env=env, capture_output=True, text=True)

    def state(self):
        return json.loads(self.hub.read_text())

    def sha(self, name):
        return hashlib.sha256((self.out / name).read_bytes()).hexdigest()

    def test_push_creates_the_repo_replaces_the_candidate_and_prints_the_manifest(self):
        self.hub.write_text(json.dumps({"branches": {"main": "m" * 40, self.branch: "old"}}))
        r = self.run_script("scripts/push", "tiny", self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        out, s = r.stdout.splitlines(), self.state()
        self.assertEqual(s["calls"][:4], [["create_repo", f"{ORG}/tiny"], ["list_repo_refs", f"{ORG}/tiny"], ["delete_branch", self.branch], ["create_branch", self.branch]])
        self.assertEqual(out[:2], [f"file eval.txt 6 {self.sha('eval.txt')}", f"file train.txt 18 {self.sha('train.txt')}"])
        self.assertEqual(out[2], f"commit: {s['branches'][self.branch]}"); self.assertRegex(out[2], r"^commit: [0-9a-f]{40}$"); self.assertEqual(len(out), 3)
        self.assertEqual(s["uploaded"], ["eval.txt", "train.txt"])  # not .work/
        self.assertIn(["upload_file", "README.md"], s["calls"]); self.assertNotIn("hf_test", r.stdout + r.stderr)

    def test_push_of_a_new_candidate_creates_its_branch_without_deleting_one(self):
        self.assertEqual(self.run_script("scripts/push", "tiny", self.out).returncode, 0)
        self.assertEqual([c[0] for c in self.state()["calls"][:3]], ["create_repo", "list_repo_refs", "create_branch"])

    def test_push_names_the_candidate_by_the_committed_tree(self):
        self.assertEqual(self.run_script("scripts/push", "tiny", self.out).returncode, 0)
        committed = git(self.repo, "rev-parse", "HEAD:datasets/tiny/recipe").strip()
        self.assertEqual(self.state()["calls"][2], ["create_branch", "candidate-" + committed])

    def refused(self, *args):
        r = self.run_script("scripts/push", "tiny", *args)
        self.assertEqual(r.returncode, 1, r.stdout); self.assertFalse(self.hub.exists())  # no call reached the Hub
        return r.stderr + r.stdout

    def test_push_refuses_uncommitted_changes(self):
        with open(self.repo / "datasets/tiny/recipe/params.toml", "a") as f: f.write("more = 2\n")
        self.assertIn("datasets/tiny has uncommitted changes; commit them first", self.refused(self.out))

    def test_push_refuses_an_ignored_file_in_the_recipe(self):
        (self.repo / ".gitignore").write_text("*.tmp\n"); git(self.repo, "add", ".gitignore"); git(self.repo, "commit", "-qm", "ignore")
        (self.repo / "datasets/tiny/recipe/x.tmp").write_text("x\n")
        self.assertIn("datasets/tiny has uncommitted changes; commit them first", self.refused(self.out))

    def test_push_refuses_an_untracked_file_a_users_git_config_hides(self):
        git(self.repo, "config", "status.showUntrackedFiles", "no")
        (self.repo / "datasets/tiny/recipe/extra").write_text("x\n")
        self.assertIn("datasets/tiny has uncommitted changes; commit them first", self.refused(self.out))

    def test_push_refuses_when_git_cannot_say_the_inputs_are_committed(self):
        shutil.rmtree(self.repo / ".git")
        r = self.run_script("scripts/push", "tiny", self.out)
        self.assertEqual(r.returncode, 1); self.assertTrue(r.stderr.startswith("cannot tell whether datasets/tiny is committed:"), r.stderr)
        self.assertFalse(self.hub.exists())

    def test_push_refuses_a_skill_holding_a_credential(self):
        skill = self.repo / "datasets/tiny/SKILL.md"
        skill.write_text(skill.read_text() + "\nhf_" + "a" * 34 + "\n"); git(self.repo, "commit", "-qam", "leak")
        self.assertIn("SKILL.md holds what looks like a credential (hf_)", self.refused(self.out))

    def test_push_refuses_an_output_with_no_files(self):
        empty, missing = self.tmp / "empty", self.tmp / "missing"
        empty.mkdir(); (empty / ".work").mkdir(); (empty / ".work" / "x").write_text("x\n")  # hidden files are not data
        for path in (empty, missing):
            with self.subTest(path=path):
                self.assertIn(f"{path} holds no files to push", self.refused(path))

    def test_the_card_carries_the_license_and_the_skills_body(self):
        self.run_script("scripts/push", "tiny", self.out)
        card = self.state()["files"]["README.md"]
        self.assertTrue(card.startswith("---\nlicense: mit\npretty_name: tiny\n---\n")); self.assertIn("## Files", card)
        self.assertNotIn("hello@1.0.1", card)  # the skill's frontmatter stays in the skill

    def record(self, commit, merged=True):
        """The record, committed; merged, origin/main holds that commit, as after the pull request's merge."""
        (self.repo / "results/tiny").mkdir(parents=True)
        (self.repo / "results/tiny/1.0.0.txt").write_text(f"---\ndataset: tiny\nversion: 1.0.0\nhub: {ORG}/tiny\nbranch: {self.branch}\n"
                                                         f"commit: {commit}\ntree: {self.tree}\nexit: 0\n---\ncommit: {commit}\n")
        git(self.repo, "add", "results"); git(self.repo, "commit", "-qm", "record")
        if merged:
            git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    def test_promote_refuses_a_record_that_is_not_on_main(self):
        self.hub.write_text(json.dumps({"branches": {self.branch: "c" * 40}}))
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.record("c" * 40, merged=False)
        r = self.run_script("scripts/promote", "tiny", "1.0.0")
        self.assertEqual(r.returncode, 1); self.assertIn("results/tiny/1.0.0.txt is not on origin/main (", r.stderr); self.assertIn("merge its pull request and pull first", r.stderr)
        self.assertEqual(self.state().get("calls", []), [])  # nothing reached the Hub

    def test_promote_says_why_git_cannot_find_the_record_on_main(self):
        self.record("c" * 40)
        shutil.rmtree(self.repo / ".git")  # as in a worktree whose main clone is not mounted
        r = self.run_script("scripts/promote", "tiny", "1.0.0")
        self.assertEqual(r.returncode, 1); self.assertIn("results/tiny/1.0.0.txt is not on origin/main (", r.stderr)
        self.assertIn("not a git repository", r.stderr); self.assertNotIn("Traceback", r.stderr)

    def test_promote_refuses_a_merged_record_missing_here(self):
        self.record("c" * 40)
        (self.repo / "results/tiny/1.0.0.txt").unlink()
        r = self.run_script("scripts/promote", "tiny", "1.0.0")
        self.assertEqual(r.returncode, 1); self.assertIn("is not on origin/main", r.stderr); self.assertNotIn("Traceback", r.stderr)

    def test_promote_tags_the_records_commit_and_deletes_the_branch(self):
        self.hub.write_text(json.dumps({"branches": {"main": "m" * 40, self.branch: "c" * 40}}))
        self.record("c" * 40)
        r = self.run_script("scripts/promote", "tiny", "1.0.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.state()
        self.assertEqual(s["tags"]["v1.0.0"], "c" * 40); self.assertNotIn(self.branch, s["branches"])
        self.assertEqual(r.stdout.splitlines()[-1], f"promoted: {ORG}/tiny v1.0.0 at {'c' * 40}")

    def test_promote_never_moves_an_existing_tag(self):
        self.hub.write_text(json.dumps({"branches": {self.branch: "c" * 40}, "tags": {"v1.0.0": "x" * 40}}))
        self.record("c" * 40)
        r = self.run_script("scripts/promote", "tiny", "1.0.0")
        self.assertEqual(r.returncode, 1); self.assertIn("v1.0.0 already exists", r.stderr)
        self.assertEqual(self.state()["tags"]["v1.0.0"], "x" * 40); self.assertIn(self.branch, self.state()["branches"])

    def test_promote_run_again_after_it_succeeded_passes(self):
        self.hub.write_text(json.dumps({"tags": {"v1.0.0": "c" * 40}}))
        self.record("c" * 40)
        r = self.run_script("scripts/promote", "tiny", "1.0.0")
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("already promoted", r.stdout)

if __name__ == "__main__":
    unittest.main()
