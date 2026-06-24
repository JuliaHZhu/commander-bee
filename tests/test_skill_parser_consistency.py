"""#5 — skills.py and skill_audition.py must parse the same frontmatter identically."""
import pytest
from agent.skills import _parse_yamlish
from tools.skill_audition import _parse_frontmatter


EDGE_CASES = [
    # Leading dash in a scalar value (the bug scenario from audit)
    "tag:\n  - something\nname: test",
    # Mixed scalars and lists
    "name: demo\ndescription: A skill\ntools:\n  - t1\n  - t2\ncategory: test",
    # Empty list
    "tools:",
    # Blank lines
    "name: a\n\ndesc: b\n\n  \n",
    # Value starting with hyphen on same line
    "note: - hello world",
]


class TestParserConsistency:
    @pytest.mark.parametrize("text", EDGE_CASES)
    def test_parse_frontmatter_matches_yamlish(self, text):
        """_parse_frontmatter must return the same meta dict as _parse_yamlish for raw frontmatter text."""
        # Wrap in markdown so _parse_frontmatter can extract it
        md = f"---\n{text}\n---\n\nbody here"
        meta, body = _parse_frontmatter(md)
        # Direct parse via skills.py parser
        direct = _parse_yamlish(text)
        assert meta == direct, f"Mismatch for:\n{text}\n_frontmatter={meta}\n_yamlish={direct}"
