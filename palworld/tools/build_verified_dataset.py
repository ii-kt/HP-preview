#!/usr/bin/env python3
"""Build a compact, cross-validated Palworld breeding dataset.

The roster is supported by at least two current sources. Every unordered parent
pair must agree between current PalworldSaveTools and the PalDB-harvested table.
PalCalc must agree wherever its roster overlaps, except that its two explicit
gender conditions are retained for the sole gender-dependent pair.

The output stores one child index per upper-triangular parent pair. Gender-
dependent rows replace, rather than supplement, the matrix result at runtime.
"""
from __future__ import annotations

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
}


def resolve_file(repo: str, path: str) -> tuple[str, str, str]:
    _, sha = audit.resolve(repo)
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
    return sha, url, audit.get(url)


def ci_map(mapping: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): value for key, value in mapping.items()}


def normalize_number(value: Any) -> tuple[int, str, str]:
    text = str(value or "").strip().upper()
    match = re.match(r"^0*(\d+)([A-Z]?)$", text)
    if not match:
        return 99999, "", text
    number, suffix = int(match.group(1)), match.group(2)
    return number, suffix, f"{number}{suffix}" if suffix else str(number)


def pair_index(size: int, first: int, second: int) -> int:
    """Return the upper-triangular row-major index for first <= second."""
    if first > second:
        first, second = second, first
    return first * size - first * (first - 1) // 2 + (second - first)


def main() -> None:
    texts, source_metadata = audit.load_all()
    palcalc = audit.load_palcalc(texts["palcalc.pals"], texts["palcalc.breeding"])
    pst = audit.load_pst(texts["pst.breeding"])
    paldeck = audit.load_paldeck(texts["paldeck.breeding"])

    extra_metadata, extra_texts = {}, {}
    for label, (repo, path) in EXTRA_REPOS.items():
        sha, url, text = resolve_file(repo, path)
        extra_metadata[label] = {
            "repo": repo,
            "commit": sha,
            "path": path,
            "url": url,
            "sha256": audit.digest(text),
        }
        extra_texts[label] = text

    ja = ci_map(json.loads(extra_texts["localization"]).get("ja", {}))
    guide_rows = json.loads(extra_texts["guide"])
    guide_by_name = {
        str(row.get("name") or "").strip().lower(): row
        for row in guide_rows
        if isinstance(row, dict)
    }

    roster_names = ("palcalc", "pst", "paldeck-paldb")
    rosters = [set(palcalc["pals"]), set(pst["pals"]), set(paldeck["pals"])]
    union = set().union(*rosters)
    supported = sorted(
        pal_id for pal_id in union
        if sum(pal_id in roster for roster in rosters) >= 2
    )
    unsupported = sorted(union - set(supported))

    pals = []
    for pal_id in supported:
        pc = palcalc["pals"].get(pal_id, {})
        ps = pst["pals"].get(pal_id, {})
        pd = paldeck["pals"].get(pal_id, {})
        english = str(pd.get("name") or ps.get("name") or pc.get("name") or pal_id).strip()
        japanese = str(ja.get(pal_id) or english).strip()
        number, suffix, display_no = normalize_number(pd.get("dex", pc.get("dex", "")))
        guide = guide_by_name.get(english.lower(), {})
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
            "icon": "",
            "sourceCoverage": sorted(
                name for name, roster in zip(roster_names, rosters)
                if pal_id in roster
            ),
        })

    pals.sort(key=lambda pal: (pal["no"], pal["suffix"], pal["jp"], pal["id"]))
    pal_order = [pal["id"] for pal in pals]
    pal_index = {pal_id: index for index, pal_id in enumerate(pal_order)}
    pal_ids = set(pal_order)
    expected_pairs = len(pals) * (len(pals) + 1) // 2

    gender_by_pair: dict[str, list[dict[str, Any]]] = {}
    for row in palcalc["genderRows"]:
        gender_by_pair.setdefault(
            audit.pkey(row["parent1"], row["parent2"]), []
        ).append(row)

    children: list[int] = []
    gender_overrides: list[dict[str, Any]] = []
    pair_failures: list[dict[str, Any]] = []
    palcalc_failures: list[dict[str, Any]] = []

    for first_index, first in enumerate(pals):
        for second_index in range(first_index, len(pals)):
            second = pals[second_index]
            key = audit.pkey(first["id"], second["id"])
            pst_result = pst["pairs"].get(key)
            paldb_result = paldeck["pairs"].get(key)
            pc_result = palcalc["pairs"].get(key)
            matrix_index = len(children)
            expected_index = pair_index(len(pals), first_index, second_index)
            if matrix_index != expected_index:
                raise RuntimeError(
                    f"Triangular index mismatch: {matrix_index}/{expected_index}"
                )

            if pst_result == paldb_result and pst_result and len(pst_result) == 1:
                child = next(iter(pst_result))
                if child not in pal_ids:
                    pair_failures.append({
                        "pair": key,
                        "reason": "child-outside-supported-roster",
                        "child": child,
                    })
                    children.append(-1)
                    continue
                children.append(pal_index[child])
                if pc_result is not None and pc_result != {child}:
                    palcalc_failures.append({
                        "pair": key,
                        "palcalc": sorted(pc_result),
                        "resolved": [child],
                    })
                continue

            gender_rows = gender_by_pair.get(key, [])
            gender_children = {row["child"] for row in gender_rows}
            if (
                len(gender_rows) == 2
                and pst_result == gender_children
                and paldb_result
                and paldb_result <= gender_children
                and gender_children <= pal_ids
            ):
                # Matrix placeholder is never displayed; the override replaces it.
                preferred = next(iter(sorted(paldb_result or gender_children)))
                children.append(pal_index[preferred])
                override_rows = []
                for row in sorted(
                    gender_rows,
                    key=lambda item: (
                        item["parent1"], item["parent1Gender"],
                        item["parent2"], item["parent2Gender"], item["child"],
                    ),
                ):
                    override_rows.append({
                        "parent1": pal_index[row["parent1"]],
                        "parent1Gender": row["parent1Gender"],
                        "parent2": pal_index[row["parent2"]],
                        "parent2Gender": row["parent2Gender"],
                        "child": pal_index[row["child"]],
                    })
                gender_overrides.append({
                    "pairIndex": matrix_index,
                    "pair": [first_index, second_index],
                    "rows": override_rows,
                })
                continue

            pair_failures.append({
                "pair": key,
                "pst": sorted(pst_result or []),
                "paldeckPalDB": sorted(paldb_result or []),
                "palcalc": sorted(pc_result or []),
                "genderRows": gender_rows,
            })
            children.append(-1)

    if pair_failures:
        raise RuntimeError(f"Unresolved parent pairs: {pair_failures[:10]}")
    if palcalc_failures:
        raise RuntimeError(
            f"PalCalc conflicts on covered pairs: {palcalc_failures[:10]}"
        )
    if len(children) != expected_pairs:
        raise RuntimeError(
            f"Incomplete compact matrix: {len(children)}/{expected_pairs}"
        )
    if any(index < 0 or index >= len(pals) for index in children):
        raise RuntimeError("Invalid child index in compact matrix")
    if len(gender_overrides) != 1:
        raise RuntimeError(
            f"Unexpected gender-dependent pair count: {len(gender_overrides)}"
        )
    gender_pair_ids = [
        audit.pkey(
            pal_order[override["pair"][0]],
            pal_order[override["pair"][1]],
        )
        for override in gender_overrides
    ]
    if gender_pair_ids != [audit.pkey("catmage", "foxmage")]:
        raise RuntimeError(f"Unexpected gender-dependent pairs: {gender_pair_ids}")
    if any(
        not pal["jp"] or not pal["en"] or pal["power"] <= 0
        for pal in pals
    ):
        raise RuntimeError("Invalid Pal metadata")

    source_commits = {
        name: value["commit"] for name, value in source_metadata.items()
    }
    source_commits.update({
        name: value["commit"] for name, value in extra_metadata.items()
    })
    logical_rows = expected_pairs + sum(
        len(override["rows"]) - 1 for override in gender_overrides
    )
    verification = {
        "schemaVersion": 3,
        "status": "cross-validated-current-game-data",
        "gameRuntimeExhaustiveVerification": False,
        "palCount": len(pals),
        "unorderedPairCount": expected_pairs,
        "compactChildCount": len(children),
        "resultRowCount": logical_rows,
        "genderDependentPairs": gender_pair_ids,
        "unsupportedSingleSourceIds": unsupported,
        "sourceCommits": source_commits,
        "checks": {
            "pstPaldbAgreementExceptGenderPair": True,
            "palcalcAgreementForCoveredRoster": True,
            "allChildrenInsideSupportedRoster": True,
            "sameSpeciesCovered": True,
            "uniqueCombinationPrecedenceApplied": True,
            "ignoreCombiAppliedByPstExtraction": True,
            "displayNamesTrimmed": True,
            "invalidExternalIconUrlsExcluded": True,
            "compactMatrixRoundTripValidated": True,
        },
    }

    compact = {
        "schemaVersion": 1,
        "palOrder": pal_order,
        "children": children,
        "genderOverrides": gender_overrides,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "pals.verified.json").write_text(
        json.dumps({"pals": pals}, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (DATA_DIR / "breeding.verified.json").write_text(
        json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (DATA_DIR / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
