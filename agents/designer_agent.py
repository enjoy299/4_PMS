"""
设计智能体 —— 设计阶段两步式：测试点（含需求理解自适应）与测试用例。

改造说明：
  原「三阶段一次生成（理解+测试点+用例）」拆为两步可停：
    1. design_testpoints：需求理解（已有则消费，缺失则同对话生成）
                          + 测试点 + 风险清单与待确认汇总（测试设计版）；
    2. design_cases     ：消费最新批次测试点（含确认列）生成测试用例。
  两步之间由人工对确认列拍板（⬜ → ✅），确保用例建立在已拍板事实之上。

输出文件：output/03_design/ 下的测试点 / 风险台账 / 用例文件
"""
import re
from pathlib import Path
from datetime import datetime
from agents.base_agent import BaseAgent
from agents.agent_loader import load_prompt
from core.config import SPLIT_REQUIREMENTS_DIR, TESTPOINTS_DIR, CASES_DIR, PROTOTYPE_URL, ROOT, find_module_file, find_latest_understanding
from agents.upstream_context import build_upstream_context
from utils.logger import get_logger

logger = get_logger("designer")

_ARCHIVE = "archive"
_LEDGER_MARK = "风险清单与待确认汇总"


class DesignerAgent(BaseAgent):
    """设计智能体类 —— 两步式设计：测试点（第一步）与测试用例（第二步）。"""
    role = "designer"

    # ==================== 第一步：需求理解（自适应）+ 测试点 + 风险台账 ====================

    def design_testpoints(self, module_name: str) -> bool:
        """第一步：为指定模块生成测试点与风险台账。支持父模块名（如"知识管理"）或子模块名（如"01-分类管理"）。"""
        files = self._resolve_req_files(module_name)
        if not files:
            return False
        for f in files:
            self._testpoints_single_file(f)
        return True

    def testpoints_all(self):
        """为所有拆分后的需求模块执行第一步（测试点 + 风险台账）。"""
        files = self._all_req_files()
        if not files:
            return
        logger.info(f"设计智能体（第一步·测试点）：{len(files)} 个模块")
        for req_file in files:
            logger.info(f"  测试点设计中：{req_file.stem}")
            self._testpoints_single_file(req_file)

    # ==================== 第二步：测试用例 ====================

    def design_cases(self, module_name: str) -> bool:
        """第二步：为指定模块生成测试用例（消费最新批次测试点确认列）。支持父/子模块名。"""
        files = self._resolve_req_files(module_name)
        if not files:
            return False
        ok = True
        for f in files:
            ok = self._cases_single_file(f) and ok
        return ok

    def cases_all(self):
        """为所有拆分后的需求模块执行第二步（测试用例）。"""
        files = self._all_req_files()
        if not files:
            return
        logger.info(f"设计智能体（第二步·用例）：{len(files)} 个模块")
        for req_file in files:
            logger.info(f"  用例设计中：{req_file.stem}")
            self._cases_single_file(req_file)

    # ==================== 兼容入口：两步连续（旧 design 语义） ====================

    def design(self, module_name: str) -> bool:
        """旧语义兼容：测试点 + 用例两步连续执行（推荐分步以获得确认门禁）。"""
        return self.design_testpoints(module_name) and self.design_cases(module_name)

    def design_all(self):
        """旧语义兼容：所有模块测试点 + 用例两步连续执行。"""
        self.testpoints_all()
        self.cases_all()

    # ==================== 单文件执行 ====================

    def _testpoints_single_file(self, req_file: Path) -> bool:
        """第一步单文件：需求理解自适应 + 测试点 + 风险台账。"""
        actual_module = req_file.stem
        parent_module = req_file.parent.name
        module_no, clean_name = self._split_module(actual_module)
        tp_out_dir = TESTPOINTS_DIR / parent_module
        tp_out_dir.mkdir(parents=True, exist_ok=True)

        # 需求理解自适应：已有（根级固定名 / 子目录批次取最新）则消费，缺失则由本步生成
        uh_file = self._find_understanding(actual_module, parent_module)
        uh_out = TESTPOINTS_DIR / f"{actual_module}-需求理解.md"

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        prompt = load_prompt(
            "design_tp",
            拆分需求目录=str(req_file.parent.resolve()),
            模块或功能=actual_module,
            模块编号=module_no,
            模块名=clean_name,
            ID前缀=self._id_prefix(parent_module, clean_name),
            测试点目录=str(tp_out_dir.resolve()),
            时间戳=ts,
            需求理解状态=("已存在" if uh_file else "待生成"),
            需求理解文件=(str(uh_file.resolve()) if uh_file else "（未提供）"),
            需求理解输出路径=str(uh_out.resolve()),
        ) + self._prototype_block() + build_upstream_context(parent_module)

        task_name = f"design_tp_{actual_module}"
        raw = self.invoke_text(prompt, task_name=task_name)

        logger.info(f"  测试点设计完成：{parent_module}/{actual_module}")
        logger.info(f"  测试点目录：{tp_out_dir}")
        logger.info(f"  需求理解：{'消费已有 ' + uh_file.name if uh_file else '本步生成 ' + uh_out.name}")
        self._print_summary("测试点设计", actual_module, raw)
        return True

    def _cases_single_file(self, req_file: Path) -> bool:
        """第二步单文件：消费最新批次测试点（含确认列）生成用例。"""
        actual_module = req_file.stem
        parent_module = req_file.parent.name
        module_no, clean_name = self._split_module(actual_module)
        case_out_dir = CASES_DIR / parent_module
        case_out_dir.mkdir(parents=True, exist_ok=True)

        # 前置纪律：必须先有测试点批次（保证用例建立在拍板后的测试点之上）
        tp_dir = TESTPOINTS_DIR / parent_module
        tp_file = self._latest_batch(tp_dir, actual_module, "测试点")
        if tp_file is None:
            logger.error(f"未找到测试点批次，请先运行：python run.py testpoints {parent_module}")
            logger.error(f"  查找位置：{tp_dir}（{actual_module}-测试点_*.md）")
            return False

        # 同批次风险台账（可能未生成，如实告知）
        ledger = tp_dir / tp_file.name.replace("-测试点_", f"-{_LEDGER_MARK}_")
        ledger_path = str(ledger.resolve()) if ledger.exists() else "（同批次未生成）"

        uh_file = self._find_understanding(actual_module, parent_module)

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        prompt = load_prompt(
            "design_case",
            拆分需求目录=str(req_file.parent.resolve()),
            模块或功能=actual_module,
            模块编号=module_no,
            模块名=clean_name,
            ID前缀=self._id_prefix(parent_module, clean_name),
            测试用例目录=str(case_out_dir.resolve()),
            时间戳=ts,
            测试点文件=str(tp_file.resolve()),
            风险台账文件=ledger_path,
            需求理解文件=(str(uh_file.resolve()) if uh_file else "（未提供）"),
        ) + self._template_block() + self._prototype_block() + build_upstream_context(parent_module)

        task_name = f"design_case_{actual_module}"
        raw = self.invoke_text(prompt, task_name=task_name)

        logger.info(f"  用例设计完成：{parent_module}/{actual_module}")
        logger.info(f"  测试用例目录：{case_out_dir}")
        self._print_summary("用例设计", actual_module, raw, extra=f"（测试点批次：{tp_file.name}）")
        return True

    # ==================== 评审反馈优化 ====================

    def design_with_feedback(self, module_name: str, feedback) -> bool:
        """基于评审反馈优化测试用例（评审→优化闭环的核心入口）。

        读取当前最新批次用例文件，将评审反馈注入优化提示词，
        让 AI 做定向修补而非全量重生。

        参数：
            module_name: 模块名（父模块名或子模块名）
            feedback: ReviewFeedback 实例（来自 core.review_feedback）
        """
        files = self._resolve_req_files(module_name)
        if not files:
            return False
        ok = True
        for f in files:
            ok = self._optimize_single(f, feedback) and ok
        return ok

    def _optimize_single(self, req_file: Path, feedback) -> bool:
        """单文件优化：读取现有用例 + 注入评审反馈 → 生成优化后新版本。"""
        from core.review_feedback import build_optimize_prompt

        actual_module = req_file.stem
        parent_module = req_file.parent.name
        module_no, clean_name = self._split_module(actual_module)
        case_out_dir = CASES_DIR / parent_module

        # 找到当前最新的用例文件
        case_module_dir = case_out_dir
        latest_case = None
        if case_module_dir.exists():
            cands = (sorted(case_module_dir.glob(f"*{clean_name}*用例*.md"))
                     + sorted(case_module_dir.glob("*-用例*.md")))
            hits = [p for p in cands if "archive" not in p.parts]
            if hits:
                latest_case = sorted(hits, key=lambda p: p.stat().st_mtime)[-1]

        if not latest_case or not latest_case.exists():
            logger.error(f"未找到现有用例文件，无法优化：{module_name}")
            return False

        case_content = latest_case.read_text(encoding="utf-8")
        ts = datetime.now().strftime("%Y%m%d_%H%M")

        prompt = build_optimize_prompt(
            case_content=case_content,
            feedback=feedback,
            module_name=clean_name,
            module_no=module_no,
            id_prefix=self._id_prefix(parent_module, clean_name),
            output_dir=str(case_out_dir.resolve()),
            timestamp=ts,
        ) + self._template_block() + self._prototype_block() + build_upstream_context(parent_module)

        task_name = f"design_case_opt_{actual_module}"
        raw = self.invoke_text(prompt, task_name=task_name)

        logger.info(f"  用例优化完成：{parent_module}/{actual_module}（基于评审反馈）")
        self._print_summary("用例优化（评审反馈）", actual_module, raw,
                            extra=f"（原文件：{latest_case.name}）")
        return True

    # ==================== 辅助 ====================

    @staticmethod
    def _split_module(actual_module: str) -> tuple[str, str]:
        """拆分模块 stem：'01-分类管理' -> ('01', '分类管理')；无编号时返回 ('01', 原名)。"""
        m = re.match(r"^(\d+)[、_.\-\s]+(.+)$", actual_module)
        if m:
            return m.group(1), m.group(2).strip()
        return "01", actual_module

    @staticmethod
    def _id_prefix(parent_module: str, clean_name: str) -> str:
        """用例/测试点 ID 前缀：「业务模块名-子模块名」（如 知识管理-分类管理）。

        未拆分子模块（需求文件直接在 02 拆分根目录、或父目录名与子模块同名）时退化为「模块名」（如 首页）。
        生成侧模板以 `{ID前缀}` 占位：TC-{ID前缀}-NNN / TP-{ID前缀}-NNN，保证全局唯一不撞号。
        """
        raw_parent = (parent_module or "").strip()
        # 注意：「02_split_requirements」目录名本身以数字开头，清洗后为 "split_requirements"，需与清洗值比对
        parent = re.sub(r"^\d+[、_.\-\s]+", "", raw_parent).strip()
        split_dir = re.sub(r"^\d+[、_.\-\s]+", "", SPLIT_REQUIREMENTS_DIR.name).strip()
        if not parent or parent == split_dir or parent == clean_name:
            return clean_name
        return f"{parent}-{clean_name}"

    def _find_understanding(self, actual_module: str, parent_module: str) -> Path | None:
        """查找该子模块已有的需求理解文件（根级固定名 + 子目录批次，兼容数字前缀），按 mtime 取最新。"""
        return find_latest_understanding(actual_module, parent_module)

    @staticmethod
    def _latest_batch(d: Path, prefix: str, suffix: str) -> Path | None:
        """目录 d 下 {prefix}-{suffix}_*.md 的最新批次（prefix 允许带数字前缀，排除 archive；文件名时间戳排序取最新）。"""
        if not d.is_dir():
            return None
        clean = re.sub(r"^\d+[、_.\-\s]+", "", prefix).strip()
        cands = [p for p in d.glob(f"*{suffix}_*.md")
                 if _ARCHIVE not in p.parts
                 and re.sub(r"^\d+[、_.\-\s]+", "", p.stem).startswith(f"{clean}-{suffix}_")]
        return sorted(cands)[-1] if cands else None

    def _resolve_req_files(self, module_name: str) -> list[Path]:
        """父模块名 -> 子目录下全部需求正文文件；子模块名 -> 单文件。"""
        clean = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        subdir = SPLIT_REQUIREMENTS_DIR / module_name
        if not subdir.exists():
            subdir = SPLIT_REQUIREMENTS_DIR / clean
        if subdir.exists() and subdir.is_dir():
            files = self._req_files_in(subdir)
            if not files:
                logger.error(f"子目录为空：{subdir}")
            return files
        req_file = self._find_req_file(module_name)
        if not req_file:
            logger.error(f"拆分需求文件未找到：{module_name}")
            return []
        return [req_file]

    @staticmethod
    def _req_files_in(subdir: Path) -> list[Path]:
        """子目录内的需求正文文件（排除风险清单与待确认汇总——由风险台账承接专门处理）。"""
        return [p for p in sorted(subdir.glob("*.md")) if _LEDGER_MARK not in p.name]

    def _all_req_files(self) -> list[Path]:
        """所有拆分后的需求正文文件（子目录 + 根目录兼容）。"""
        files: list[Path] = []
        for subdir in sorted(SPLIT_REQUIREMENTS_DIR.iterdir()):
            if subdir.is_dir():
                files += self._req_files_in(subdir)
        files += [p for p in sorted(SPLIT_REQUIREMENTS_DIR.glob("*.md"))
                  if _LEDGER_MARK not in p.name]
        if not files:
            logger.error(f"未找到拆分后的需求文件：{SPLIT_REQUIREMENTS_DIR}")
        return files

    def _find_req_file(self, module_name: str) -> Path | None:
        """查找模块的需求文件（支持子目录结构）。"""
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        search_names = [module_name, clean_name] if clean_name != module_name else [module_name]

        # 先在子目录中查找
        for subdir in SPLIT_REQUIREMENTS_DIR.iterdir():
            if subdir.is_dir():
                for f in subdir.glob("*.md"):
                    if _LEDGER_MARK in f.name:
                        continue
                    for name in search_names:
                        if name in f.stem or f.stem in name:
                            return f

        # 回退：在根目录查找
        return find_module_file(SPLIT_REQUIREMENTS_DIR, module_name, [".md"])

    @staticmethod
    def _prototype_block() -> str:
        """原型参考块（未配置原型时返回空串）。"""
        if not PROTOTYPE_URL:
            return ""
        return (f"\n\n## 原型参考\n\n在线原型地址：{PROTOTYPE_URL}\n"
                "设计时请参考原型界面，确保操作步骤和预期结果与实际 UI 一致。")

    @staticmethod
    def _template_block() -> str:
        """用例格式模板块（模板缺失时优雅降级为空串）。"""
        template_path = ROOT / "templates" / "test_case_template.xlsx"
        if not template_path.exists():
            return ""
        return (f"\n\n## 用例格式模板\n\n请严格参照模板文件生成用例：{template_path.resolve()}\n"
                "模板为导出视图（13 字段），本步骤在其基础上追加「确认结论(业务填)」为第 14 字段，"
                "其余填写规范请参照 templates/README.md。")

    @staticmethod
    def _print_summary(title: str, name: str, raw: str, extra: str = ""):
        """统一输出 Qoder 回复摘要（GBK 控制台安全）。"""
        print(f"\n{'=' * 60}")
        print(f"  {title}：{name}{extra}")
        print(f"{'=' * 60}")
        safe_text = raw[:500].encode("gbk", errors="replace").decode("gbk")
        print(safe_text)
        if len(raw) > 500:
            print("...")
