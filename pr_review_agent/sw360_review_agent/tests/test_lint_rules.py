# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Unit tests for Layer 1 deterministic lint rules.

These rules complement ArchUnit — they only check what ArchUnit/CI miss.
"""

from sw360_review_agent.lint_rules import DeterministicLinter
from sw360_review_agent.schemas import ChangedFile, FileClassification, Severity


def _make_file(
    path: str = "rest/Controller.java",
    status: str = "modified",
    classification: FileClassification = FileClassification.CONTROLLER,
    added_lines: list[tuple[int, str]] | None = None,
    content: str = "",
) -> ChangedFile:
    return ChangedFile(
        path=path,
        status=status,
        classification=classification,
        added_lines=added_lines or [],
        content=content,
        patch=content,
    )


class TestR01SignedOff:
    def test_missing_signed_off(self):
        linter = DeterministicLinter(enabled_rules=["R01"])
        findings = linter.check_commits(["feat(rest): add endpoint\n\nSome body"])
        assert len(findings) == 1
        assert findings[0].rule == "SW360-R01"
        assert findings[0].severity == Severity.ERROR

    def test_present_signed_off(self):
        linter = DeterministicLinter(enabled_rules=["R01"])
        findings = linter.check_commits([
            "feat(rest): add endpoint\n\nSigned-off-by: Dev <dev@example.com>"
        ])
        assert len(findings) == 0

    def test_multiple_commits_partial(self):
        linter = DeterministicLinter(enabled_rules=["R01"])
        findings = linter.check_commits([
            "feat: first\n\nSigned-off-by: Dev <dev@example.com>",
            "fix: second\n\nNo sign-off here",
        ])
        assert len(findings) == 1
        assert "Commit 2" in findings[0].message


class TestR02ThriftNullSafety:
    def test_detects_chained_thrift_call(self):
        file = _make_file(
            path="rest/Sw360ProjectService.java",
            classification=FileClassification.SERVICE,
            added_lines=[
                (42, "        String name = client.getProjectById(id, user).getName();"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R02"])
        findings = linter.check_file(file)
        assert len(findings) == 1
        assert findings[0].rule == "SW360-R02"

    def test_no_false_positive_on_safe_usage(self):
        file = _make_file(
            path="rest/Sw360ProjectService.java",
            classification=FileClassification.SERVICE,
            added_lines=[
                (42, "        Project project = client.getProjectById(id, user);"),
                (43, "        if (project == null) { throw new ResourceNotFoundException(); }"),
                (44, "        return project.getName();"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R02"])
        findings = linter.check_file(file)
        assert len(findings) == 0


class TestR03HardcodedCredentials:
    def test_detects_hardcoded_password(self):
        file = _make_file(
            path="backend/SomeHandler.java",
            classification=FileClassification.HANDLER,
            added_lines=[
                (15, '        String password = "mySecret123";'),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R03"])
        findings = linter.check_file(file)
        assert len(findings) == 1
        assert findings[0].rule == "SW360-R03"
        assert findings[0].severity == Severity.ERROR

    def test_detects_hardcoded_api_key(self):
        file = _make_file(
            path="backend/ExternalService.java",
            classification=FileClassification.HANDLER,
            added_lines=[
                (20, '        String apiKey = "sk-abc123def456";'),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R03"])
        findings = linter.check_file(file)
        assert len(findings) == 1

    def test_skips_test_files(self):
        file = _make_file(
            path="rest/src/test/java/SomeTest.java",
            classification=FileClassification.TEST,
            added_lines=[
                (10, '        String password = "testPassword";'),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R03"])
        findings = linter.check_file(file)
        assert len(findings) == 0

    def test_no_false_positive_on_property_reference(self):
        file = _make_file(
            path="backend/Config.java",
            classification=FileClassification.HANDLER,
            added_lines=[
                (10, '        String password = props.getProperty("couchdb.password");'),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R03"])
        findings = linter.check_file(file)
        assert len(findings) == 0


class TestR04UnboundedFetch:
    def test_detects_get_all_without_pagination(self):
        file = _make_file(
            path="backend/ComponentDatabaseHandler.java",
            classification=FileClassification.HANDLER,
            added_lines=[
                (30, "        List<Component> all = repository.getAllComponents();"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R04"])
        findings = linter.check_file(file)
        assert len(findings) == 1
        assert findings[0].rule == "SW360-R04"

    def test_no_flag_with_pagination(self):
        file = _make_file(
            path="backend/ComponentDatabaseHandler.java",
            classification=FileClassification.HANDLER,
            added_lines=[
                (30, "        List<Component> all = repository.getAllComponents(pageData);"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R04"])
        findings = linter.check_file(file)
        assert len(findings) == 0


class TestR05MigrationScript:
    def test_detects_new_thrift_field(self):
        file = _make_file(
            path="libraries/datahandler/src/main/thrift/components.thrift",
            status="modified",
            classification=FileClassification.THRIFT,
            added_lines=[
                (120, "    42: optional string newField,"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R05"])
        findings = linter.check_file(file)
        assert len(findings) == 1
        assert findings[0].rule == "SW360-R05"
        assert "migration" in findings[0].message.lower()

    def test_skips_non_thrift_files(self):
        file = _make_file(
            path="rest/Controller.java",
            status="modified",
            classification=FileClassification.CONTROLLER,
            added_lines=[
                (10, "    42: optional string newField,"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R05"])
        findings = linter.check_file(file)
        assert len(findings) == 0


class TestR06CatchGenericException:
    def test_detects_catch_exception(self):
        file = _make_file(
            path="backend/ProjectHandler.java",
            classification=FileClassification.HANDLER,
            added_lines=[
                (50, "        } catch (Exception e) {"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R06"])
        findings = linter.check_file(file)
        assert len(findings) == 1
        assert findings[0].rule == "SW360-R06"

    def test_specific_exception_not_flagged(self):
        file = _make_file(
            path="backend/ProjectHandler.java",
            classification=FileClassification.HANDLER,
            added_lines=[
                (50, "        } catch (SW360Exception e) {"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R06"])
        findings = linter.check_file(file)
        assert len(findings) == 0

    def test_skips_test_files(self):
        file = _make_file(
            path="rest/src/test/java/ProjectTest.java",
            classification=FileClassification.TEST,
            added_lines=[
                (50, "        } catch (Exception e) {"),
            ],
        )
        linter = DeterministicLinter(enabled_rules=["R06"])
        findings = linter.check_file(file)
        assert len(findings) == 0


class TestOtherFileSkipped:
    def test_non_java_files_skipped(self):
        file = _make_file(
            path="README.md",
            classification=FileClassification.OTHER,
            added_lines=[(1, "some text")],
        )
        linter = DeterministicLinter()
        findings = linter.check_file(file)
        assert len(findings) == 0
