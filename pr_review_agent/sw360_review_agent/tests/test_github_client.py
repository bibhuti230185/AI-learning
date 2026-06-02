# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Unit tests for GitHub client utilities."""

from sw360_review_agent.github_client import classify_file, _extract_added_lines
from sw360_review_agent.schemas import FileClassification


class TestClassifyFile:
    def test_controller(self):
        classification, file_type = classify_file("rest/server/ProjectController.java")
        assert classification == FileClassification.CONTROLLER
        assert file_type == "controller"

    def test_service(self):
        classification, file_type = classify_file("rest/Sw360ProjectService.java")
        assert classification == FileClassification.SERVICE
        assert file_type == "service"

    def test_test_file(self):
        classification, file_type = classify_file("test/ProjectTest.java")
        assert classification == FileClassification.TEST
        assert file_type == "test"

    def test_spec_test(self):
        classification, file_type = classify_file("test/ProjectSpecTest.java")
        assert classification == FileClassification.TEST
        assert file_type == "test"

    def test_thrift(self):
        classification, file_type = classify_file("libraries/components.thrift")
        assert classification == FileClassification.THRIFT
        assert file_type == "thrift"

    def test_handler(self):
        classification, file_type = classify_file("backend/ComponentHandler.java")
        assert classification == FileClassification.HANDLER
        assert file_type == "handler"

    def test_database_handler(self):
        classification, file_type = classify_file("backend/ComponentDatabaseHandler.java")
        assert classification == FileClassification.HANDLER
        assert file_type == "handler"

    def test_jackson(self):
        classification, file_type = classify_file("rest/JacksonCustomizations.java")
        assert classification == FileClassification.JACKSON_MIXIN
        assert file_type == "jackson_mixin"

    def test_generic_java(self):
        classification, file_type = classify_file("src/SomeUtil.java")
        assert classification == FileClassification.JAVA
        assert file_type == "java"

    def test_non_java(self):
        classification, file_type = classify_file("README.md")
        assert classification == FileClassification.OTHER
        assert file_type == "other"

    def test_yaml(self):
        classification, file_type = classify_file("config/application.yml")
        assert classification == FileClassification.OTHER
        assert file_type == "other"


class TestExtractAddedLines:
    def test_simple_patch(self):
        patch = (
            "@@ -10,3 +10,5 @@ public class Foo {\n"
            "     existing line\n"
            "+    new line 1\n"
            "+    new line 2\n"
            "     another existing\n"
        )
        result = _extract_added_lines(patch)
        assert len(result) == 2
        assert result[0] == (11, "    new line 1")
        assert result[1] == (12, "    new line 2")

    def test_empty_patch(self):
        assert _extract_added_lines("") == []

    def test_multiple_hunks(self):
        patch = (
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            "+added1\n"
            " line2\n"
            "@@ -10,3 +11,4 @@\n"
            " line10\n"
            "+added2\n"
            " line11\n"
        )
        result = _extract_added_lines(patch)
        assert len(result) == 2
        assert result[0] == (2, "added1")
        assert result[1] == (12, "added2")
