"""
业务梳理智能体 —— 流水线独立阶段：交叉比对「系统探索产物 + 原始需求」，输出业务全景图。

定位（与 explore/analyze/design 平级）：
  系统探索(00_explore) → 【业务梳理(01_business)】 → 需求拆分(02_split) → 需求理解/测试点/用例设计(03_design) → 评审(04) → 导出(05) → 执行报告(06)

输入：
  - 原始需求文档：inputs/requirements/{n}、{模块}.md
  - 系统探索产物：output/00_explore/*（功能地图 / 页面探索记录）、
                  output/02_split_requirements/{模块}/*基于页面探索*.md
输出：
  - output/01_business/{模块}-业务全景图.md

说明：业务全景图模板内含大量示例花括号，不能用 str.format，
      故本 agent 直接读取提示词文件并做定向替换。
"""
import re
from pathlib import Path
from datetime import datetime
from agents.base_agent import BaseAgent
from core.config import (
    SPEC_DIR, EXPLORE_DIR, SPLIT_REQUIREMENTS_DIR, BUSINESS_DIR,
)
from utils.logger import get_logger

logger = get_logger("business")

PROMPT_FILE = Path(__file__).parent / "business_prompt.md"


class BusinessAgent(BaseAgent):
    """业务梳理智能体 —— 生成业务全景图。"""
    role = "business"

    def __init__(self):
        super().__init__()

    # ---------- 输入定位 ----------

    def _clean(self, name: str) -> str:
        return re.sub(r"^\d+[、_.\-\s]+", "", name).strip()

    def _find_req_file(self, module_name: str) -> Path | None:
        """在 inputs/requirements 下模糊匹配模块的原始需求文件。"""
        clean = self._clean(module_name)
        cands = sorted(list(SPEC_DIR.glob("*.md")) + list(SPEC_DIR.glob("*.txt")))
        for f in cands:
            if clean in f.stem or module_name in f.stem:
                return f
        return None

    def _find_explore_files(self, module_name: str) -> list[Path]:
        """收集与该模块相关的系统探索产物（页面事实）。"""
        clean = self._clean(module_name)
        found: list[Path] = []
        # 00_explore 下的功能地图 / 探索记录
        if EXPLORE_DIR.exists():
            for p in sorted(EXPLORE_DIR.rglob("*.md")):
                if clean and clean in p.stem:
                    found.append(p)
        # 02_split_requirements/{模块} 下基于页面探索的校准报告
        for base in (SPLIT_REQUIREMENTS_DIR / module_name, SPLIT_REQUIREMENTS_DIR / clean):
            if base.exists() and base.is_dir():
                for p in sorted(base.glob("*.md")):
                    if ("探索" in p.stem or "功能地图" in p.stem or "校准" in p.stem) and p not in found:
                        found.append(p)
        return found

    # ---------- 主流程 ----------

    def analyze(self, module_name: str) -> bool:
        """为指定模块生成业务全景图。支持带/不带数字前缀的模块名（如 '首页' 或 '1、首页'）。"""
        clean = self._clean(module_name)
        output_file = BUSINESS_DIR / f"{clean}-业务全景图.md"

        if output_file.exists() and output_file.stat().st_size > 0:
            logger.info(f"  业务全景图已存在，跳过：{output_file}")
            return True

        req_file = self._find_req_file(module_name)
        if not req_file:
            logger.error(f"  未找到原始需求文件：{module_name}（目录 {SPEC_DIR}）")
            return False

        explore_files = self._find_explore_files(module_name)
        if explore_files:
            explore_block = "\n".join(f"  - {p.resolve()}" for p in explore_files)
        else:
            explore_block = "  - （未找到系统探索产物，仅基于需求文档梳理，并在第 7 节注明未做页面比对）"

        prompt = self._render_prompt(
            模块=clean,
            需求文件路径=str(req_file.resolve()),
            探索产物清单=explore_block,
            输出文件=str(output_file.resolve()),
        )

        task_name = f"business_{clean}"
        raw = self.invoke_text(prompt, task_name=task_name)

        logger.info(f"  业务梳理完成：{clean}")
        logger.info(f"  输出文件：{output_file}")
        print(f"\n{'=' * 60}")
        print(f"  业务全景图：{clean}   （探索产物 {len(explore_files)} 份）")
        print(f"{'=' * 60}")
        print(raw[:500].encode("gbk", errors="replace").decode("gbk"))
        if len(raw) > 500:
            print("...")
        return True

    def analyze_all(self):
        """为 inputs/requirements 下的所有模块生成业务全景图。"""
        docs = sorted(list(SPEC_DIR.glob("*.md")) + list(SPEC_DIR.glob("*.txt")))
        if not docs:
            logger.error(f"未找到需求文档：{SPEC_DIR}")
            return
        modules = []
        seen = set()
        for d in docs:
            clean = self._clean(d.stem)
            if clean not in seen:
                seen.add(clean)
                modules.append(clean)
        logger.info(f"业务梳理智能体：{len(modules)} 个模块")
        for m in modules:
            logger.info(f"  梳理中：{m}")
            self.analyze(m)

    # ---------- 模板渲染（绕开 str.format） ----------

    def _render_prompt(self, **tokens: str) -> str:
        template = PROMPT_FILE.read_text(encoding="utf-8")
        # 模板正文里的 {模块} 等占位符做定向替换；示例花括号原样保留
        replacements = {
            "{模块}": tokens.get("模块", ""),
            "{需求文件路径}": tokens.get("需求文件路径", ""),
            "{探索产物清单}": tokens.get("探索产物清单", ""),
            "{输出文件}": tokens.get("输出文件", ""),
            "{时间}": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        for k, v in replacements.items():
            template = template.replace(k, v)
        return template
