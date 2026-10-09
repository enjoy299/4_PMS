"""
基础智能体 —— 所有 AI 智能体的共同父类。

改造说明：
  原版本使用 ChatOpenAI 和 browser-use 库。
  改造后，AI 分析通过 Qoder 对话完成（文件交互），
  浏览器操作通过 Playwright 纯脚本完成。

本类提供两个核心方法：
  1. invoke_text() —— 发送文字提示词给 Qoder，获取回复
  2. invoke_with_images() —— 发送文字+图片提示词给 Qoder，获取回复
"""
from pathlib import Path
from core.brain import save_prompt, read_response
from utils.logger import get_logger

logger = get_logger("base_agent")


class BaseAgent:
    """
    基础智能体类。
    所有其他智能体（AnalystAgent、DesignerAgent 等）都继承自这个类。

    改造后不再创建 AI 模型连接，而是通过文件与 Qoder 对话交互。
    """
    role: str = "base"

    def __init__(self, **kwargs):
        """
        初始化智能体。

        改造后不再需要 temperature 等 AI 参数，
        保留 **kwargs 以兼容子类调用。
        """
        pass

    def invoke_text(self, prompt: str, task_name: str = "") -> str:
        """
        发送纯文字提示词给 Qoder，获取回复。

        工作流程：
        1. 把提示词保存到 ai_workspace/ 目录（自动复制到剪贴板）
        2. 等待用户从 Qoder 对话中粘贴结果
        3. 返回 Qoder 的回复文字

        参数：
            prompt: 要问 Qoder 的问题
            task_name: 任务标识符（用于文件命名，默认使用 role）

        返回：
            Qoder 的回复文字
        """
        if not task_name:
            task_name = self.role
        save_prompt(task_name, prompt)
        return read_response(task_name)

    def invoke_with_images(self, prompt: str, image_paths: list[Path],
                           task_name: str = "") -> str:
        """
        发送文字 + 图片提示词给 Qoder，获取回复。

        工作流程：
        1. 把提示词和图片路径保存到文件
        2. 用户在 Qoder 中手动打开图片并粘贴提示词
        3. 等待用户粘贴 Qoder 的回复

        参数：
            prompt: 要问 Qoder 的问题
            image_paths: 图片文件路径列表
            task_name: 任务标识符

        返回：
            Qoder 的回复文字
        """
        if not task_name:
            task_name = self.role
        # 过滤掉不存在的图片
        valid_images = [p for p in image_paths if p.exists()]
        save_prompt(task_name, prompt, valid_images)
        return read_response(task_name)
