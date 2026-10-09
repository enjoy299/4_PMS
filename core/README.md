# core/ — 核心模块

这个文件夹包含框架的核心基础设施，被各个智能体共同使用。

## 文件说明

| 文件 | 用途 |
|------|------|
| `__init__.py` | 包初始化文件，标记 core 为 Python 包 |
| `config.py` | 配置中心。读取 `.env`（目标网址、测试账号、运行参数、导出格式等），定义 output/00~06 各阶段目录常量，并提供 `get_module_dir()`/`find_module_file()` 供各模块定位路径与模糊查找模块文件 |
| `brain.py` | Qoder 桥接器。不再直连远程模型，而是通过文件与 Qoder 对话交互：`save_prompt()` 把提示词存到 `ai_workspace/` 并复制到剪贴板，`read_response()` 从 `_response.md` 或终端粘贴读取 Qoder 的回复（消费后自动归档为 `*_response_consumed_*.md`，防重跑串轮） |
| `hooks.py` | 生命周期钩子。在 AI 操控浏览器的每一步自动截图和记录日志，方便回溯测试过程 |
| `human_confirm.py` | 人工确认机制。当 AI 遇到不确定的内容时暂停，让人类审核（保留/删除/修改测试点、审核测试用例） |
| `prototype_loader.py` | 在线原型加载器。读取配置文件，让 AI 打开原型网站截图，供分析需求时参考 UI 布局 |
