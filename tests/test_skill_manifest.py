"""Lock the .claude/skills/jarvislabs/ skill manifest valid.

Skills with broken frontmatter silently fail to load. This test catches:
- Missing SKILL.md
- Malformed frontmatter delimiters
- Missing required fields (name, description)
- Name not kebab-case or too long
- Description over 250 chars (truncated in skill listings)
- Referenced sibling files that don't exist
- setup.sh not executable

Parses frontmatter manually so the suite stays dependency-free (no pyyaml).
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / ".claude" / "skills" / "jarvislabs"
SKILL_MD = SKILL_DIR / "SKILL.md"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter_dict, body) from a markdown file with YAML frontmatter."""
    if not text.startswith("---\n"):
        raise ValueError("frontmatter must start with '---' on line 1")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("frontmatter terminator '---' not found")
    raw = text[4:end]
    body = text[end + 5 :]

    fm: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"frontmatter line missing colon: {line!r}")
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm, body


# ---------------------------------------------------------------------------
# Existence + frontmatter
# ---------------------------------------------------------------------------


def test_skill_directory_exists() -> None:
    assert SKILL_DIR.is_dir(), f"missing skill dir: {SKILL_DIR}"


def test_skill_md_exists() -> None:
    assert SKILL_MD.is_file(), f"missing SKILL.md at {SKILL_MD}"


def test_frontmatter_parses() -> None:
    fm, body = _parse_frontmatter(SKILL_MD.read_text())
    assert fm, "frontmatter is empty"
    assert body.strip(), "skill body is empty"


def test_frontmatter_has_required_fields() -> None:
    fm, _ = _parse_frontmatter(SKILL_MD.read_text())
    assert "name" in fm
    assert "description" in fm


def test_name_is_kebab_case_under_64_chars() -> None:
    fm, _ = _parse_frontmatter(SKILL_MD.read_text())
    name = fm["name"]
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", name), (
        f"skill name must be lowercase letters/digits/hyphens: {name!r}"
    )
    assert len(name) <= 64, f"skill name too long: {len(name)} > 64"


def test_description_is_present_and_under_250_chars() -> None:
    fm, _ = _parse_frontmatter(SKILL_MD.read_text())
    desc = fm["description"]
    assert desc, "description must not be empty"
    assert len(desc) <= 250, (
        f"description is {len(desc)} chars; max 250 (it gets truncated in listings)"
    )


def test_description_mentions_jarvislabs_or_jltool() -> None:
    """Trigger keywords must be present so the skill activates correctly."""
    fm, _ = _parse_frontmatter(SKILL_MD.read_text())
    desc = fm["description"].lower()
    assert "jarvislabs" in desc or "jltool" in desc, (
        "skill description must mention 'jarvislabs' or 'jltool' so it triggers"
    )


def test_allowed_tools_field_includes_bash() -> None:
    """The skill must be able to invoke jltool via Bash."""
    fm, _ = _parse_frontmatter(SKILL_MD.read_text())
    allowed = fm.get("allowed-tools", "")
    assert "Bash" in allowed, (
        f"allowed-tools must include Bash for jltool execution: {allowed!r}"
    )


# ---------------------------------------------------------------------------
# Sibling files referenced from SKILL.md
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relpath",
    [
        "REFERENCE.md",
        "workflows.md",
        "scripts/setup.sh",
    ],
)
def test_referenced_sibling_file_exists(relpath: str) -> None:
    target = SKILL_DIR / relpath
    assert target.is_file(), f"missing skill asset: {target}"


def test_skill_md_references_each_sibling() -> None:
    """SKILL.md must explicitly reference REFERENCE.md, workflows.md, and setup.sh
    so Claude knows when to read them (progressive disclosure)."""
    body = SKILL_MD.read_text()
    for needle in ("REFERENCE.md", "workflows.md", "scripts/setup.sh"):
        assert needle in body, f"SKILL.md must reference {needle}"


# ---------------------------------------------------------------------------
# Setup script
# ---------------------------------------------------------------------------


def test_setup_script_is_executable() -> None:
    setup = SKILL_DIR / "scripts" / "setup.sh"
    mode = setup.stat().st_mode
    assert mode & stat.S_IXUSR, f"setup.sh is not executable (mode={oct(mode)})"


def test_setup_script_has_shebang_and_strict_mode() -> None:
    setup = SKILL_DIR / "scripts" / "setup.sh"
    text = setup.read_text()
    assert text.startswith("#!"), "setup.sh missing shebang"
    assert "set -euo pipefail" in text, "setup.sh missing strict-mode pragma"


# ---------------------------------------------------------------------------
# Reference file invariants
# ---------------------------------------------------------------------------


def test_reference_lists_every_namespace() -> None:
    text = (SKILL_DIR / "REFERENCE.md").read_text().lower()
    for ns in ("account", "instances", "scripts", "fs", "keys"):
        assert ns in text, f"REFERENCE.md missing namespace: {ns}"


def test_reference_documents_exit_codes() -> None:
    text = (SKILL_DIR / "REFERENCE.md").read_text()
    for code in ("EXIT_OK", "EXIT_AUTH", "EXIT_INSUFFICIENT_BALANCE"):
        assert code in text, f"REFERENCE.md missing exit code: {code}"


def test_workflows_includes_doctor_pattern() -> None:
    text = (SKILL_DIR / "workflows.md").read_text().lower()
    assert "doctor" in text, "workflows.md must include the doctor preflight pattern"
    assert "instances wait" in text, "workflows.md must reference `instances wait`"
