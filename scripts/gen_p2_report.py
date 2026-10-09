# -*- coding: utf-8 -*-
"""生成知识管理模块P2用例Excel测试报告"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exporters.report_exporter import ReportExporter

exporter = ReportExporter()

results = [
    {
        "id": "TC-KQ-002",
        "name": "搜索无结果",
        "module": "知识查询",
        "case_type": "异常",
        "priority": "P2",
        "status": "pass",
        "duration": 6.4,
        "precondition": "已登录，知识库中有知识",
        "steps": "1. 点击筛选按钮 2. 在名称输入框输入'不存在的关键词xyz123' 3. 点击确定",
        "expected": "1. 列表为空或显示'未找到相关知识'提示",
        "test_data": "关键词：不存在的关键词xyz123",
        "req_source": "-",
        "test_point_ref": "TP-KQ-004",
        "assertions": [
            {"text": "列表为空，显示'暂无数据'", "passed": True},
            {"text": "共0条记录", "passed": True},
        ],
        "output": "",
        "error": "",
    },
    {
        "id": "TC-KM-014",
        "name": "查看知识历史版本",
        "module": "知识维护",
        "case_type": "正向",
        "priority": "P2",
        "status": "error",
        "duration": 5.6,
        "precondition": "已登录，存在有多个版本的知识",
        "steps": "1. 勾选该知识 2. 点击'历史版本'按钮",
        "expected": "1. 显示历史版本列表 2. 列表包含版本号、创建人、创建时间",
        "test_data": "",
        "req_source": "-",
        "test_point_ref": "TP-KM-014",
        "assertions": [
            {"text": "显示历史版本列表", "passed": False},
        ],
        "output": "",
        "error": "【阻塞】页面上没有'历史版本'按钮，无法验证该功能",
    },
]

report = exporter.build_and_save(
    suite_name="知识管理",
    results=results
)

print(f"报告生成成功")
print(f"通过率: {report['summary']['pass_rate']}")
print(f"通过: {report['summary']['passed']}, 失败: {report['summary']['failed']}, 错误: {report['summary']['errors']}")
