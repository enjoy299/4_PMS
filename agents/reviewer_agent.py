"""
审核智能体 —— 流水线第 3 步：审核测试用例的质量。

改造说明：
  原版本通过 ChatOpenAI 调用远程 AI 模型。
  改造后，通过 Qoder 对话完成审核。

输出文件：output/04_review/xxx_review_xxx.md
"""
from pathlib import Path
from datetime import datetime
from agents.agent_loader import load_prompt
from core.config import SPLIT_REQUIREMENTS_DIR, DESIGN_WORKSPACE_DIR, REVIEW_DIR, find_module_file
from core.brain import save_prompt, read_response
from utils.logger import get_logger

logger = get_logger("reviewer")

class ReviewerAgent:
    """
    审核智能体类 —— 负责审核测试用例的质量（流程步骤 3）。
    """

    def review(self, module_name: str) -> Path | None:
        """审核指定模块的测试用例。支持父模块名（如"项目管理"）或子模块名（如"01-项目概述"）。

        新目录约定：
          用例存放于 output/03_design/test_cases/{父模块名}/{子模块 stem}-用例.md
          与 output/02_split_requirements/{父模块名}/ 对齐。
        """
        import re

        test_cases_dir = DESIGN_WORKSPACE_DIR / "test_cases"

        # 先检查是否是父模块名（对应拆分需求子目录）
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        subdir = SPLIT_REQUIREMENTS_DIR / module_name
        if not subdir.exists():
            subdir = SPLIT_REQUIREMENTS_DIR / clean_name

        if subdir.exists() and subdir.is_dir():
            parent_module = subdir.name
            case_module_dir = test_cases_dir / parent_module
            # 先查找与父模块名一致的整合作用例文件（支持带时间戳）
            import re as _re
            combined: Path | None = None
            if case_module_dir.exists():
                for cand in sorted(case_module_dir.glob("*-用例.md")) + sorted(case_module_dir.glob("*-用例_*.md")):
                    if module_name in cand.stem or cand.stem.replace("_", "-").split("-")[1:2] == [clean_name]:
                        combined = cand
                        break
            if combined:
                return self._review_single_file(combined, parent_module)
            # 否则处理该父模块下的所有子模块用例文件
            results = []
            search_dir = case_module_dir if case_module_dir.exists() else test_cases_dir
            for f in sorted(subdir.glob("*.md")):
                # 兼容带时间戳/数字前缀的用例文件：{子模块 stem}-用例.md / {NN}-{stem}-用例_{戳}.md
                want = _re.sub(r"^\d+[、_.\-\s]+", "", f.stem).strip()
                cands = [p for p in search_dir.glob("*用例*.md")
                         if _re.sub(r"^\d+[、_.\-\s]+", "", p.stem).startswith(f"{want}-用例")]
                if not cands:
                    continue
                case_file = sorted(cands)[-1]  # 取时间最新的一份
                results.append(self._review_single_file(case_file, parent_module))
            return results[0] if results else None

        # 否则递归查找匹配的单个用例文件（兼容带时间戳批次，取最新；排除 archive）
        cands = (sorted(test_cases_dir.rglob("*-用例_*.md")) +
                 sorted(test_cases_dir.rglob("*-用例.md")))
        hits = [p for p in cands
                if "archive" not in p.parts
                and (module_name in p.stem or p.stem in module_name)]
        if hits:
            case_file = sorted(hits)[-1]
            parent_module = case_file.parent.name if case_file.parent != test_cases_dir else ""
            return self._review_single_file(case_file, parent_module)
        logger.error(f"用例设计文件未找到：{module_name}")
        return None

    def _review_single_file(self, case_file: Path, parent_module: str = "") -> Path | None:
        """审核单个用例设计文件。parent_module 为业务模块名（子目录名）。"""
        import re as _re
        # 剥离文件名末尾的时间戳后缀（如 “-用例_20260907_0953” → “-用例”），避免报告名双时间戳
        actual_module = _re.sub(r"_\d{8}_\d{4}$", "", case_file.stem)
        
        # 从 .md 文件加载提示词
        prompt = load_prompt(
            "reviewer",
            需求内容目录=str(SPLIT_REQUIREMENTS_DIR.resolve()),
            用例设计目录=str(DESIGN_WORKSPACE_DIR.resolve()),
            用例评审目录=str(REVIEW_DIR.resolve()),
            模块编号="01",  # 可以根据实际情况调整
            模块名=actual_module
        )

        task_name = f"review_{actual_module}"
        save_prompt(task_name, prompt)
        response_text = read_response(task_name)

        # 保存评审报告（按业务模块归类子目录）
        report_dir = REVIEW_DIR / parent_module if parent_module else REVIEW_DIR
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_file = report_dir / f"01-{actual_module}-评审报告_{ts}.md"
        output_file.write_text(response_text, encoding="utf-8")
        logger.info(f"  评审报告：{output_file.name}")

        print(f"\n{'=' * 60}")
        print(f"  用例评审：{actual_module}")
        print(f"{'=' * 60}")
        safe_text = response_text[:500].encode('gbk', errors='replace').decode('gbk')
        print(safe_text)
        if len(response_text) > 500:
            print("...")
        return output_file

    def parse_verdict_from_report(self, report_path: Path) -> tuple[str, str]:
        """从已有评审报告中解析评审结论。

        返回：(verdict_code, verdict_text)
          verdict_code: "pass" | "conditional_pass" | "reject" | "unknown"
          verdict_text: 原始结论文本
        """
        from core.review_feedback import parse_verdict
        if not report_path.exists():
            return "unknown", "报告不存在"
        content = report_path.read_text(encoding="utf-8")
        return parse_verdict(content)

    def review_all(self):
        """审核所有模块的测试用例（按父模块目录逐个评审，自动取各子模块最新批次）。"""
        import re as _re
        test_cases_dir = DESIGN_WORKSPACE_DIR / "test_cases"
        if not test_cases_dir.is_dir():
            logger.error(f"未找到用例目录：{test_cases_dir}")
            return
        parents = [d for d in sorted(test_cases_dir.iterdir())
                   if d.is_dir() and d.name != "archive"]
        if parents:
            logger.info(f"审核智能体：{len(parents)} 个父模块")
            for d in parents:
                logger.info(f"  评审中：{d.name}")
                self.review(d.name)
            return
        # 兜底：用例散放根目录的旧结构（兼容带/不带时间戳）
        files = (sorted(test_cases_dir.glob("*-用例_*.md")) +
                 sorted(test_cases_dir.glob("*-用例.md")))
        if not files:
            logger.error(f"未找到用例设计文件：{test_cases_dir}")
            return
        logger.info(f"审核智能体：{len(files)} 个用例文件")
        for f in files:
            actual = _re.sub(r"-用例(_\d{8}_\d{4})?$", "", f.stem)
            logger.info(f"  评审中：{actual}")
            self._review_single_file(f, "")
