#!/usr/bin/env python3
"""Audit current Palworld breeding datasets without assuming any source is correct.

The script downloads pinned snapshots from three independent implementations:
- PalCalc: game-PAK extraction + generated breeding table
- PalworldSaveTools: exported game tables + independent formula/known in-game tests
- Paldeck: exhaustive pair results harvested from PalDB endpoints

It writes a compact machine-readable report used by later build/review iterations.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "palworld" / "audit" / "source-audit.json"

SOURCES = {
    "palcalc_pals": "https://raw.githubusercontent.com/tylercamp/palcalc/8b7e2f779e47fddae16ddcb973e828ba20c02b80/PalCalc.GenDB/out-csv/pals.csv",
    "palcalc_breeding": "https://raw.githubusercontent.com/tylercamp/palcalc/8b7e2f779e47fddae16ddcb973e828ba20c02b80/PalCalc.Model/breeding.json",
    "pst_breeding": "https://raw.githubusercontent.com/deafdudecomputers/PalworldSaveTools/4a4e63c45ea4d57a9dfbd82031bdc226b722ff90/resources/game_data/breedingdata.json",
    "paldeck_breeding": "https://raw.githubusercontent.com/FearlessKenji/Paldeck/073a1b0376e2005fc5cb09226544cf3fbd75eeee/data/palBreeding.json",
}


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "HP-preview-palworld-audit/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read().decode("utf-8-sig")


def canonical_id(value: Any) -> str:
    return str(value or "").strip().lower()


def pair_key(a: str, b: str) -> str:
    return "|".join(sorted((canonical_id(a), canonical_id(b))))


def describe(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"type": type(value).__name__}
    if isinstance(value, (dict, list)):
        result["count"] = len(value)
    if isinstance(value, dict):
        result["keysSample"] = list(value.keys())[:12]
    elif isinstance(value, list):
        result["sample"] = value[:2]
    return result


def load_palcalc(pals_text: str, breeding_text: str) -> dict[str, Any]:
    rows = list(csv.DictReader(io.StringIO(pals_text)))
    code_to_name = {canonical_id(r["CodeName"]): r["Name"] for r in rows}
    code_to_no = {canonical_id(r["CodeName"]): r["PalDexNo"] for r in rows}
    raw = json.loads(breeding_text)
    pair_results: dict[str, set[str]] = {}
    gendered_rows = 0
    skipped = 0
    for row in raw.get("Breeding", []):
        p1 = canonical_id(row.get("Parent1InternalName"))
        p2 = canonical_id(row.get("Parent2InternalName"))
        child = canonical_id(row.get("ChildInternalName"))
        if not p1 or not p2 or not child:
            skipped += 1
            continue
        pair_results.setdefault(pair_key(p1, p2), set()).add(child)
        if row.get("Parent1Gender") != "WILDCARD" or row.get("Parent2Gender") != "WILDCARD":
            gendered_rows += 1
    return {
        "palCount": len(rows),
        "pairCount": len(pair_results),
        "rowCount": len(raw.get("Breeding", [])),
        "genderedRowCount": gendered_rows,
        "skippedRows": skipped,
        "codeToName": code_to_name,
        "codeToNo": code_to_no,
        "pairResults": pair_results,
    }


def load_paldeck(text: str) -> dict[str, Any]:
    raw = json.loads(text)
    all_pals = list(raw.get("Pals", [])) + list(raw.get("SourceOnlyPals", []))
    name_to_id = {canonical_id(p.get("name")): canonical_id(p.get("breedingId")) for p in all_pals}
    id_to_name = {canonical_id(p.get("breedingId")): p.get("name") for p in all_pals if p.get("breedingId")}
    pair_results: dict[str, set[str]] = {}
    unknown = []
    for row in raw.get("PairResults", []):
        if isinstance(row, list) and len(row) >= 3:
            n1, n2, nc = row[:3]
        elif isinstance(row, dict):
            n1, n2, nc = row.get("parentA"), row.get("parentB"), row.get("child")
        else:
            continue
        p1 = name_to_id.get(canonical_id(n1), "")
        p2 = name_to_id.get(canonical_id(n2), "")
        child = name_to_id.get(canonical_id(nc), "")
        if not p1 or not p2 or not child:
            unknown.append([n1, n2, nc])
            continue
        pair_results.setdefault(pair_key(p1, p2), set()).add(child)
    return {
        "palCount": len(all_pals),
        "parentCount": sum(bool(p.get("canBeParent")) for p in all_pals),
        "childCount": sum(bool(p.get("canBeChild")) for p in all_pals),
        "standardChildCount": sum(bool(p.get("canBeStandardChild")) for p in all_pals),
        "pairCount": len(pair_results),
        "pairRows": len(raw.get("PairResults", [])),
        "pairResultsMetadata": raw.get("PairResultsMetadata", {}),
        "unknownPairRows": unknown[:50],
        "idToName": id_to_name,
        "pairResults": pair_results,
        "topLevel": {key: describe(value) for key, value in raw.items()},
    }


def compare_pair_maps(left: dict[str, set[str]], right: dict[str, set[str]]) -> dict[str, Any]:
    common = sorted(set(left) & set(right))
    mismatches = []
    for key in common:
        if left[key] != right[key]:
            mismatches.append({"pair": key, "left": sorted(left[key]), "right": sorted(right[key])})
    return {
        "leftPairs": len(left),
        "rightPairs": len(right),
        "commonPairs": len(common),
        "matchingPairs": len(common) - len(mismatches),
        "mismatchCount": len(mismatches),
        "leftOnlyCount": len(set(left) - set(right)),
        "rightOnlyCount": len(set(right) - set(left)),
        "mismatchSample": mismatches[:100],
    }


def lookup(pair_map: dict[str, set[str]], first: str, second: str) -> list[str]:
    return sorted(pair_map.get(pair_key(first, second), set()))


def main() -> None:
    texts = {name: fetch_text(url) for name, url in SOURCES.items()}
    palcalc = load_palcalc(texts["palcalc_pals"], texts["palcalc_breeding"])
    paldeck = load_paldeck(texts["paldeck_breeding"])
    pst_raw = json.loads(texts["pst_breeding"])

    known_pairs = [
        ("sheepball", "pinkcat"),
        ("sheepball", "chickenpal"),
        ("alpaca", "anubis"),
        ("plesiosaur", "thunderfluffybird"),
        ("blueskydragon", "hadesbird_electric"),
        ("chickenpal", "yakushimaboss001"),
    ]
    known = []
    for first, second in known_pairs:
        known.append({
            "pair": [first, second],
            "palcalc": lookup(palcalc["pairResults"], first, second),
            "paldeckPalDB": lookup(paldeck["pairResults"], first, second),
        })

    report = {
        "schemaVersion": 1,
        "sources": SOURCES,
        "palcalc": {k: v for k, v in palcalc.items() if k not in {"pairResults", "codeToName", "codeToNo"}},
        "paldeckPalDB": {k: v for k, v in paldeck.items() if k not in {"pairResults", "idToName"}},
        "palworldSaveTools": {
            "topLevel": {key: describe(value) for key, value in pst_raw.items()},
            "palInfoCount": len(pst_raw.get("pal_info", {})),
            "ignoreCombiCount": sum(bool(v.get("ignore_combi")) for v in pst_raw.get("pal_info", {}).values() if isinstance(v, dict)),
            "ignoreCombiSample": [
                {"id": key, **value}
                for key, value in pst_raw.get("pal_info", {}).items()
                if isinstance(value, dict) and value.get("ignore_combi")
            ][:40],
        },
        "palcalcVsPaldeckPalDB": compare_pair_maps(palcalc["pairResults"], paldeck["pairResults"]),
        "knownPairs": known,
        "sourcePayloadBytes": {key: len(value.encode("utf-8")) for key, value in texts.items()},
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUT.relative_to(ROOT)),
        "palcalcPairs": palcalc["pairCount"],
        "paldeckPairs": paldeck["pairCount"],
        "mismatches": report["palcalcVsPaldeckPalDB"]["mismatchCount"],
        "pstKeys": list(pst_raw.keys()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
