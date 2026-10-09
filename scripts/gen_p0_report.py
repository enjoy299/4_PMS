# -*- coding: utf-8 -*-
"""生成知识管理模块P0用例Excel测试报告"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exporters.report_exporter import ReportExporter

exporter = ReportExporter()

results = [
    {
        "id": "TC-CAT-001",
        "name": "文档知识库下新建一级分类",
        "module": "分类管理",
        "case_type": "正向",
        "priority": "P0",
        "status": "pass",
        "duration": 8.5,
        "precondition": "已登录系统，进入知识管理页面，选中'文档知识库'分类",
        "steps": "1. 点击左侧'文档知识库' 2. 点击工具栏'新建分类'按钮 3. 在弹窗中输入分类名称'P0测试分类' 4. 输入描述'P0用例测试描述' 5. 点击'保存'",
        "expected": "1. 弹窗关闭，显示'新建成功'提示 2. 左侧分类树中出现'P0测试分类'一级分类",
        "test_data": "分类名称：P0测试分类；描述：P0用例测试描述",
        "req_source": "CAT-01,CAT-02,CAT-04",
        "test_point_ref": "TP-CAT-001",
        "assertions": [
            {"text": "弹窗关闭，显示'新建成功'提示", "passed": True},
            {"text": "分类树中出现'P0测试分类'", "passed": True},
        ],
        "output": "",
        "error": "",
    },
    {
        "id": "TC-CAT-009",
        "name": "删除含有知识文档的分类",
        "module": "分类管理",
        "case_type": "异常",
        "priority": "P0",
        "status": "fail",
        "duration": 6.3,
        "precondition": "已登录，存在分类'基础理论'且该分类下有知识文档（1条已入库知识）",
        "steps": "1. 选中'基础理论'分类 2. 点击'删除分类'按钮",
        "expected": "1. 显示全局提示'当前分类下有知识文档，不允许删除' 2. 分类未被删除",
        "test_data": "",
        "req_source": "CAT-13",
        "test_point_ref": "TP-CAT-010",
        "assertions": [
            {"text": "显示'当前分类下有知识文档，不允许删除'提示", "passed": False},
            {"text": "分类未被删除", "passed": True},
        ],
        "output": "",
        "error": "【缺陷】删除前未检查文档，直接弹出删除确认框，缺少友好提示",
    },
    {
        "id": "TC-KM-001",
        "name": "新建知识状态为编辑中",
        "module": "知识维护",
        "case_type": "状态",
        "priority": "P0",
        "status": "error",
        "duration": 15.2,
        "precondition": "已登录，进入文档知识库某分类",
        "steps": "1. 点击'新建'按钮 2. 上传文档test.doc 3. 填写知识信息 4. 点击保存",
        "expected": "1. 知识创建成功 2. 列表中显示该知识 3. 状态列为'编辑中'",
        "test_data": "上传文件：test.doc（需要实际文件）",
        "req_source": "KM-01,KM-02",
        "test_point_ref": "TP-KM-001",
        "assertions": [
            {"text": "知识创建成功", "passed": False},
            {"text": "状态列为'编辑中'", "passed": False},
        ],
        "output": "",
        "error": "【阻塞】需要上传实际文件才能完成测试，当前环境无法提供测试文件",
    },
    {
        "id": "TC-KM-002",
        "name": "入库后状态变为已入库",
        "module": "知识维护",
        "case_type": "状态",
        "priority": "P0",
        "status": "error",
        "duration": 0,
        "precondition": "已登录，存在'编辑中'状态的知识",
        "steps": "1. 勾选该知识 2. 点击'入库'按钮 3. 在确认弹窗中点击'确认'",
        "expected": "1. 弹出二次确认对话框 2. 该知识状态变为'已入库'",
        "test_data": "",
        "req_source": "KM-03,KM-12",
        "test_point_ref": "TP-KM-002",
        "assertions": [
            {"text": "弹出二次确认对话框", "passed": False},
            {"text": "状态变为'已入库'", "passed": False},
        ],
        "output": "",
        "error": "【阻塞】依赖TC-KM-001，无法创建测试知识",
    },
    {
        "id": "TC-KM-003",
        "name": "删除操作需要二次确认",
        "module": "知识维护",
        "case_type": "正向",
        "priority": "P0",
        "status": "error",
        "duration": 0,
        "precondition": "已登录，存在'编辑中'状态且无版本的知识",
        "steps": "1. 勾选该知识 2. 点击'删除'按钮",
        "expected": "1. 弹出二次确认对话框 2. 点击确认后知识被删除",
        "test_data": "",
        "req_source": "KM-08",
        "test_point_ref": "TP-KM-006",
        "assertions": [
            {"text": "弹出二次确认对话框", "passed": False},
        ],
        "output": "",
        "error": "【阻塞】依赖TC-KM-001，无法创建测试知识",
    },
    {
        "id": "TC-KM-004",
        "name": "入库操作需要二次确认",
        "module": "知识维护",
        "case_type": "正向",
        "priority": "P0",
        "status": "error",
        "duration": 0,
        "precondition": "已登录，存在'编辑中'状态的知识",
        "steps": "1. 勾选该知识 2. 点击'入库'按钮",
        "expected": "1. 弹出二次确认对话框 2. 显示确认提示信息",
        "test_data": "",
        "req_source": "KM-11",
        "test_point_ref": "TP-KM-007",
        "assertions": [
            {"text": "弹出二次确认对话框", "passed": False},
        ],
        "output": "",
        "error": "【阻塞】依赖TC-KM-001，无法创建测试知识",
    },
]

report = exporter.build_and_save(
    suite_name="知识管理",
    results=results
)

print(f"报告生成成功")
print(f"通过率: {report['summary']['pass_rate']}")
print(f"通过: {report['summary']['passed']}, 失败: {report['summary']['failed']}, 错误: {report['summary']['errors']}")
