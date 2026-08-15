"""PowerShell scripts must be parseable by Windows PowerShell 5.1.

A live setup run died with 'The string is missing the terminator' on a
line that was syntactically fine. Cause: Windows PowerShell 5.1 reads
.ps1 as ANSI (Windows-1252) unless the file carries a UTF-8 BOM, so
every multi-byte character became mojibake and eventually broke string
parsing.

Two defences, both enforced here: a BOM so the encoding is declared,
and ASCII-only bodies so the file is safe even where the BOM is lost
(copy-paste, some editors, transfer through other tools).
"""

from pathlib import Path

import pytest

SCRIPTS = sorted((Path(__file__).resolve().parent.parent / "scripts").glob("*.ps1"))
UTF8_BOM = b"\xef\xbb\xbf"


def test_scripts_exist():
    assert SCRIPTS, "no PowerShell scripts found to check"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_has_utf8_bom(script):
    assert script.read_bytes().startswith(UTF8_BOM), (
        f"{script.name} lacks a UTF-8 BOM; Windows PowerShell 5.1 will read "
        "it as ANSI and may fail to parse"
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_body_is_ascii_only(script):
    body = script.read_bytes()[len(UTF8_BOM):].decode("utf-8")
    offenders = sorted({c for c in body if ord(c) > 127})
    assert not offenders, (
        f"{script.name} contains non-ASCII {offenders}. Use '-' for dashes "
        "and 'section' for the section sign: these files must survive being "
        "read as ANSI."
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_quotes_are_balanced(script):
    """Cheap guard against the exact failure seen: an unterminated string."""
    body = script.read_bytes()[len(UTF8_BOM):].decode("utf-8")
    in_here_string = False
    for number, line in enumerate(body.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('@"') or stripped.endswith('@"'):
            in_here_string = True
            continue
        if stripped.startswith('"@'):
            in_here_string = False
            continue
        if in_here_string or stripped.startswith("#"):
            continue
        # Ignore escaped quotes, then count.
        cleaned = line.replace('`"', "").replace("''", "")
        if cleaned.count('"') % 2 != 0:
            pytest.fail(f"{script.name}:{number} has an odd number of double "
                        f"quotes: {line.strip()[:80]}")
