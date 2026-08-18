#!/usr/bin/env python3
import json
import sys
from pathlib import Path

HIGH_SECURITY_SEVERITY = 7.0


def high_security_findings(sarif):
    findings = []
    for run in sarif.get("runs", []):
        rules = run.get("tool", {}).get("driver", {}).get("rules", []) or []
        by_id = {str(rule.get("id")): rule for rule in rules if rule.get("id")}
        for result in run.get("results", []) or []:
            rule = None
            index = result.get("ruleIndex")
            if isinstance(index, int) and 0 <= index < len(rules):
                rule = rules[index]
            if rule is None:
                rule = by_id.get(str(result.get("ruleId") or "")) or {}
            props = rule.get("properties", {}) or {}
            raw = props.get("security-severity")
            try:
                score = float(raw)
            except (TypeError, ValueError):
                continue
            if score < HIGH_SECURITY_SEVERITY:
                continue
            location = ""
            locations = result.get("locations") or []
            if locations:
                physical = locations[0].get("physicalLocation", {}) or {}
                artifact = physical.get("artifactLocation", {}) or {}
                region = physical.get("region", {}) or {}
                location = str(artifact.get("uri") or "")
                if region.get("startLine"):
                    location += f":{region['startLine']}"
            message = result.get("message", {}) or {}
            findings.append({
                "rule_id": result.get("ruleId") or rule.get("id"),
                "security_severity": score,
                "location": location,
                "message": message.get("text") or message.get("markdown") or "",
            })
    return findings


def validate_paths(paths):
    all_findings = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            raise ValueError(f"missing SARIF file: {path}")
        sarif = json.loads(path.read_text(encoding="utf-8"))
        findings = high_security_findings(sarif)
        all_findings.extend((str(path), item) for item in findings)
    return all_findings


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: validate_codeql_sarif.py <file.sarif> [...]")
    try:
        findings = validate_paths(sys.argv[1:])
    except Exception as exc:
        print(f"CodeQL SARIF validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if findings:
        for path, finding in findings:
            print(
                f"HIGH/CRITICAL CodeQL finding in {path}: {finding['rule_id']} "
                f"security-severity={finding['security_severity']} {finding['location']} "
                f"{finding['message']}",
                file=sys.stderr,
            )
        raise SystemExit(1)
    print("CodeQL SARIF gate: no high/critical findings")


if __name__ == "__main__":
    main()
