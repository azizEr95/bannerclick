"""D) Decodes TC strings with the official IAB Tech Lab library @iabtechlabtcf/core (Node).

Why this library: it is maintained by the IAB Tech Lab itself, follows the TCF v2.2 spec and is
used by CMPs; Python decoders for TCF v2.2 are not comparably maintained. Setup once:
    cd tcfmeasure/tcstring && npm ci

decode_many(["CQ...", ...]) -> list of dicts (fields see decode.mjs), same order as the input.
"""
import json
import subprocess
from pathlib import Path

DECODER = Path(__file__).parent / "decode.mjs"
LIBRARY = Path(__file__).parent / "node_modules" / "@iabtechlabtcf" / "core" / "package.json"


def library_version():
    return json.loads(LIBRARY.read_text())["version"] if LIBRARY.exists() else None


def decode_many(tc_strings):
    if not tc_strings:
        return []
    if not LIBRARY.exists():
        raise RuntimeError("@iabtechlabtcf/core missing: run `npm ci` in tcfmeasure/tcstring")
    output = subprocess.run(["node", str(DECODER)], input="\n".join(tc_strings), text=True,
                            capture_output=True, check=True).stdout
    return [json.loads(line) for line in output.splitlines()]
