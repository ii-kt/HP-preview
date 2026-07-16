#!/usr/bin/env python3
"""Adversarial audit of Palworld breeding data sources.

No third-party source is treated as authoritative. The audit resolves the current
GitHub revision of each implementation, reconstructs its parent-pair table, and
classifies every pair as unanimous, disputed, or insufficiently evidenced.

Outputs:
- palworld/audit/source-audit.json: detailed machine-readable findings
- palworld/audit/consensus.json: only pairs with at least two agreeing sources
  and no dissenting source

The consensus file is deliberately fail-closed. It is not labelled as an
official or fully game-verified table.
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
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / "palworld" / "audit"
REPORT_OUT = AUDIT_DIR / "source-audit.json"
CONSENSUS_OUT = AUDIT_DIR / "consensus.json"

SOURCE_SPECS = {
    "palcalc": {
        "repo": "tylercamp/palcalc",
        "ref": "HEAD",
        "files": {
            "pals": "PalCalc.GenDB/out-csv/pals.csv",
            "breeding": "PalCalc.Model/breeding.json",
            "reader": "PalCalc.GenDB/GameDataReaders/PalReader.cs",
            "calculator": "PalCalc.GenDB/PalBreedingCalculator.cs",
        },
    },
    "pst": {
        "repo": "deafdudecomputers/PalworldSaveTools",
        "ref": "HEAD",
        "files": {
            "breeding": "resources/game_data/breedingdata.json",
            "generator": "scripts/scrs/update_game_data.py",
            "notes": ".opencode/skills/pst-breeding/SKILL.md",
        },
    },
    "paldeck": {
        "repo": "FearlessKenji/Paldeck",
        "ref": "HEAD",
        "files": {
            "breeding": "data/palBreeding.json",
            "calculator": "utils/palBreeding.js",
            "updater": "scripts/update-palworld-breeding-results.js",
        },
    },
}

USER_AGENT = "HP-preview-palworld-audit/3.0"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()


def request_text(url: str, *, accept: str = "text/plain", timeout: int = 180) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if GITHUB_TOKEN and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")


def request_json(url: str) -> Any:
    return json.loads(request_text(url, accept="application/vnd.github+json"))


def resolve_sha(repo: str, ref: str) -> tuple[str, str]:
    if ref != "HEAD":
        payload = request_json(f"https://api.github.com/repos/{repo}/commits/{ref}")
        return payload["sha"], ref
    repo_payload = request_json(f"https://api.github.com/repos/{repo}")
    branch = repo_payload["default_branch"]
    commit_payload = request_json(f"https://api.github.com/repos/{repo}/commits/{branch}")
    return commit_payload["sha"], branch


def raw_url(repo: str, sha: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_id(value: Any) -> str:
    value = str(value or "").strip().lower()
    aliases = {
        "blueplatypus": "blueplatypus",
        "blueplatypus_fire": "blueplatypus_fire",
    }
    return aliases.get(value, value)


def pair_key(first: str, second: str) -> str:
    return "|".join(sorted((canonical_id(first), canonical_id(second))))


def add_result(target: dict[str, set[str]], first: Any, second: Any, child: Any) -> None:
    first_id = canonical_id(first)
    second_id = canonical_id(second)
    child_id = canonical_id(child)
    if first_id and second_id and child_id:
        target.setdefault(pair_key(first_id, second_id), set()).add(child_id)


def public_pair_map(pair_map: dict[str, set[str]]) -> dict[str, list[str]]:
    return {key: sorted(values) for key, values in sorted(pair_map.items())}


def describe_payload(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"type": type(value).__name__}
    if isinstance(value, (dict, list)):
        result["count"] = len(value)
    if isinstance(value, dict):
        result["keysSample"] = list(value)[:20]
    return result


def load_palcalc(pals_text: str, breeding_text: str) -> dict[str, Any]:
    rows = list(csv.DictReader(io.StringIO(pals_text)))
    pals: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        code = canonical_id(row.get("CodeName"))
        if not code:
            continue
        pals[code] = {
            "id": code,
            "name": row.get("Name", ""),
            "dex": int(row.get("PalDexNo") or -1),
            "variant": row.get("IsVariant") == "True",
            "rank": int(row.get("BreedPower") or 0),
            "maleProbability": int(row.get("MaleProbability") or 0),
            "index": int(row.get("IndexOrder") or index),
        }

    raw = json.loads(breeding_text)
    pairs: dict[str, set[str]] = {}
    gender_rows: list[dict[str, Any]] = []
    malformed = 0
    for row in raw.get("Breeding", []):
        first = row.get("Parent1InternalName")
        second = row.get("Parent2InternalName")
        child = row.get("ChildInternalName")
        if not first or not second or not child:
            malformed += 1
            continue
        add_result(pairs, first, second, child)
        if row.get("Parent1Gender") != "WILDCARD" or row.get("Parent2Gender") != "WILDCARD":
            gender_rows.append({
                "parent1": canonical_id(first),
                "parent1Gender": row.get("Parent1Gender"),
                "parent2": canonical_id(second),
                "parent2Gender": row.get("Parent2Gender"),
                "child": canonical_id(child),
            })

    return {
        "pals": pals,
        "pairs": pairs,
        "genderRows": gender_rows,
        "rawRowCount": len(raw.get("Breeding", [])),
        "malformedRows": malformed,
    }


def load_pst(text: str) -> dict[str, Any]:
    raw = json.loads(text)
    info_raw = raw.get("pal_info", {})
    pals: dict[str, dict[str, Any]] = {}
    for pal_id, value in info_raw.items():
        if not isinstance(value, dict):
            continue
        canonical = canonical_id(pal_id)
        pals[canonical] = {
            "id": canonical,
            "name": value.get("name", pal_id),
            "rank": int(value.get("combi_rank") or 0),
            "rarity": int(value.get("rarity") or 0),
            "ignoreCombi": bool(value.get("ignore_combi")),
        }

    pairs: dict[str, set[str]] = {}
    category_rows: Counter[str] = Counter()

    def invert_child_map(field: str, category: str) -> None:
        value = raw.get(field, {})
        if not isinstance(value, dict):
            return
        for child, parent_rows in value.items():
            if not isinstance(parent_rows, list):
                continue
            for row in parent_rows:
                if not isinstance(row, dict):
                    continue
                first = row.get("parent_a")
                second = row.get("parent_b")
                if first and second:
                    add_result(pairs, first, second, child)
                    category_rows[category] += 1

    invert_child_map("child_to_parents_formula", "formula")
    invert_child_map("child_to_parents_unique", "unique")
    invert_child_map("child_to_parents_ignore", "ignore-parent-formula")

    # Unique combos are also read directly to detect inconsistent reverse indexes.
    direct_unique: dict[str, set[str]] = {}
    for row in raw.get("unique_combos", []):
        if not isinstance(row, dict):
            continue
        add_result(direct_unique, row.get("parent_a"), row.get("parent_b"), row.get("child"))

    reverse_unique = {}
    for child, parent_rows in raw.get("child_to_parents_unique", {}).items():
        for row in parent_rows if isinstance(parent_rows, list) else []:
            if isinstance(row, dict):
                add_result(reverse_unique, row.get("parent_a"), row.get("parent_b"), child)

    return {
        "pals": pals,
        "pairs": pairs,
        "raw": raw,
        "categoryRows": dict(category_rows),
        "uniqueIndexMismatch": compare_maps(direct_unique, reverse_unique, sample_limit=25),
    }


def load_paldeck(text: str) -> dict[str, Any]:
    raw = json.loads(text)
    all_pals = list(raw.get("Pals", [])) + list(raw.get("SourceOnlyPals", []))
    pals: dict[str, dict[str, Any]] = {}
    name_to_id: dict[str, str] = {}
    for pal in all_pals:
        pal_id = canonical_id(pal.get("breedingId"))
        name = str(pal.get("name") or "").strip()
        if not pal_id or not name:
            continue
        name_to_id[canonical_id(name)] = pal_id
        pals[pal_id] = {
            "id": pal_id,
            "name": name,
            "dex": pal.get("number"),
            "rank": pal.get("breedingRank"),
            "canBeParent": bool(pal.get("canBeParent")),
            "canBeChild": bool(pal.get("canBeChild")),
            "canBeStandardChild": bool(pal.get("canBeStandardChild")),
            "sourceOnly": pal in raw.get("SourceOnlyPals", []),
        }

    pairs: dict[str, set[str]] = {}
    unknown: list[Any] = []
    for row in raw.get("PairResults", []):
        if isinstance(row, list) and len(row) >= 3:
            first_name, second_name, child_name = row[:3]
        elif isinstance(row, dict):
            first_name, second_name, child_name = row.get("parentA"), row.get("parentB"), row.get("child")
        else:
            continue
        first = name_to_id.get(canonical_id(first_name))
        second = name_to_id.get(canonical_id(second_name))
        child = name_to_id.get(canonical_id(child_name))
        if not first or not second or not child:
            unknown.append([first_name, second_name, child_name])
            continue
        add_result(pairs, first, second, child)

    return {
        "pals": pals,
        "pairs": pairs,
        "unknownPairRows": unknown,
        "metadata": raw.get("PairResultsMetadata", {}),
        "rawPairRowCount": len(raw.get("PairResults", [])),
        "topLevel": {key: describe_payload(value) for key, value in raw.items()},
    }


def compare_maps(
    left: dict[str, set[str]],
    right: dict[str, set[str]],
    *,
    sample_limit: int = 100,
) -> dict[str, Any]:
    left_keys = set(left)
    right_keys = set(right)
    common = sorted(left_keys & right_keys)
    mismatches = [
        {"pair": key, "left": sorted(left[key]), "right": sorted(right[key])}
        for key in common
        if left[key] != right[key]
    ]
    return {
        "leftPairs": len(left),
        "rightPairs": len(right),
        "commonPairs": len(common),
        "matchingPairs": len(common) - len(mismatches),
        "mismatchCount": len(mismatches),
        "leftOnlyCount": len(left_keys - right_keys),
        "rightOnlyCount": len(right_keys - left_keys),
        "mismatchSample": mismatches[:sample_limit],
        "leftOnlySample": sorted(left_keys - right_keys)[:sample_limit],
        "rightOnlySample": sorted(right_keys - left_keys)[:sample_limit],
    }


def same_species_audit(source_name: str, pals: dict[str, Any], pairs: dict[str, set[str]]) -> dict[str, Any]:
    failures = []
    missing = []
    for pal_id in sorted(pals):
        key = pair_key(pal_id, pal_id)
        if key not in pairs:
            missing.append(pal_id)
        elif pairs[key] != {pal_id}:
            failures.append({"pal": pal_id, "results": sorted(pairs[key])})
    return {
        "source": source_name,
        "palCount": len(pals),
        "missingCount": len(missing),
        "wrongResultCount": len(failures),
        "missingSample": missing[:100],
        "wrongResultSample": failures[:100],
    }


def build_consensus(source_maps: dict[str, dict[str, set[str]]]) -> tuple[dict[str, Any], dict[str, Any]]:
    all_keys = sorted(set().union(*(set(value) for value in source_maps.values())))
    usable: dict[str, Any] = {}
    disputed: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []
    unanimous_all = 0
    unanimous_available = 0
    majority_with_dissent = 0

    for key in all_keys:
        present = {name: source_maps[name][key] for name in source_maps if key in source_maps[name]}
        signatures: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for source, children in present.items():
            signatures[tuple(sorted(children))].append(source)

        if len(present) == len(source_maps) and len(signatures) == 1:
            unanimous_all += 1
        if len(present) >= 2 and len(signatures) == 1:
            unanimous_available += 1
            children = next(iter(signatures))
            usable[key] = {
                "children": list(children),
                "sources": sorted(present),
                "evidence": "unanimous-among-available-sources",
                "allSourcesPresent": len(present) == len(source_maps),
            }
            continue

        largest = max((len(names) for names in signatures.values()), default=0)
        details = {source: sorted(children) for source, children in sorted(present.items())}
        if largest >= 2:
            majority_with_dissent += 1
            disputed.append({"pair": key, "results": details, "reason": "source-dissent"})
        elif len(present) >= 2:
            disputed.append({"pair": key, "results": details, "reason": "no-two-sources-agree"})
        else:
            insufficient.append({"pair": key, "results": details, "reason": "single-source-only"})

    summary = {
        "unionPairs": len(all_keys),
        "unanimousAllSources": unanimous_all,
        "unanimousAvailableSources": unanimous_available,
        "majorityWithDissent": majority_with_dissent,
        "disputedPairs": len(disputed),
        "insufficientPairs": len(insufficient),
        "usablePairs": len(usable),
        "disputedSample": disputed[:200],
        "insufficientSample": insufficient[:200],
    }
    return usable, summary


def detect_source_drift(source_texts: dict[str, str]) -> dict[str, Any]:
    pst_generator = source_texts["pst.generator"]
    pst_notes = source_texts["pst.notes"]
    palcalc_reader = source_texts["palcalc.reader"]
    palcalc_calculator = source_texts["palcalc.calculator"]

    return {
        "pst": {
            "generatorReadsIgnoreCombi": "IgnoreCombi" in pst_generator,
            "generatorReadsRarity": "Rarity" in pst_generator,
            "generatorExcludesUniqueChildren": "unique_child_tribes" in pst_generator and "candidate_pool" in pst_generator,
            "generatorHigherRankDistanceTie": bool(re.search(r"diff\s*==\s*best_diff[^\n]+\['rank'\]\s*>\s*best\['rank'\]", pst_generator)),
            "notesClaimRarityTieBreaker": "rarity" in pst_notes.lower() and "tiebreaker" in pst_notes.lower(),
            "notesAndGeneratorConflict": (
                "rarity" in pst_notes.lower()
                and "tiebreaker" in pst_notes.lower()
                and bool(re.search(r"diff\s*==\s*best_diff[^\n]+\['rank'\]\s*>\s*best\['rank'\]", pst_generator))
            ),
        },
        "palcalc": {
            "readerReadsIgnoreCombi": "IgnoreCombi" in palcalc_reader,
            "readerReadsDuplicatePriority": "CombiDuplicatePriority" in palcalc_reader,
            "calculatorUsesDuplicatePriority": "BreedingPowerPriority" in palcalc_calculator,
            "calculatorExcludesUniqueChildren": "specificBreedingCombos.Select" in palcalc_calculator,
        },
    }


def load_sources() -> tuple[dict[str, str], dict[str, Any]]:
    texts: dict[str, str] = {}
    metadata: dict[str, Any] = {}
    for source_name, spec in SOURCE_SPECS.items():
        repo = spec["repo"]
        sha, resolved_ref = resolve_sha(repo, spec["ref"])
        source_files = {}
        for label, path in spec["files"].items():
            url = raw_url(repo, sha, path)
            text = request_text(url)
            texts[f"{source_name}.{label}"] = text
            source_files[label] = {
                "path": path,
                "url": url,
                "bytes": len(text.encode("utf-8")),
                "sha256": sha256_text(text),
            }
        metadata[source_name] = {
            "repo": repo,
            "requestedRef": spec["ref"],
            "resolvedRef": resolved_ref,
            "commit": sha,
            "files": source_files,
        }
    return texts, metadata


def validate_output(report: dict[str, Any], consensus: dict[str, Any]) -> None:
    source_pairs = report["sourcesSummary"]
    for required in ("palcalc", "pst", "paldeck"):
        if required not in source_pairs or source_pairs[required]["pairCount"] <= 0:
            raise RuntimeError(f"Missing usable pair data from {required}")

    pairs = consensus.get("pairs", {})
    for key, row in pairs.items():
        if "|" not in key:
            raise RuntimeError(f"Invalid pair key: {key}")
        if len(row.get("sources", [])) < 2:
            raise RuntimeError(f"Consensus pair lacks two sources: {key}")
        if not row.get("children"):
            raise RuntimeError(f"Consensus pair has no child: {key}")

    if len(pairs) != report["consensus"]["usablePairs"]:
        raise RuntimeError("Consensus pair count does not match report")


def main() -> None:
    texts, source_metadata = load_sources()
    palcalc = load_palcalc(texts["palcalc.pals"], texts["palcalc.breeding"])
    pst = load_pst(texts["pst.breeding"])
    paldeck = load_paldeck(texts["paldeck.breeding"])

    source_maps = {
        "palcalc": palcalc["pairs"],
        "pst": pst["pairs"],
        "paldeck-paldb": paldeck["pairs"],
    }
    usable, consensus_summary = build_consensus(source_maps)

    roster_union = sorted(set(palcalc["pals"]) | set(pst["pals"]) | set(paldeck["pals"]))
    roster_intersection = sorted(set(palcalc["pals"]) & set(pst["pals"]) & set(paldeck["pals"]))
    roster_presence = Counter()
    for pal_id in roster_union:
        roster_presence[sum(pal_id in roster for roster in (palcalc["pals"], pst["pals"], paldeck["pals"]))] += 1

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report = {
        "schemaVersion": 3,
        "generatedAt": generated_at,
        "policy": {
            "authoritativeSource": None,
            "usableRule": "At least two sources agree and no available source dissents",
            "gameRuntimeVerified": False,
            "failClosed": True,
        },
        "sourceMetadata": source_metadata,
        "sourcesSummary": {
            "palcalc": {
                "palCount": len(palcalc["pals"]),
                "pairCount": len(palcalc["pairs"]),
                "rawRowCount": palcalc["rawRowCount"],
                "genderSpecificRows": len(palcalc["genderRows"]),
                "malformedRows": palcalc["malformedRows"],
            },
            "pst": {
                "palCount": len(pst["pals"]),
                "pairCount": len(pst["pairs"]),
                "ignoreCombiCount": sum(bool(p["ignoreCombi"]) for p in pst["pals"].values()),
                "categoryRows": pst["categoryRows"],
                "uniqueIndexMismatch": pst["uniqueIndexMismatch"],
            },
            "paldeck": {
                "palCount": len(paldeck["pals"]),
                "pairCount": len(paldeck["pairs"]),
                "rawPairRowCount": paldeck["rawPairRowCount"],
                "unknownPairRows": len(paldeck["unknownPairRows"]),
                "metadata": paldeck["metadata"],
            },
        },
        "roster": {
            "unionCount": len(roster_union),
            "intersectionCount": len(roster_intersection),
            "presenceBySourceCount": {str(key): value for key, value in sorted(roster_presence.items())},
            "palcalcOnly": sorted(set(palcalc["pals"]) - set(pst["pals"]) - set(paldeck["pals"])),
            "pstOnly": sorted(set(pst["pals"]) - set(palcalc["pals"]) - set(paldeck["pals"])),
            "paldeckOnly": sorted(set(paldeck["pals"]) - set(palcalc["pals"]) - set(pst["pals"])),
            "union": roster_union,
            "intersection": roster_intersection,
        },
        "comparisons": {
            "palcalcVsPst": compare_maps(palcalc["pairs"], pst["pairs"]),
            "palcalcVsPaldeckPalDB": compare_maps(palcalc["pairs"], paldeck["pairs"]),
            "pstVsPaldeckPalDB": compare_maps(pst["pairs"], paldeck["pairs"]),
        },
        "sameSpecies": {
            "palcalc": same_species_audit("palcalc", palcalc["pals"], palcalc["pairs"]),
            "pst": same_species_audit("pst", pst["pals"], pst["pairs"]),
            "paldeck": same_species_audit("paldeck", paldeck["pals"], paldeck["pairs"]),
        },
        "sourceDrift": detect_source_drift(texts),
        "consensus": consensus_summary,
        "genderSpecificPalcalcRows": palcalc["genderRows"],
    }

    consensus = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "status": "cross-source-consensus-not-game-runtime-verified",
        "failClosed": True,
        "sourceCommits": {name: value["commit"] for name, value in source_metadata.items()},
        "pairCount": len(usable),
        "pairs": usable,
    }

    validate_output(report, consensus)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CONSENSUS_OUT.write_text(json.dumps(consensus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "report": str(REPORT_OUT.relative_to(ROOT)),
        "consensus": str(CONSENSUS_OUT.relative_to(ROOT)),
        "sourcePairs": {name: len(value) for name, value in source_maps.items()},
        "usablePairs": len(usable),
        "disputedPairs": consensus_summary["disputedPairs"],
        "insufficientPairs": consensus_summary["insufficientPairs"],
        "sourceDrift": report["sourceDrift"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {error.code} while auditing sources: {body[:1000]}") from error
