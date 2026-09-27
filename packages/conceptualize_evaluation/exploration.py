"""Conservative explicit-read observations, never inferred total filesystem access."""

import fnmatch
import re


def exploration(events, paths):
    reads = []
    searches = 0
    greps = 0
    listings = 0
    unknown = []
    failed_tests = []
    first = {}
    for step, event in enumerate(events):
        item = event.get("item", {})
        if event.get("type") != "item.completed" or item.get("type") != "command_execution":
            continue
        cmd = item.get("command", "").replace("\\", "/")
        if item.get("exit_code") not in (None, 0) and re.search(
            r"\b(pytest|unittest)\b|npm\s+test", cmd
        ):
            failed_tests.append({"step": step, "command": cmd, "exit_code": item["exit_code"]})
        if item.get("exit_code") != 0:
            continue
        searches += len(re.findall(r"\brg\b(?!\s+--files)|\bSelect-String\b", cmd, re.I))
        greps += len(re.findall(r"\bgrep\b", cmd))
        listings += len(re.findall(r"Get-ChildItem|\bls\b|\bdir\b|\brg\s+--files", cmd, re.I))
        for match in re.finditer(r"(?:Get-Content|\bcat\b|\btype\b)\s+([^;|\n]+)", cmd, re.I):
            segment = match.group(1)
            tokens = re.findall(r"[\w./*?\-]+\.(?:py|ts|tsx|js|json|toml|yaml|yml|md)", segment)
            found = set()
            for token in tokens:
                for path in paths:
                    if fnmatch.fnmatch(path, token.lstrip("./")) or token.endswith("/" + path):
                        found.add(path)
            if not found:
                unknown.append(
                    {
                        "step": step,
                        "command": match.group(0),
                        "reason": "unresolved literal/variable path",
                    }
                )
            for path in sorted(found):
                reads.append(
                    {
                        "step": step,
                        "path": path,
                        "evidence": match.group(0),
                        "confidence": "explicit successful read command; lower bound",
                    }
                )
                first.setdefault(path, step)
    inspected = sorted(first)
    return {
        "observed_file_reads": len(reads),
        "observed_repeated_reads": len(reads) - len(inspected),
        "observed_files_inspected": inspected,
        "first_observed_read": first,
        "read_evidence": reads,
        "searches": searches,
        "grep_operations": greps,
        "directory_listings": listings,
        "unresolved_read_commands": unknown,
        "observed_failed_test_commands": failed_tests,
        "all_file_reads": None,
        "coverage_scope": "Supported literal Get-Content/cat/type commands only. Variable reads, editor tools, pipelines, implicit imports and other commands are not fully observable.",
    }


def coverage(events, observed, relevant, successful):
    if not successful:
        return {
            "relevant_file_recall_before_observed_read": None,
            "reason": "No successful outcome to establish relevant-change proxy",
        }
    surfaced = {}
    source = {}
    duplicates = 0
    avoided = 0
    wire_bytes = 0
    timings = []
    for step, event in enumerate(events):
        item = event.get("item", {})
        if event.get("type") != "item.completed" or item.get("type") != "mcp_tool_call":
            continue
        result = item.get("result") or {}
        payload = result.get("structured_content") or result.get("structuredContent") or {}
        import json

        wire_bytes += len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        timings.append(
            {"step": step, "tool": item.get("tool"), "timings_ms": payload.get("timings_ms", {})}
        )
        for path in payload.get("included_files", []):
            surfaced.setdefault(path, step)
        for unit in payload.get("deliveries", []):
            if unit.get("level") in {"source", "pack"}:
                source.setdefault(unit["path"], step)
        duplicates += payload.get("metrics", {}).get("duplicate_tokens_retransmitted", 0)
        avoided += payload.get("metrics", {}).get("duplicate_tokens_avoided", 0)
    early = {
        p: step
        for p, step in source.items()
        if p in relevant
        and p in observed["first_observed_read"]
        and step < observed["first_observed_read"][p]
    }
    return {
        "relevant_files_proxy": sorted(relevant),
        "relevance_basis": "Python source and test files modified in a run that passed independent checks. This is a post-hoc proxy, not perfect task ground truth.",
        "relevant_file_recall_before_independent_read": None,
        "relevant_file_recall_before_observed_read": len(early) / len(relevant)
        if relevant
        else None,
        "early_discovery": early,
        "source_surfaced_without_observed_read": sorted(
            set(source) & relevant - set(observed["first_observed_read"])
        ),
        "relevant_source_files_surfaced": sorted(set(source) & relevant),
        "relevant_files_surfaced": sorted(set(surfaced) & relevant),
        "unnecessary_files_surfaced": sorted(set(surfaced) - relevant),
        "observed_unnecessary_files_inspected": sorted(
            set(observed["observed_files_inspected"]) - relevant
        ),
        "duplicate_context_tokens_retransmitted": duplicates,
        "duplicate_tokens_avoided": avoided,
        "recorded_mcp_result_json_bytes": wire_bytes,
        "operation_timings": timings,
        "limits": "Before independently opening means before a supported observed explicit read. Structural map exposure is reported separately from source delivery.",
    }
