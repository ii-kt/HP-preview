#!/usr/bin/env python3
"""Fail-closed, adversarial audit of Palworld breeding sources.

The program resolves current revisions of three independent implementations,
reconstructs their effective parent-pair results, and refuses to call any source
authoritative. Raw source defects and effective results are audited separately.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "palworld" / "audit"
REPORT_PATH = OUT_DIR / "source-audit.json"
CONSENSUS_PATH = OUT_DIR / "consensus.json"
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
UA = "HP-preview-palworld-audit/4.0"

SPECS = {
    "palcalc": ("tylercamp/palcalc", {
        "pals": "PalCalc.GenDB/out-csv/pals.csv",
        "breeding": "PalCalc.Model/breeding.json",
        "reader": "PalCalc.GenDB/GameDataReaders/PalReader.cs",
        "calculator": "PalCalc.GenDB/PalBreedingCalculator.cs",
    }),
    "pst": ("deafdudecomputers/PalworldSaveTools", {
        "breeding": "resources/game_data/breedingdata.json",
        "generator": "scripts/scrs/update_game_data.py",
        "notes": ".opencode/skills/pst-breeding/SKILL.md",
        "ui": "src/palworld_aio/ui/tabs/breeding_tab.py",
    }),
    "paldeck": ("FearlessKenji/Paldeck", {
        "breeding": "data/palBreeding.json",
        "calculator": "utils/palBreeding.js",
        "updater": "scripts/update-palworld-breeding-results.js",
    }),
}


def get(url: str, *, json_accept: bool = False) -> str:
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json" if json_accept else "text/plain"}
    if TOKEN and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {TOKEN}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as response:
        return response.read().decode("utf-8-sig")


def get_json(url: str) -> Any:
    return json.loads(get(url, json_accept=True))


def resolve(repo: str) -> tuple[str, str]:
    branch = get_json(f"https://api.github.com/repos/{repo}")["default_branch"]
    sha = get_json(f"https://api.github.com/repos/{repo}/commits/{branch}")["sha"]
    return branch, sha


def canon(value: Any) -> str:
    return str(value or "").strip().lower()


def pkey(first: Any, second: Any) -> str:
    return "|".join(sorted((canon(first), canon(second))))


def add(table: dict[str, set[str]], first: Any, second: Any, child: Any) -> None:
    a, b, c = canon(first), canon(second), canon(child)
    if a and b and c:
        table.setdefault(pkey(a, b), set()).add(c)


def replace(table: dict[str, set[str]], first: Any, second: Any, child: Any) -> None:
    a, b, c = canon(first), canon(second), canon(child)
    if a and b and c:
        table[pkey(a, b)] = {c}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_all() -> tuple[dict[str, str], dict[str, Any]]:
    texts, metadata = {}, {}
    for source, (repo, files) in SPECS.items():
        branch, sha = resolve(repo)
        metadata[source] = {"repo": repo, "branch": branch, "commit": sha, "files": {}}
        for label, path in files.items():
            url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
            text = get(url)
            texts[f"{source}.{label}"] = text
            metadata[source]["files"][label] = {
                "path": path, "url": url, "bytes": len(text.encode()), "sha256": digest(text)
            }
    return texts, metadata


def load_palcalc(pals_text: str, breeding_text: str) -> dict[str, Any]:
    pals = {}
    for index, row in enumerate(csv.DictReader(io.StringIO(pals_text))):
        pal_id = canon(row.get("CodeName"))
        if pal_id:
            pals[pal_id] = {
                "name": row.get("Name"), "dex": int(row.get("PalDexNo") or -1),
                "rank": int(row.get("BreedPower") or 0), "index": int(row.get("IndexOrder") or index),
            }
    raw = json.loads(breeding_text)
    pairs, gender_rows = {}, []
    for row in raw.get("Breeding", []):
        add(pairs, row.get("Parent1InternalName"), row.get("Parent2InternalName"), row.get("ChildInternalName"))
        if row.get("Parent1Gender") != "WILDCARD" or row.get("Parent2Gender") != "WILDCARD":
            gender_rows.append({
                "parent1": canon(row.get("Parent1InternalName")), "parent1Gender": row.get("Parent1Gender"),
                "parent2": canon(row.get("Parent2InternalName")), "parent2Gender": row.get("Parent2Gender"),
                "child": canon(row.get("ChildInternalName")),
            })
    return {"pals": pals, "pairs": pairs, "genderRows": gender_rows, "rowCount": len(raw.get("Breeding", []))}


def child_map(raw: dict[str, Any], field: str) -> dict[str, set[str]]:
    result = {}
    for child, rows in raw.get(field, {}).items():
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                add(result, row.get("parent_a"), row.get("parent_b"), child)
    return result


def load_pst(text: str) -> dict[str, Any]:
    raw = json.loads(text)
    pals = {
        canon(key): {
            "name": value.get("name"), "rank": int(value.get("combi_rank") or 0),
            "rarity": int(value.get("rarity") or 0), "ignoreCombi": bool(value.get("ignore_combi")),
        }
        for key, value in raw.get("pal_info", {}).items() if isinstance(value, dict)
    }
    formula = child_map(raw, "child_to_parents_formula")
    ignore_formula = child_map(raw, "child_to_parents_ignore")
    unique_reverse = child_map(raw, "child_to_parents_unique")
    unique_direct = {}
    for row in raw.get("unique_combos", []):
        if isinstance(row, dict):
            add(unique_direct, row.get("parent_a"), row.get("parent_b"), row.get("child"))

    # Raw union exposes generator/UI overlap defects; resolved applies game-style precedence.
    raw_union = {}
    for source in (formula, ignore_formula, unique_reverse):
        for key, children in source.items():
            raw_union.setdefault(key, set()).update(children)

    resolved = {key: set(children) for key, children in formula.items()}
    for key, children in ignore_formula.items():
        resolved[key] = set(children)
    for key, children in unique_direct.items():
        resolved[key] = set(children)  # unique combinations override generic formula
    for pal_id in pals:
        resolved[pkey(pal_id, pal_id)] = {pal_id}  # same species is evaluated before unique/formula

    return {
        "pals": pals, "pairs": resolved, "rawPairs": raw_union,
        "formula": formula, "ignoreFormula": ignore_formula, "unique": unique_direct,
        "uniqueReverse": unique_reverse,
    }


def load_paldeck(text: str) -> dict[str, Any]:
    raw = json.loads(text)
    entries = list(raw.get("Pals", [])) + list(raw.get("SourceOnlyPals", []))
    name_to_id, pals = {}, {}
    for entry in entries:
        pal_id, name = canon(entry.get("breedingId")), str(entry.get("name") or "").strip()
        if pal_id and name:
            name_to_id[canon(name)] = pal_id
            pals[pal_id] = {
                "name": name, "dex": entry.get("number"), "rank": entry.get("breedingRank"),
                "canBeParent": bool(entry.get("canBeParent")), "canBeChild": bool(entry.get("canBeChild")),
                "canBeStandardChild": bool(entry.get("canBeStandardChild")),
            }
    pairs, unknown = {}, []
    for row in raw.get("PairResults", []):
        if isinstance(row, list) and len(row) >= 3:
            names = row[:3]
        elif isinstance(row, dict):
            names = [row.get("parentA"), row.get("parentB"), row.get("child")]
        else:
            continue
        ids = [name_to_id.get(canon(name), "") for name in names]
        if all(ids):
            add(pairs, *ids)
        else:
            unknown.append(names)
    return {
        "pals": pals, "pairs": pairs, "unknown": unknown,
        "metadata": raw.get("PairResultsMetadata", {}), "rowCount": len(raw.get("PairResults", [])),
    }


def compare(left: dict[str, set[str]], right: dict[str, set[str]], limit: int = 100) -> dict[str, Any]:
    lk, rk = set(left), set(right)
    common = sorted(lk & rk)
    mismatch = [{"pair": key, "left": sorted(left[key]), "right": sorted(right[key])}
                for key in common if left[key] != right[key]]
    return {
        "leftPairs": len(left), "rightPairs": len(right), "commonPairs": len(common),
        "matchingPairs": len(common) - len(mismatch), "mismatchCount": len(mismatch),
        "leftOnlyCount": len(lk-rk), "rightOnlyCount": len(rk-lk),
        "mismatchSample": mismatch[:limit], "leftOnlySample": sorted(lk-rk)[:limit],
        "rightOnlySample": sorted(rk-lk)[:limit],
    }


def same_species(pals: dict[str, Any], pairs: dict[str, set[str]]) -> dict[str, Any]:
    missing, wrong = [], []
    for pal_id in sorted(pals):
        result = pairs.get(pkey(pal_id, pal_id))
        if result is None:
            missing.append(pal_id)
        elif result != {pal_id}:
            wrong.append({"pal": pal_id, "results": sorted(result)})
    return {"missingCount": len(missing), "wrongResultCount": len(wrong),
            "missingSample": missing[:100], "wrongResultSample": wrong[:100]}


def classify(maps: dict[str, dict[str, set[str]]]) -> tuple[dict[str, list[str]], dict[str, Any]]:
    keys = sorted(set().union(*(set(table) for table in maps.values())))
    strict, available = {}, {}
    disputed, single = [], []
    partial_coverage = []
    for key in keys:
        present = {name: table[key] for name, table in maps.items() if key in table}
        groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for source, children in present.items():
            groups[tuple(sorted(children))].append(source)
        if len(present) == len(maps) and len(groups) == 1:
            strict[key] = list(next(iter(groups)))
            available[key] = strict[key]
        elif len(present) >= 2 and len(groups) == 1:
            available[key] = list(next(iter(groups)))
        elif len(present) >= 2:
            values = list(present.values())
            # One source may omit a gender-specific outcome while returning a valid subset.
            union = set().union(*values)
            if all(value <= union for value in values) and any(value < union for value in values):
                partial_coverage.append({"pair": key, "results": {k: sorted(v) for k, v in present.items()}})
            else:
                disputed.append({"pair": key, "results": {k: sorted(v) for k, v in present.items()}})
        else:
            single.append({"pair": key, "results": {k: sorted(v) for k, v in present.items()}})
    return strict, {
        "unionPairs": len(keys), "strictAllSourcePairs": len(strict),
        "nonDissentingAvailablePairs": len(available), "disputedPairs": len(disputed),
        "partialCoveragePairs": len(partial_coverage), "singleSourcePairs": len(single),
        "disputedSample": disputed[:200], "partialCoverageSample": partial_coverage[:200],
        "singleSourceSample": single[:200],
    }


def source_drift(texts: dict[str, str]) -> dict[str, Any]:
    generator, notes, ui = texts["pst.generator"], texts["pst.notes"], texts["pst.ui"]
    reader, calculator = texts["palcalc.reader"], texts["palcalc.calculator"]
    return {
        "pst": {
            "readsIgnoreCombi": "IgnoreCombi" in generator,
            "excludesUniqueChildren": "unique_child_tribes" in generator and "candidate_pool" in generator,
            "generatorUsesHigherRankDistanceTie": bool(re.search(r"diff\s*==\s*best_diff[^\n]+\['rank'\]\s*>\s*best\['rank'\]", generator)),
            "notesClaimRarityTie": "rarity" in notes.lower() and "tiebreaker" in notes.lower(),
            "documentationConflict": "rarity" in notes.lower() and "tiebreaker" in notes.lower()
                and bool(re.search(r"diff\s*==\s*best_diff[^\n]+\['rank'\]\s*>\s*best\['rank'\]", generator)),
            "uiListsUniqueBeforeFormula": "('unique', bd.get('child_to_parents_unique'" in ui,
            "uiChildModeCanExposeOverlappingResults": "children_map.setdefault" in ui,
        },
        "palcalc": {
            "readerReadsIgnoreCombi": "IgnoreCombi" in reader,
            "readerReadsDuplicatePriority": "CombiDuplicatePriority" in reader,
            "sameSpeciesFirst": "if (parent1.Pal == parent2.Pal)" in calculator,
            "uniqueBeforeFormula": "if (specialCombo.Any())" in calculator,
            "excludesUniqueChildrenFromFormula": ".Where(p => !uniqueCombos.Any(c => p == c.Child))" in calculator,
            "usesDuplicatePriority": "ThenByDescending(p => p.BreedingPowerPriority)" in calculator,
        },
    }


def main() -> None:
    texts, metadata = load_all()
    palcalc = load_palcalc(texts["palcalc.pals"], texts["palcalc.breeding"])
    pst = load_pst(texts["pst.breeding"])
    paldeck = load_paldeck(texts["paldeck.breeding"])
    maps = {"palcalc": palcalc["pairs"], "pst-resolved": pst["pairs"], "paldeck-paldb": paldeck["pairs"]}
    strict, consensus = classify(maps)

    roster_sets = {"palcalc": set(palcalc["pals"]), "pst": set(pst["pals"]), "paldeck": set(paldeck["pals"])}
    union = sorted(set().union(*roster_sets.values()))
    intersection = sorted(set.intersection(*roster_sets.values()))
    presence = Counter(sum(pal in roster for roster in roster_sets.values()) for pal in union)
    supported = sorted(pal for pal in union if sum(pal in roster for roster in roster_sets.values()) >= 2)

    report = {
        "schemaVersion": 4, "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "policy": {"authoritativeSource": None, "gameRuntimeVerified": False, "failClosed": True,
                   "strictConsensusRule": "All three effective source tables contain the pair and return the same child set"},
        "sourceMetadata": metadata,
        "sourcesSummary": {
            "palcalc": {"palCount": len(palcalc["pals"]), "pairCount": len(palcalc["pairs"]),
                        "rowCount": palcalc["rowCount"], "genderSpecificRows": len(palcalc["genderRows"])},
            "pst": {"palCount": len(pst["pals"]), "resolvedPairCount": len(pst["pairs"]),
                    "rawUnionPairCount": len(pst["rawPairs"]), "ignoreCombiCount": sum(p["ignoreCombi"] for p in pst["pals"].values()),
                    "formulaPairs": len(pst["formula"]), "ignoreFormulaPairs": len(pst["ignoreFormula"]),
                    "uniquePairs": len(pst["unique"]), "uniqueReverseIntegrity": compare(pst["unique"], pst["uniqueReverse"], 25)},
            "paldeck": {"palCount": len(paldeck["pals"]), "pairCount": len(paldeck["pairs"]),
                        "rowCount": paldeck["rowCount"], "unknownRows": len(paldeck["unknown"]), "metadata": paldeck["metadata"]},
        },
        "roster": {"unionCount": len(union), "intersectionCount": len(intersection), "supportedByAtLeastTwoCount": len(supported),
                   "presenceBySourceCount": {str(k): v for k, v in sorted(presence.items())},
                   "supportedByAtLeastTwo": supported,
                   "singleSourceOnly": {name: sorted(roster - set().union(*(v for k, v in roster_sets.items() if k != name)))
                                        for name, roster in roster_sets.items()}},
        "comparisons": {
            "palcalcVsPstResolved": compare(palcalc["pairs"], pst["pairs"]),
            "palcalcVsPaldeckPalDB": compare(palcalc["pairs"], paldeck["pairs"]),
            "pstResolvedVsPaldeckPalDB": compare(pst["pairs"], paldeck["pairs"]),
            "pstRawVsResolved": compare(pst["rawPairs"], pst["pairs"]),
        },
        "sameSpecies": {"palcalc": same_species(palcalc["pals"], palcalc["pairs"]),
                        "pstRaw": same_species(pst["pals"], pst["rawPairs"]),
                        "pstResolved": same_species(pst["pals"], pst["pairs"]),
                        "paldeck": same_species(paldeck["pals"], paldeck["pairs"])},
        "sourceDrift": source_drift(texts), "consensus": consensus,
        "genderSpecificPalcalcRows": palcalc["genderRows"],
    }
    consensus_file = {
        "schemaVersion": 2, "generatedAt": report["generatedAt"],
        "status": "strict-three-source-consensus-not-game-runtime-verified", "failClosed": True,
        "sourceCommits": {name: data["commit"] for name, data in metadata.items()},
        "pairCount": len(strict), "pairs": strict,
    }
    if consensus_file["pairCount"] != len(consensus_file["pairs"]):
        raise RuntimeError("Consensus count mismatch")
    if not all(children for children in strict.values()):
        raise RuntimeError("Empty consensus child set")
    if any(summary.get("pairCount", summary.get("resolvedPairCount", 0)) <= 0 for summary in report["sourcesSummary"].values()):
        raise RuntimeError("A source produced no pairs")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CONSENSUS_PATH.write_text(json.dumps(consensus_file, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"sourcePairs": {k: len(v) for k, v in maps.items()}, "consensus": consensus,
                      "roster": {"union": len(union), "intersection": len(intersection), "supported": len(supported)},
                      "sourceDrift": report["sourceDrift"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise SystemExit(f"HTTP {error.code}: {detail[:1000]}") from error
