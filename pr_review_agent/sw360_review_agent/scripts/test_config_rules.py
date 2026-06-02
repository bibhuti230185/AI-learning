"""Quick smoke test for config-driven rules."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sw360_review_agent.rules_loader import load_project_rules
from sw360_review_agent.lint_rules import DeterministicLinter
from sw360_review_agent.schemas import ChangedFile, FileClassification


def main():
    rules = load_project_rules("project_rules")
    linter = DeterministicLinter(project_rules=rules)

    # Test R01 commit rule
    findings = linter.check_commits(["feat: no sign-off here"])
    assert len(findings) == 1, f"R01: expected 1, got {len(findings)}"
    print(f"R01 (commit Signed-off-by): PASS ({len(findings)} finding)")

    # Test R03 hardcoded credentials
    f = ChangedFile(
        path="src/Service.java",
        status="modified",
        classification=FileClassification.SERVICE,
        file_type="service",
        added_lines=[(10, 'String password = "secret123";')],
    )
    findings = linter.check_file(f)
    assert len(findings) == 1, f"R03: expected 1, got {len(findings)}"
    print(f"R03 (hardcoded creds): PASS ({len(findings)} finding)")

    # Test R06 generic catch
    f = ChangedFile(
        path="src/Handler.java",
        status="modified",
        classification=FileClassification.HANDLER,
        file_type="handler",
        added_lines=[(10, "} catch (Exception e) {")],
    )
    findings = linter.check_file(f)
    assert len(findings) == 1, f"R06: expected 1, got {len(findings)}"
    print(f"R06 (generic catch): PASS ({len(findings)} finding)")

    # Test R06 skips test files (exclude_paths)
    f = ChangedFile(
        path="src/test/SomeTest.java",
        status="modified",
        classification=FileClassification.TEST,
        file_type="test",
        added_lines=[(10, "} catch (Exception e) {")],
    )
    findings = linter.check_file(f)
    assert len(findings) == 0, f"R06 skip: expected 0, got {len(findings)}"
    print(f"R06 (skip test files): PASS ({len(findings)} findings)")

    # Test R02 thrift null-safety
    f = ChangedFile(
        path="rest/Sw360ProjectService.java",
        status="modified",
        classification=FileClassification.SERVICE,
        file_type="service",
        added_lines=[(42, "String name = client.getProjectById(id, user).getName();")],
    )
    findings = linter.check_file(f)
    assert len(findings) == 1, f"R02: expected 1, got {len(findings)}"
    print(f"R02 (thrift null-safety): PASS ({len(findings)} finding)")

    # Test file classification from config
    from sw360_review_agent.github_client import classify_file

    classification, file_type = classify_file("rest/ProjectController.java", rules)
    assert classification == FileClassification.CONTROLLER
    assert file_type == "controller"
    print(f"File classification (config): PASS (controller)")

    classification, file_type = classify_file("src/models.py", rules)
    assert classification == FileClassification.OTHER
    assert file_type == "other"
    print(f"File classification (no match): PASS (other)")

    print("\n ALL CONFIG-DRIVEN TESTS PASSED!")


if __name__ == "__main__":
    main()
