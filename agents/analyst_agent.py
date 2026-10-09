"""
分析智能体 —— 流水线第 1 步：分析需求文档，提取测试点。

改造说明：
  原版本通过 ChatOpenAI 调用远程 AI 模型。
  改造后，通过 Qoder 对话完成分析，脚本负责：
    1. 读取需求文档和原型截图
    2. 生成提示词并复制到剪贴板
    3. 等待用户粘贴 Qoder 的分析结果
    4. 解析结果并导出测试点

输出文件：output/02_split_requirements/ (拆分后需求) 和 output/03_design/test_points/ (测试点)
"""
import json
import re
from pathlib import Path
from agents.base_agent import BaseAgent
from agents.agent_loader import load_prompt
from core.config import SPEC_DIR, SPLIT_REQUIREMENTS_DIR, get_module_dir, PROTOTYPE_URL
from agents.upstream_context import build_upstream_context
from utils.logger import get_logger

logger = get_logger("analyst")

# 需求拆分提示词（从 analyst_agent.md 加载）
ANALYST_SPLIT_PROMPT = """你现在是一名测试分析负责人。

我已经把原始需求文档转换成 Markdown：

`{归一化需求文件路径}`

请你先不要生成测试用例，而是把这份需求文档拆分成后续更容易分析的模块化需求文件。

## 目标

请完成 4 件事：

1. 按业务领域拆分需求，不要只按原章节机械切割。
2. 把分散在不同章节、但属于同一功能模块的规则聚合到同一个文件。
3. 保留原文中的规则编号、表格、流程图、状态、字段、验收标准和待确认问题。
4. 识别影响测试设计的风险，例如未定义、歧义、冲突、缺少边界、缺少状态说明。

## 推荐拆分方式

你可以先参考下面的通用结构，再根据实际文档调整：

| 文件 | 适用内容 |
|---|---|
| `01-项目概述.md` | 项目背景、角色、术语、范围、总体流程、非功能需求 |
| `02-身份与权限.md` | 注册、登录、认证、授权、账号状态、角色权限 |
| `03-信息查询与展示.md` | 首页、列表、搜索、筛选、详情、信息展示 |
| `04-核心业务流程.md` | 创建、提交、确认、办理、支付、审批等主流程 |
| `05-状态管理与后续处理.md` | 状态流转、撤销、取消、审核、申诉、复核、关闭 |
| `06-个人中心与数据维护.md` | 用户资料、地址、联系人、偏好设置、历史记录 |
| `07-管理配置.md` | 管理后台、系统配置、基础数据、权限管理、运营配置 |
| `08-风险清单与待确认汇总.md` | 全部风险、待确认项、冲突点、缺失规则 |
| `目录.md` | 文件索引、模块说明、原文来源、规则编号索引 |

如果文档不适合这个结构，请给出你自己的拆分方案，并说明原因。

## 每个模块文件的建议结构

```markdown
# {模块名称}

> 来源：{原文章节号或标题}

## 1. 模块范围

说明该模块包含哪些功能，不包含哪些功能。

## 2. 业务流程

保留原文中的流程图、流程步骤或状态流转。没有流程时写"原文未提供明确流程"。

## 3. 功能规则

| 规则编号 | 规则内容 | 来源 |
|---|---|---|

## 4. 字段、状态和配置

整理表单字段、查询条件、状态枚举、配置项、角色权限等测试设计需要的信息。

## 5. 异常、边界和验收标准

提取原文中已经明确的异常处理、边界条件和验收标准。

## 6. 风险小结

| 风险编号 | 风险类型 | 风险描述 | 来源 | 对测试设计的影响 |
|---|---|---|---|---|
```

## 风险分类

| 风险类型 | 判断标准 |
|---|---|
| 待确认 | 原文明确写了"待确认""TBD""？"等 |
| 未定义 | 功能被提到，但缺少字段、规则、流程、状态或异常处理 |
| 有歧义 | 描述可能有多种理解，例如"按系统规则""适当提示""默认处理" |
| 前后冲突 | 不同章节对同一规则、状态、字段或权限的描述不一致 |
| 测试阻塞 | 缺少账号、测试数据、配置说明、状态枚举，导致用例无法确定预期 |

## 输出要求

1. 先输出"拆分方案摘要"，说明你将生成哪些文件。
2. 然后在 `{拆分需求目录}` 下创建对应 Markdown 文件。
3. 不要修改原始需求文件。
4. 不要补充文档外的业务规则。
5. 需求不明确时，只标记为风险或待确认，不要替业务方下结论。
6. 最后输出"完成清单"：文件名、对应原文章节、主要内容、风险数量。
"""


class AnalystAgent(BaseAgent):
    """分析智能体类 —— 负责拆分和整理需求文档。"""
    role = "analyst"

    def __init__(self):
        super().__init__()

    def analyze(self, doc_path: Path) -> str | None:
        """
        分析单个需求文档，拆分成模块化需求文件。

        流程：
        1. 读取需求文档内容
        2. 把文档路径发给 Qoder 进行拆分
        3. Qoder 会在 output/02_split_requirements/{模块名}/ 目录下创建模块化文件
        """
        module_name = doc_path.stem
        doc_content = doc_path.read_text(encoding="utf-8")

        # 获取模块专属子目录
        module_dir = get_module_dir(SPLIT_REQUIREMENTS_DIR, module_name)

        # 构建原型参考信息
        prototype_info = ""
        if PROTOTYPE_URL:
            prototype_info = f"\n\n## 原型参考\n\n在线原型地址：{PROTOTYPE_URL}\n分析需求时请参考原型界面，帮助理解功能布局和交互方式。"

        # 上游业务基线（探索产物 / 业务全景图），在 .format 之后拼接，避免花括号冲突
        upstream_info = build_upstream_context(module_name)

        # 从 .md 文件加载提示词
        prompt = load_prompt(
            "analyst",
            归一化需求文件路径=str(doc_path.resolve()),
            拆分需求目录=str(module_dir.resolve())
        ) + prototype_info + upstream_info

        # 发送给 Qoder
        task_name = f"analyze_{module_name}"
        raw = self.invoke_text(prompt, task_name=task_name)

        logger.info(f"  需求拆分完成：{module_name}")
        logger.info(f"  输出目录：{module_dir}")
        
        # 显示 Qoder 的回复摘要
        print(f"\n{'=' * 60}")
        print(f"  需求拆分：{module_name}")
        print(f"{'=' * 60}")
        print(raw[:500].encode('gbk', errors='replace').decode('gbk'))
        if len(raw) > 500:
            print("...")
        
        return module_name

    def analyze_all(self):
        """分析所有需求文档。"""
        docs = sorted(list(SPEC_DIR.glob("*.md")) + list(SPEC_DIR.glob("*.txt")))
        if not docs:
            logger.error(f"未找到需求文档：{SPEC_DIR}")
            return
        logger.info(f"分析智能体：{len(docs)} 份文档")
        for doc in docs:
            logger.info(f"  分析中：{doc.name}")
            self.analyze(doc)
