"""
需求理解智能体 —— 流水线第 2 步：生成需求理解文档供用户确认。

输出文件：output/03_design/test_points/{模块编号}-{模块名}-需求理解.md
"""
from pathlib import Path
from agents.base_agent import BaseAgent
from agents.agent_loader import load_prompt
from core.config import SPLIT_REQUIREMENTS_DIR, TESTPOINTS_DIR, find_module_file, find_latest_understanding
from agents.upstream_context import build_upstream_context
from utils.logger import get_logger

logger = get_logger("understanding")


class UnderstandingAgent(BaseAgent):
    """需求理解智能体类 —— 负责生成需求理解文档。"""
    role = "understanding"

    def understand(self, module_name: str) -> bool:
        """为指定模块生成需求理解文档。支持父模块名（如"项目管理"）或子模块名（如"01-项目概述"）。"""
        import re
        
        # 先检查是否是父模块名（对应子目录）
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        subdir = SPLIT_REQUIREMENTS_DIR / module_name
        if not subdir.exists():
            subdir = SPLIT_REQUIREMENTS_DIR / clean_name
        
        if subdir.exists() and subdir.is_dir():
            # 处理子目录下的所有文件
            files = sorted(subdir.glob("*.md"))
            if not files:
                logger.error(f"子目录为空：{subdir}")
                return False
            for f in files:
                self._understand_single_file(f)
            return True
        
        # 否则按单个文件查找
        req_file = self._find_req_file(module_name)
        if not req_file:
            logger.error(f"拆分需求文件未找到：{module_name}")
            return False
        return self._understand_single_file(req_file)

    def _understand_single_file(self, req_file: Path) -> bool:
        """为单个拆分需求文件生成需求理解文档。"""
        actual_module = req_file.stem

        # 上游业务基线：拆分需求所在子目录名即父模块名
        module_hint = req_file.parent.name or actual_module
        if module_hint == SPLIT_REQUIREMENTS_DIR.name:
            module_hint = actual_module

        # 检查是否已存在需求理解文档（根级固定名 / 子目录批次，兼容数字前缀）
        existing = find_latest_understanding(actual_module, module_hint)
        if existing:
            logger.info(f"  需求理解文档已存在，跳过：{existing}")
            return True

        # 从 .md 文件加载提示词
        prompt = load_prompt(
            "understanding",
            拆分需求目录=str(req_file.parent.resolve()),
            模块或功能=actual_module,
            输出目录=str(TESTPOINTS_DIR.resolve()),
        ) + build_upstream_context(module_hint)

        task_name = f"understand_{actual_module}"
        raw = self.invoke_text(prompt, task_name=task_name)

        logger.info(f"  需求理解完成：{actual_module}")
        logger.info(f"  输出目录：{TESTPOINTS_DIR}")
        
        # 显示 Qoder 的回复摘要
        print(f"\n{'=' * 60}")
        print(f"  需求理解：{actual_module}")
        print(f"{'=' * 60}")
        safe_text = raw[:500].encode('gbk', errors='replace').decode('gbk')
        print(safe_text)
        if len(raw) > 500:
            print("...")
        
        return True

    def understand_all(self):
        """为所有拆分后的需求模块生成需求理解文档。"""
        # 收集所有模块名
        module_names = set()
        for f in SPLIT_REQUIREMENTS_DIR.glob("*.md"):
            module_names.add(f.stem)
        for subdir in SPLIT_REQUIREMENTS_DIR.iterdir():
            if subdir.is_dir():
                for f in subdir.glob("*.md"):
                    module_names.add(f.stem)
        
        if not module_names:
            logger.error(f"未找到拆分后的需求文件：{SPLIT_REQUIREMENTS_DIR}")
            return
        
        logger.info(f"需求理解智能体：{len(module_names)} 个模块")
        for module_name in sorted(module_names):
            logger.info(f"  理解中：{module_name}")
            self.understand(module_name)

    def _find_req_file(self, module_name: str) -> Path | None:
        """查找模块的需求文件（支持子目录结构）。"""
        import re
        clean_name = re.sub(r"^\d+[、_.\-\s]+", "", module_name).strip()
        search_names = [module_name, clean_name] if clean_name != module_name else [module_name]
        
        # 先在子目录中查找
        for subdir in SPLIT_REQUIREMENTS_DIR.iterdir():
            if subdir.is_dir():
                for f in subdir.glob("*.md"):
                    for name in search_names:
                        if name in f.stem or f.stem in name:
                            return f
        
        # 回退：在根目录查找
        return find_module_file(SPLIT_REQUIREMENTS_DIR, module_name, [".md"])
