#!/usr/bin/env python3
"""Build the calculator dataset only after adversarial cross-validation.

The roster is the set supported by at least two current sources. Every unordered
parent pair must be returned identically by current PalworldSaveTools and the
PalDB-harvested table. For pairs also covered by PalCalc, PalCalc must agree.
The sole gender-dependent pair is represented as two conditional rows from the
game-data-derived PalCalc table.
"""
from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from typing import Any

import audit_breeding_sources as audit

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "palworld" / "data"

EXTRA_REPOS = {
    "localization": ("zaigie/palworld-server-tool", "web/src/assets/pal.json"),
    "guide": ("bowenchen-1/palworld-guide", "public/data/pals.json"),
    "icons": ("bowenchen-1/palworld-guide", "data/sources/palworld-icon-manifest.json"),
}


def resolve_file(repo: str, path: str) -> tuple[str, str, str]:
    branch, sha = audit.resolve(repo)
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
    return sha, url, audit.get(url)


def ci_map(mapping: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): value for key, value in mapping.items()}


def normalize_number(value: Any) -> tuple[int, str, str]:
    text = str(value or "").strip().upper()
    match = re.match(r"^0*(\d+)([A-Z]?)$", text)
    if not match:
        return 99999, "", text
    number = int(match.group(1))
    suffix = match.group(2)
    display = f"{number}{suffix}" if suffix else str(number)
    return number, suffix, display


def find_icon_source(node: Any, internal_id: str, english_name: str) -> str:
    target_values = {internal_id.lower(), english_name.lower()}
    found = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            string_values = {str(item).lower() for item in value.values() if isinstance(item, str)}
            if string_values & target_values:
                for key in ("source", "icon", "displayIcon", "displayIconFile"):
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate.startswith("http"):
                        found.append(candidate)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found[0] if found else ""


def main() -> None:
    texts, source_metadata = audit.load_all()
    palcalc = audit.load_palcalc(texts["palcalc.pals"], texts["palcalc.breeding"])
    pst = audit.load_pst(texts["pst.breeding"])
    paldeck = audit.load_paldeck(texts["paldeck.breeding"])

    extra_metadata = {}
    extra_texts = {}
    for label, (repo, path) in EXTRA_REPOS.items():
        sha, url, text = resolve_file(repo, path)
        extra_metadata[label] = {"repo": repo, "commit": sha, "path": path, "url": url, "sha256": audit.digest(text)}
        extra_texts[label] = text

    localization = json.loads(extra_texts["localization"])
    ja = ci_map(localization.get("ja", {}))
    guide_rows = json.loads(extra_texts["guide"])
    guide_by_name = {str(row.get("name") or "").lower(): row for row in guide_rows if isinstance(row, dict)}
    icon_manifest = json.loads(extra_texts["icons"])

    rosters = [set(palcalc["pals"]), set(pst["pals"]), set(paldeck["pals"])]
    union = set().union(*rosters)
    supported = sorted(pal_id for pal_id in union if sum(pal_id in roster for roster in rosters) >= 2)
    unsupported = sorted(union - set(supported))

    pals = []
    for pal_id in supported:
        pc = palcalc["pals"].get(pal_id, {})
        ps = pst["pals"].get(pal_id, {})
        pd = paldeck["pals"].get(pal_id, {})
        english = str(pd.get("name") or ps.get("name") or pc.get("name") or pal_id)
        japanese = str(ja.get(pal_id) or english)
        dex_raw = pd.get("dex", pc.get("dex", ""))
        number, suffix, display_no = normalize_number(dex_raw)
        guide = guide_by_name.get(english.lower(), {})
        icon = find_icon_source(icon_manifest, pal_id, english)
        pals.append({
            "id": pal_id,
            "en": english,
            "jp": japanese,
            "no": number,
            "suffix": suffix,
            "displayNo": display_no,
            "variant": bool(suffix),
            "power": int(ps.get("rank") or pc.get("rank") or guide.get("power") or 0),
            "rarity": int(ps.get("rarity") or guide.get("rarity") or 0),
            "ignoreCombi": bool(ps.get("ignoreCombi")),
            "elements": guide.get("elements") or [],
            "work": guide.get("work") or {},
            "slug": guide.get("slug") or "",
            "icon": icon,
            "sourceCoverage": sorted(name for name, roster in zip(("palcalc", "pst", "paldeck-paldb"), rosters) if pal_id in roster),
        })

    pals.sort(key=lambda pal: (pal["no"], pal["suffix"], pal["jp"], pal["id"]))
    pal_ids = {pal["id"] for pal in pals}
    expected_pairs = len(pals) * (len(pals) + 1) // 2
    gender_by_pair: dict[str, list[dict[str, Any]]] = {}
    for row in palcalc["genderRows"]:
        gender_by_pair.setdefault(audit.pkey(row["parent1"], row["parent2"]), []).append(row)

    rows = []
    pair_failures = []
    palcalc_failures = []
    gender_pairs = []
    for index, first in enumerate(pals):
        for second in pals[index:]:
            key = audit.pkey(first["id"], second["id"])
            pst_result = pst["pairs"].get(key)
            paldb_result = paldeck["pairs"].get(key)
            pc_result = palcalc["pairs"].get(key)

            if pst_result == paldb_result and pst_result and len(pst_result) == 1:
                child = next(iter(pst_result))
                if child not in pal_ids:
                    pair_failures.append({"pair": key, "reason": "child-outside-supported-roster", "child": child})
                    continue
                rows.append({"parent1": first["id"], "parent1Gender": "WILDCARD",
                             "parent2": second["id"], "parent2Gender": "WILDCARD", "child": child})
                if pc_result is not None and pc_result != {child}:
                    palcalc_failures.append({"pair": key, "palcalc": sorted(pc_result), "resolved": [child]})
                continue

            gender_rows = gender_by_pair.get(key, [])
            gender_children = {row["child"] for row in gender_rows}
            if (gender_rows and len(gender_rows) == 2 and pst_result == gender_children
                    and paldb_result and paldb_result <= gender_children):
                gender_pairs.append(key)
                for row in gender_rows:
                    rows.append({
                        "parent1": row["parent1"], "parent1Gender": row["parent1Gender"],
                        "parent2": row["parent2"], "parent2Gender": row["parent2Gender"], "child": row["child"],
                    })
                continue

            pair_failures.append({
                "pair": key,
                "pst": sorted(pst_result or []),
                "paldeckPalDB": sorted(paldb_result or []),
                "palcalc": sorted(pc_result or []),
                "genderRows": gender_rows,
            })

    represented_pairs = {audit.pkey(row["parent1"], row["parent2"]) for row in rows}
    if pair_failures:
        raise RuntimeError(f"Unresolved parent pairs: {pair_failures[:10]}")
    if palcalc_failures:
        raise RuntimeError(f"PalCalc conflicts on covered pairs: {palcalc_failures[:10]}")
    if len(represented_pairs) != expected_pairs:
        raise RuntimeError(f"Incomplete pair coverage: {len(represented_pairs)}/{expected_pairs}")
    if len(rows) != expected_pairs + len(gender_pairs):
        raise RuntimeError(f"Unexpected conditional-row count: {len(rows)}")
    if gender_pairs != [audit.pkey("catmage", "foxmage")]:
        raise RuntimeError(f"Unexpected gender-dependent pairs: {gender_pairs}")

    source_commits = {name: value["commit"] for name, value in source_metadata.items()}
    source_commits.update({name: value["commit"] for name, value in extra_metadata.items()})
    verification = {
        "schemaVersion": 1,
        "status": "cross-validated-current-game-data",
        "gameRuntimeExhaustiveVerification": False,
        "palCount": len(pals),
        "unorderedPairCount": expected_pairs,
        "resultRowCount": len(rows),
        "genderDependentPairs": gender_pairs,
        "unsupportedSingleSourceIds": unsupported,
        "sourceCommits": source_commits,
        "checks": {
            "pstPaldbAgreementExceptGenderPair": True,
            "palcalcAgreementForCoveredRoster": True,
            "allChildrenInsideSupportedRoster": True,
            "sameSpeciesCovered": True,
            "uniqueCombinationPrecedenceApplied": True,
            "ignoreCombiAppliedByPstExtraction": True,
        },
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "pals.verified.json").write_text(json.dumps({"pals": pals}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (DATA_DIR / "breeding.verified.json").write_text(json.dumps({"breeding": rows}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (DATA_DIR / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
