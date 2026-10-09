"""固化功能单元测试。"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agents.solidify_agent import (
    _find_latest_run_for_module,
    _load_passed_cases,
    _extract_case_from_markdown,
)


class TestLoadPassedCases:
    """测试 _load_passed_cases 函数。"""

    def test_filters_pass_only(self):
        records = [
            {"case_id": "TC-001", "status": "pass", "name": "用例1"},
            {"case_id": "TC-002", "status": "fail", "name": "用例2"},
            {"case_id": "TC-003", "status": "pass", "name": "用例3"},
        ]
        result = _load_passed_cases(records)
        assert len(result) == 2
        assert result[0]["case_id"] == "TC-001"
        assert result[1]["case_id"] == "TC-003"

    def test_empty_records(self):
        assert _load_passed_cases([]) == []

    def test_no_pass_records(self):
        records = [
            {"case_id": "TC-001", "status": "fail"},
            {"case_id": "TC-002", "status": "blocked"},
        ]
        assert _load_passed_cases(records) == []

    def test_preserves_case_fields(self):
        records = [
            {
                "case_id": "TC-工业APP-分类管理-001",
                "status": "pass",
                "name": "验证新建分类",
                "module": "分类管理",
                "priority": "P0",
                "steps": [{"order": 1, "action": "点击新建"}],
                "assertions": [{"text": "弹窗关闭"}],
                "precondition": "已登录",
                "test_data": "分类名：测试A",
            },
        ]
        result = _load_passed_cases(records)
        assert len(result) == 1
        assert result[0]["case_id"] == "TC-工业APP-分类管理-001"
        assert result[0]["priority"] == "P0"
        assert len(result[0]["steps"]) == 1


class TestFindLatestRun:
    """测试 _find_latest_run_for_module 函数。"""

    @patch("agents.solidify_agent.list_runs")
    def test_finds_matching_run(self, mock_list_runs):
        mock_list_runs.return_value = [
            "工业APP_20260930_140000",
            "知识管理_20260929_100000",
        ]
        result = _find_latest_run_for_module("工业APP")
        assert result == "工业APP_20260930_140000"

    @patch("agents.solidify_agent.list_runs")
    def test_returns_none_when_no_match(self, mock_list_runs):
        mock_list_runs.return_value = ["知识管理_20260929_100000"]
        result = _find_latest_run_for_module("工业APP")
        assert result is None

    @patch("agents.solidify_agent.list_runs")
    def test_returns_none_when_empty(self, mock_list_runs):
        mock_list_runs.return_value = []
        result = _find_latest_run_for_module("工业APP")
        assert result is None

    @patch("agents.solidify_agent.list_runs")
    def test_returns_latest_when_multiple(self, mock_list_runs):
        mock_list_runs.return_value = [
            "工业APP_20260930_160000",
            "工业APP_20260929_100000",
        ]
        result = _find_latest_run_for_module("工业APP")
        assert result == "工业APP_20260930_160000"


class TestExtractCaseFromMarkdown:
    """测试 _extract_case_from_markdown 函数。"""

    def test_extracts_steps_and_assertions(self, tmp_path):
        md_content = """# 测试用例

### TC-工业APP-分类管理-001 验证新建分类

| 字段 | 值 |
|------|-----|
| 用例ID | TC-工业APP-分类管理-001 |
| 模块 | 分类管理 |
| 测试步骤 | 1. 点击文档知识库 2. 点击新建分类 3. 输入名称 4. 保存 |
| 预期结果 | 1. 弹窗关闭 2. 新分类出现在树中 |
"""
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content, encoding="utf-8")
        
        result = _extract_case_from_markdown(md_file, "TC-工业APP-分类管理-001")
        assert result is not None
        assert "点击文档知识库" in result["steps"]
        assert "弹窗关闭" in result["assertions"]

    def test_returns_none_for_missing_case(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# empty", encoding="utf-8")
        
        result = _extract_case_from_markdown(md_file, "TC-NOT-EXIST")
        assert result is None

    def test_returns_none_for_missing_file(self):
        result = _extract_case_from_markdown(Path("/nonexistent.md"), "TC-001")
        assert result is None

    def test_extracts_operation_steps_alias(self, tmp_path):
        """测试 '操作步骤' 也能被识别（不仅是 '测试步骤'）。"""
        md_content = """### TC-001 测试

| 字段 | 值 |
|------|-----|
| 操作步骤 | 1. 打开页面 2. 点击按钮 |
| 预期结果 | 1. 页面正常显示 |
"""
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content, encoding="utf-8")
        
        result = _extract_case_from_markdown(md_file, "TC-001")
        assert result is not None
        assert "打开页面" in result["steps"]
