"""
上游业务基线上下文 —— 打通「探索 / 业务梳理」与「分析 / 理解 / 设计」的数据链。

背景：
  流水线中 00_explore（系统探索）与 01_business（业务梳理）产出的页面事实与业务全景图，
  过去只被 business_agent 单向消费，下游 analyze/understand/design 直接读 inputs 需求，
  导致探索与业务梳理成为「孤儿分支」。本模块提供一个共享 helper，
  在下游三个 agent 构建提示词时，注入「请先阅读上游业务基线」的显式引用。

设计约束：
  - 返回纯文本块，供调用方在 load_prompt(...).format 之后用字符串拼接追加，
    因此本模块内的文本不参与 str.format，可安全包含花括号。
  - 找不到任何上游产物时返回空字符串（优雅降级，不污染提示词）。
"""
import re
from pathlib import Path

from core.config import BUSINESS_DIR, EXPLORE_DIR


def _clean(name: str) -> str:
    """去除数字前缀（如 '1、首页' -> '首页'，'03-项目维护' -> '项目维护'）。"""
    return re.sub(r"^\d+[、_.\-\s]+", "", name).strip()


def _find_business(module_hint: str) -> Path | None:
    """在 01_business 下模糊查找该模块的业务全景图。"""
    if not BUSINESS_DIR.exists():
        return None
    clean = _clean(module_hint)
    # 精确：{clean}-业务全景图.md
    exact = BUSINESS_DIR / f"{clean}-业务全景图.md"
    if exact.exists():
        return exact
    # 回退：文件名包含 clean 的业务全景图
    if clean:
        for p in sorted(BUSINESS_DIR.glob("*-业务全景图.md")):
            if clean in p.stem or p.stem.replace("-业务全景图", "") in clean:
                return p
    return None


def _find_explore(module_hint: str) -> list[Path]:
    """在 00_explore 下查找与模块相关的功能地图 / 页面探索记录。"""
    if not EXPLORE_DIR.exists():
        return []
    clean = _clean(module_hint)
    if not clean:
        return []
    hits = []
    for p in sorted(EXPLORE_DIR.rglob("*.md")):
        if clean in p.stem:
            hits.append(p)
    return hits


def _find_system_business() -> Path | None:
    """查找系统级业务全景图（约定 `00-` 前缀，如 `00-空气系统-业务全景图.md`）。

    系统级全景图是跨模块的全局业务基线，对**所有模块**都应注入，
    与按模块名匹配的模块级全景图互补。
    """
    if not BUSINESS_DIR.exists():
        return None
    for p in sorted(BUSINESS_DIR.glob("00-*-业务全景图.md")):
        return p
    return None


def _find_system_explore() -> list[Path]:
    """查找系统级探索产物（`全站/` 子目录 + 前缀/关键词放宽）。

    实际产物按主题批次落在 `output/00_explore/全站/` 子目录
    （如 `00-功能地图-20260915_1657.md`、`zgn-全系统探索记录-第2版-*.md`），
    旧实现只匹配根级 `00-*.md`，而根级从未产出过此类文件，注入始终为空。
    现放宽为命中其一即算系统级：
      1) 路径含「全站」目录；
      2) 文件名含「全系统」；
      3) 根级 `00-` 前缀（原约定兜底）。
    """
    if not EXPLORE_DIR.exists():
        return []
    hits: list[Path] = []
    for p in sorted(EXPLORE_DIR.rglob("*.md")):
        if "archive" in p.parts:
            continue
        if ("全站" in p.parts
                or "全系统" in p.stem
                or (p.parent == EXPLORE_DIR and p.stem.startswith("00-"))):
            hits.append(p)
    return hits


def build_upstream_context(module_hint: str) -> str:
    """
    根据模块名（父模块或子模块均可）构建上游业务基线引用块。

    参数：
        module_hint: 模块名，可带数字前缀，可为父模块（如 '项目管理'）或含子模块路径。

    返回：
        Markdown 文本块；若无任何上游产物，返回空字符串。
    """
    # 系统级（`00-` 前缀，全局基线）+ 模块级（按模块名匹配），去重后合并
    sys_business = _find_system_business()
    business = _find_business(module_hint)
    sys_explore = _find_system_explore()
    explore = _find_explore(module_hint)

    # 去重：模块级命中可能等于系统级文件
    seen: set[str] = set()
    biz_list: list[Path] = []
    for p in [sys_business, business]:
        if p and str(p.resolve()) not in seen:
            seen.add(str(p.resolve()))
            biz_list.append(p)
    exp_list: list[Path] = []
    for p in sys_explore + explore:
        if p and str(p.resolve()) not in seen:
            seen.add(str(p.resolve()))
            exp_list.append(p)

    if not biz_list and not exp_list:
        return ""

    lines = ["", "", "## 上游业务基线（务必先阅读，再开始本步骤）", ""]
    lines.append(
        "以下产物来自「系统探索(00_explore)」与「业务梳理(01_business)」，"
        "是比原始需求更贴近真实页面的事实基线。请以此为参照，不要臆测页面结构："
    )
    lines.append("")

    for p in biz_list:
        level = "系统级" if p is sys_business else "模块级"
        lines.append(
            f"- 【{level}】业务全景图（角色/权限/实体与关系/数据流/模块依赖/流程与跨模块链路/状态机/术语/需求缺口）：`{p.resolve()}`"
        )
    for p in exp_list:
        level = "系统级" if p in sys_explore else "模块级"
        kind = "功能地图" if "功能地图" in p.stem else "页面探索记录"
        lines.append(f"- 【{level}】{kind}：`{p.resolve()}`")

    lines.append("")
    if biz_list:
        lines.append(
            "使用要求：\n"
            "1. 拆分/理解/设计前先对齐业务全景图中的功能清单与权限矩阵，确保不遗漏已确认功能。\n"
            "2. 当业务全景图的「需求缺口与实现差异」记录了页面事实与需求不一致项时，"
            "在风险/待确认清单中显式引用，不要按需求想当然。\n"
            "3. 探索产物中出现但需求未提及的入口/字段，标注为『实现超出需求，待确认』，不得虚构。\n"
            "4. 设计测试点/用例时用业务全景图的稳定ID（BA-/ENT-/FLOW-）建立可追溯矩阵；"
            "第5.2节每条跨模块端到端链路至少对应一条完整旅程用例（覆盖用户动作→最终可见状态，而非单模块单跳）；"
            "第4.3节模块依赖决定集成/回归测试的范围与顺序。\n"
            "5. 存在系统级全景图时，先据其跨模块数据流/依赖/关键路径定位本模块在整体中的位置，再展开模块级细节。\n"
            "6. 上游产物确认列（业务全景图第7/8节「确认结论(业务填)」、风险清单与待确认汇总、需求理解待确认表）"
            "已写 `✅ <结论>` 的项视为业务已拍板事实：直接按结论执行、不得再标记待确认或重复提问，"
            "对应测试点「是否依赖确认」填「否」并在备注引用结论；"
            "仍为 `⬜ <问句>` 的项才标记待确认并引用该问句。"
        )
    else:
        lines.append(
            f"提示：该模块尚未生成业务全景图，可先运行 `python run.py business {_clean(module_hint)}` "
            "补齐业务基线后再进入本步骤（非阻塞，探索产物仍可作为事实参照）。"
        )

    return "\n".join(lines)
