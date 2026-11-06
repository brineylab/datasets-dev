import json, shutil, tempfile, unittest
from pathlib import Path
from unittest import mock
from helpers import FIXTURES, TINY, copy_of
import check  # noqa: E402
ORG = check.hub_org()  # hub.toml's organization: a fork with its own is its own store

RESULTS = FIXTURES / "results"
HUB = FIXTURES / "hub"
RECORD = check.parse_record(RESULTS / "tiny" / "1.0.0.txt") if hasattr(check, "parse_record") else {"commit": ""}
API = f"https://huggingface.co/api/datasets/{ORG}/tiny"

class HubTests(unittest.TestCase):
    """check.fetch answers from tests/fixtures/hub/, by URL; anything else is absent, as a 404 is."""
    def setUp(self):
        self.answers = {
            f"{API}/refs": (HUB / "refs.json").read_bytes(),
            f"{API}/tree/{RECORD['commit']}?recursive=true": (HUB / "tree.json").read_bytes(),
            "https://api.github.com/repos/brineylab/toolshed/contents/tools": (HUB / "catalogue.json").read_bytes(),
            "https://raw.githubusercontent.com/brineylab/toolshed/main/tools/hello/SKILL.md": (HUB / "hello-SKILL.md").read_bytes(),
        }
        patch = mock.patch.object(check, "fetch", side_effect=lambda url: self.answers.get(url))
        patch.start(); self.addCleanup(patch.stop)

    def edit(self, url, change):
        self.answers[url] = json.dumps(change(json.loads(self.answers[url]))).encode()

    def results_with(self, text):
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d)
        (d / "tiny").mkdir(); (d / "tiny" / "1.0.0.txt").write_text(text)
        return d

    def test_a_fresh_version_with_a_matching_record_passes(self):
        self.assertEqual(check.hub_problems(TINY, RESULTS), [])

    def test_an_existing_tag_is_refused(self):
        self.edit(f"{API}/refs", lambda r: {**r, "tags": [{"name": "v1.0.0", "ref": "refs/tags/v1.0.0", "targetCommit": "f" * 40}]})
        self.assertIn("v1.0.0 is already on the Hub", check.hub_problems(TINY, RESULTS))

    def test_a_missing_record_is_refused(self):
        empty = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, empty)
        self.assertIn("results/tiny/1.0.0.txt is missing", check.hub_problems(TINY, empty))

    def test_a_record_whose_files_differ_from_the_hub_is_refused(self):
        tree = f"{API}/tree/{RECORD['commit']}?recursive=true"
        self.edit(tree, lambda t: [{**f, "lfs": {**f["lfs"], "oid": "0" * 64}} if f["path"] == "eval.txt" else f for f in t])
        self.assertIn("eval.txt differs from the Hub", check.hub_problems(TINY, RESULTS))

    def test_a_file_on_the_hub_the_record_lacks_is_refused(self):
        tree = f"{API}/tree/{RECORD['commit']}?recursive=true"
        self.edit(tree, lambda t: t + [{"type": "file", "path": "extra.parquet", "size": 9, "lfs": {"oid": "1" * 64, "size": 9}}])
        self.assertIn("extra.parquet is not in the record", check.hub_problems(TINY, RESULTS))

    def test_a_record_whose_commit_is_not_on_the_hub_is_refused(self):
        del self.answers[f"{API}/tree/{RECORD['commit']}?recursive=true"]
        self.assertIn(f"the record's commit {RECORD['commit']} is not on {ORG}/tiny", check.hub_problems(TINY, RESULTS))

    def test_a_record_with_a_nonzero_exit_is_refused(self):
        text = (RESULTS / "tiny" / "1.0.0.txt").read_text().replace("exit: 0", "exit: 1")
        self.assertIn("the record's exit is 1", check.hub_problems(TINY, self.results_with(text)))

    def test_a_record_of_another_recipe_tree_is_refused(self):
        with copy_of(TINY) as d:
            (d / "recipe" / "params.toml").write_text("seed = 2\n")
            self.assertIn(f"the record's tree {RECORD['tree']} is not the recipe's {check.tree_hash(d / 'recipe')}; build and test the committed recipe",
                          check.hub_problems(d, RESULTS))

    def test_a_record_of_another_tool_is_refused(self):
        text = (RESULTS / "tiny" / "1.0.0.txt").read_text().replace("tools: hello@1.0.1", "tools: hello@1.0.0")
        self.assertIn("the record's tools hello@1.0.0 is not the skill's hello@1.0.1", check.hub_problems(TINY, self.results_with(text)))

    def test_a_record_holding_a_credential_is_refused(self):
        text = (RESULTS / "tiny" / "1.0.0.txt").read_text() + "HF_TOKEN=hf_" + "a" * 34 + "\n"
        self.assertIn("results/tiny/1.0.0.txt holds what looks like a credential (hf_)", check.hub_problems(TINY, self.results_with(text)))

    def test_a_tool_the_shed_lacks_is_refused(self):
        with copy_of(TINY) as d:
            skill = d / "SKILL.md"; skill.write_text(skill.read_text().replace("hello@1.0.1", "nothere@1.0.0"))
            self.assertIn("nothere@1.0.0 is not in the toolshed", check.hub_problems(d, RESULTS))

    def test_a_second_tool_the_shed_lacks_is_refused(self):
        with copy_of(TINY) as d:
            skill = d / "SKILL.md"; skill.write_text(skill.read_text().replace("hello@1.0.1", "hello@1.0.1 nothere@1.0.0"))
            problems = check.hub_problems(d, RESULTS)
            self.assertIn("nothere@1.0.0 is not in the toolshed", problems)
            self.assertNotIn("hello@1.0.1 is not in the toolshed", problems)

    def test_a_tool_at_a_version_the_shed_lacks_is_refused(self):
        with copy_of(TINY) as d:
            skill = d / "SKILL.md"; skill.write_text(skill.read_text().replace("hello@1.0.1", "hello@1.0.0"))
            self.assertIn("hello@1.0.0 is not in the toolshed", check.hub_problems(d, RESULTS))

    def test_parse_record_reads_the_header_and_the_files(self):
        r = check.parse_record(RESULTS / "tiny" / "1.0.0.txt")
        self.assertEqual((r["version"], r["exit"], len(r["files"])), ("1.0.0", 0, 2))
        self.assertEqual(r["files"][0][:2], ("eval.txt", 6))

if __name__ == "__main__":
    unittest.main()
