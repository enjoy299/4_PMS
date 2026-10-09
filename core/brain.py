"""
Qoder 桥接器 —— 通过文件与 Qoder 对话交互。

改造说明：
  原版本使用 langchain_openai 的 ChatOpenAI 调用远程 AI 模型。
  改造后，AI 分析全部由 Qoder 对话完成，本模块负责：
    1. 把提示词保存到文件（自动复制到剪贴板）
    2. 等待用户从 Qoder 对话中粘贴结果
    3. 读取结果文件供后续脚本使用

工作流程：
  脚本运行 → 生成提示词 → 用户粘贴到 Qoder → Qoder 返回结果 → 用户粘贴回终端

防串轮：回复一经消费立即归档（{task}_response_consumed_*.md），
  同一任务重跑时不会静默读到上一轮遗留的旧回复。
"""
import sys
from datetime import datetime
from pathlib import Path
from core.config import AI_WORKSPACE_DIR
from utils.logger import get_logger

logger = get_logger("brain")


def save_prompt(task_name: str, prompt: str, image_paths: list[Path] | None = None) -> Path:
    """
    保存提示词到文件并复制到剪贴板。

    参数：
        task_name: 任务名称（如 analyze_example、design_example）
        prompt: 要发给 Qoder 的提示词文本
        image_paths: 可选的图片路径列表（如有图片，会在提示词末尾列出）

    返回：
        提示词文件路径
    """
    # 如果有图片，在提示词末尾列出路径
    if image_paths:
        prompt += "\n\n## 参考图片路径\n"
        for img in image_paths:
            if img.exists():
                prompt += f"- {img.resolve()}\n"

    prompt_file = AI_WORKSPACE_DIR / f"{task_name}_prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    logger.info(f"  提示词已保存：{prompt_file}")

    # 尝试复制到系统剪贴板
    _copy_to_clipboard(prompt)

    return prompt_file


def read_response(task_name: str) -> str:
    """
    读取 Qoder 返回的结果。

    两种读取方式：
    1. 从文件读取（ai_workspace/{task_name}_response.md）
    2. 从终端粘贴（用户直接把 Qoder 的输出粘贴进来）

    防串轮：无论文件读取还是终端粘贴，回复一经消费即改名归档为
    `{task_name}_response_consumed_{时间戳}.md`，日志带上原文件写入时间；
    同一任务重跑时不会静默消费上一轮遗留的旧回复，需重新提供。

    参数：
        task_name: 任务名称

    返回：
        Qoder 返回的结果文本
    """
    response_file = AI_WORKSPACE_DIR / f"{task_name}_response.md"

    print(f"\n{'=' * 60}")
    print(f"  请将 Qoder 的回复粘贴到下方（或先保存到文件后按回车）：")
    print(f"  文件路径：{response_file}")
    print(f"{'=' * 60}")

    # 尝试从文件读取（消费成功后立即归档，避免下次重跑串轮）
    if response_file.exists():
        content = response_file.read_text(encoding="utf-8").strip()
        if content:
            mtime = datetime.fromtimestamp(response_file.stat().st_mtime)
            archived = _archive_consumed_response(response_file)
            logger.info(f"  已从文件读取响应（写入时间 {mtime:%Y-%m-%d %H:%M:%S}），"
                        f"已消费并归档：{archived.name}")
            return content

    # 文件为空或不存在，等待用户从终端粘贴
    print("  （文件为空，请粘贴 Qoder 的回复，然后按两次回车结束）")
    lines = []
    empty_count = 0
    while True:
        try:
            line = input()
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0
            lines.append(line)
        except EOFError:
            break

    content = "\n".join(lines).strip()
    if content:
        response_file.write_text(content, encoding="utf-8")
        archived = _archive_consumed_response(response_file)
        logger.info(f"  响应已保存并归档：{archived.name}（重跑需重新提供，不会复用）")
    return content


def _archive_consumed_response(response_file: Path) -> Path:
    """把已消费的响应文件改名归档，避免同一任务重跑时串轮读到旧回复。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = response_file.with_name(f"{response_file.stem}_consumed_{ts}.md")
    seq = 1
    while archive.exists():
        archive = response_file.with_name(f"{response_file.stem}_consumed_{ts}_{seq}.md")
        seq += 1
    response_file.rename(archive)
    return archive


def _copy_to_clipboard(text: str):
    """尝试将文本复制到系统剪贴板。"""
    try:
        if sys.platform == "win32":
            import subprocess
            process = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            process.communicate(text.encode("utf-16-le"))
            logger.info("  提示词已复制到剪贴板")
        elif sys.platform == "darwin":
            import subprocess
            process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            process.communicate(text.encode("utf-8"))
            logger.info("  提示词已复制到剪贴板")
    except Exception:
        logger.info("  （无法自动复制到剪贴板，请手动从文件中复制）")
