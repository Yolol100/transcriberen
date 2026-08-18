import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "validate_codeql_sarif.py"
spec = importlib.util.spec_from_file_location("codeql_gate", MODULE_PATH)
codeql_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codeql_gate)


def sarif(score=None, rule_id="py/test"):
    properties = {} if score is None else {"security-severity": str(score)}
    return {
        "runs": [{
            "tool": {"driver": {"rules": [{"id": rule_id, "properties": properties}]}},
            "results": [{
                "ruleId": rule_id,
                "ruleIndex": 0,
                "message": {"text": "example"},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": "scripts/x.py"}, "region": {"startLine": 5}}}],
            }],
        }]
    }


class CodeQLSarifGateTests(unittest.TestCase):
    def test_high_is_blocked(self):
        findings = codeql_gate.high_security_findings(sarif(7.0))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["location"], "scripts/x.py:5")

    def test_critical_is_blocked(self):
        self.assertEqual(len(codeql_gate.high_security_findings(sarif(9.5))), 1)

    def test_medium_is_not_blocked(self):
        self.assertEqual(codeql_gate.high_security_findings(sarif(6.9)), [])

    def test_rule_without_security_severity_is_not_invented_as_high(self):
        self.assertEqual(codeql_gate.high_security_findings(sarif()), [])


if __name__ == "__main__":
    unittest.main()
