"""
智能体提示词加载器 —— 从 .md 文件加载提示词模板。

功能：
  1. 从 agents/ 目录加载 .md 提示词文件
  2. 支持变量替换（如 {app_url}、{module} 等）
  3. 缓存已加载的提示词，避免重复读取
  4. fail-loud 渲染：缺参保留占位符原文并 WARNING 点名；孤立花括号不崩溃、告警后返回原模板

使用示例：
    from agents.agent_loader import load_prompt

    prompt = load_prompt("analyst", app_url="http://...", module="知识管理")
"""
import re
from pathlib import Path
from utils.logger import get_logger

logger = get_logger("agent_loader")

# 提示词文件目录
PROMPTS_DIR = Path(__file__).parent

# 提示词缓存
_prompt_cache = {}

# 模板中的单层占位符（排除 {{...}} 转义写法；字段名不含 :/! 等格式规格字符）
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([^{}\n:!]+)\}")


class _KeepMissing(dict):
    """format_map 兜底字典：缺失的键保留 `{key}` 原文，而不是抛 KeyError 丢弃整份模板。"""

    def __missing__(self, key):
        return "{" + key + "}"


def load_prompt(agent_name: str, **kwargs) -> str:
    """
    加载指定智能体的提示词模板，并进行变量替换。

    参数：
        agent_name: 智能体名称（如 "analyst"、"designer"、"reviewer"）
        **kwargs: 要替换的变量（如 app_url="...", module="..."）

    返回：
        替换后的提示词文本

    fail-loud 行为约定：
        - 模板要求而调用方未传的变量：占位符保留原文，并 WARNING 点名（不静默降级）；
        - 模板含孤立花括号（未配对的 { 或 }）：不崩溃，ERROR 告警后返回原模板，
          字面花括号请在模板中写成 {{ }} 转义。

    示例：
        prompt = load_prompt("analyst", app_url="http://...", module="知识管理")
    """
    # 检查缓存
    cache_key = agent_name
    if cache_key in _prompt_cache:
        template = _prompt_cache[cache_key]
    else:
        # 从文件加载
        prompt_file = PROMPTS_DIR / f"{agent_name}_prompt.md"
        if not prompt_file.exists():
            logger.error(f"提示词文件未找到：{prompt_file}")
            return ""

        template = prompt_file.read_text(encoding="utf-8")
        _prompt_cache[cache_key] = template
        logger.info(f"已加载提示词：{prompt_file.name}")

    # 缺参检测：渲染前点名缺失变量（fail-loud；对应占位符将由 __missing__ 保留原文）
    required = set(_PLACEHOLDER_RE.findall(template))
    missing = sorted(required - set(kwargs))
    if missing:
        logger.warning(f"提示词缺参 {missing}（{agent_name}_prompt.md），"
                       f"对应占位符将保留原样，请检查调用方是否漏传")

    # 变量替换：__missing__ 兜底保留缺失占位符原文；孤立花括号不再崩溃
    try:
        return template.format_map(_KeepMissing(kwargs))
    except (KeyError, ValueError, IndexError) as e:
        logger.error(f"提示词渲染失败（{type(e).__name__}: {e}），返回未替换模板："
                     f"{agent_name}_prompt.md（字面花括号请用 {{{{ }}}} 转义）")
        return template


def clear_cache():
    """清空提示词缓存。"""
    _prompt_cache.clear()
    logger.info("提示词缓存已清空")


def list_prompts() -> list[Path]:
    """列出所有可用的提示词文件。"""
    return sorted(PROMPTS_DIR.glob("*_prompt.md"))
