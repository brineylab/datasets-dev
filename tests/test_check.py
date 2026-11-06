import unittest
from helpers import TINY, copy_of, git
import check  # noqa: E402
ORG = check.hub_org()  # hub.toml's organization: a fork with its own is its own store

class CheckTests(unittest.TestCase):
    def test_frontmatter_reads_the_five_fields(self):
        fm = check.frontmatter(TINY / "SKILL.md")
        self.assertEqual((fm["name"], fm["metadata"]["version"], fm["metadata"]["tools"], fm["metadata"]["license"]), ("tiny", "1.0.0", "hello@1.0.1", "mit"))

    def test_two_tools_separated_by_a_space_pass(self):
        with copy_of(TINY) as d:
            skill = d / "SKILL.md"; skill.write_text(skill.read_text().replace("tools: hello@1.0.1", "tools: hello@1.0.1 datascience@1.0.0"))
            self.assertEqual(check.rules(d), [])

    def test_a_malformed_tools_list_is_refused(self):
        for value in ("hello@1.0.1,datascience@1.0.0", "hello@1.0.1  datascience@1.0.0", ""):
            with self.subTest(value=value), copy_of(TINY) as d:
                skill = d / "SKILL.md"; skill.write_text(skill.read_text().replace("tools: hello@1.0.1", f'tools: "{value}"'))
                self.assertIn(f"tools {value!r} is not one or more toolshed tools' name@MAJOR.MINOR.PATCH separated by single spaces", check.rules(d))

    def test_rules_pass_on_the_fixture_and_name_each_defect(self):
        self.assertEqual(check.rules(TINY), [])
        with copy_of(TINY) as d:
            (d / "recipe" / "params.toml").unlink()
            self.assertIn("recipe/params.toml is missing", check.rules(d))
        with copy_of(TINY) as d:
            skill = d / "SKILL.md"; skill.write_text(skill.read_text().replace("name: tiny", "name: other"))
            self.assertIn("name 'other' is not the directory's 'tiny'", check.rules(d))
        with copy_of(TINY) as d:
            skill = d / "SKILL.md"; skill.write_text(skill.read_text().replace("version: 1.0.0", "version: 1.0"))
            self.assertIn("version '1.0' is not MAJOR.MINOR.PATCH", check.rules(d))
        with copy_of(TINY) as d:
            (d / "recipe" / "build").chmod(0o644)
            self.assertIn("recipe/build is not executable", check.rules(d))

    def test_rules_refuse_a_credential_and_a_params_file_that_does_not_parse(self):
        with copy_of(TINY) as d:
            (d / "recipe" / "params.toml").write_text("seed = 1\ntoken = \"hf_" + "a" * 34 + "\"\n")
            self.assertIn("recipe/params.toml holds what looks like a credential (hf_)", check.rules(d))
        with copy_of(TINY) as d:
            (d / "recipe" / "params.toml").write_text("seed = \n")
            self.assertTrue(any(r.startswith("recipe/params.toml does not parse") for r in check.rules(d)))

    def test_the_minimal_toml_reader_reads_the_recipes_shapes(self):
        text = 'seed = 1\nidentity = 0.9\nspecies = "human"\nlimit_on = false\nsplit = [0.8, 0.1, 0.1]  # fractions\n\n# a comment\n'
        self.assertEqual(check.read_toml(text, minimal=True),
                         {"seed": 1, "identity": 0.9, "species": "human", "limit_on": False, "split": [0.8, 0.1, 0.1]})

    def test_tree_hash_is_gits(self):
        with copy_of(TINY) as d:
            (d / "recipe" / "sub").mkdir(); (d / "recipe" / "sub" / "x").write_text("x\n")
            (d / "recipe" / "sub.txt").write_text("sorts before sub/ in git's order\n")
            git(d, "init", "-q"); git(d, "add", "."); git(d, "commit", "-q", "-m", "x")
            self.assertEqual(check.tree_hash(d / "recipe"), git(d, "rev-parse", "HEAD:recipe").strip())

    def test_scan_finds_credential_shapes(self):
        self.assertEqual(check.scan("token hf_" + "a" * 34 + " end"), ["hf_"])
        self.assertEqual(check.scan("nothing here"), [])

    def test_hub_toml_names_the_org_and_the_shed(self):
        self.assertRegex(check.hub_org(), r"^[a-z0-9][a-z0-9-]*$"); self.assertEqual(check.toolshed_registry(), "ghcr.io/brineylab/toolshed")

if __name__ == "__main__":
    unittest.main()
