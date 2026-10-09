#!/usr/bin/env python3
"""
原型截图脚本 —— 使用 Playwright 截取在线原型页面。

使用方法：
    python scripts/run_prototype.py              # 截取所有配置的原型
    python scripts/run_prototype.py 知识管理      # 截取指定模块的原型
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.prototype_loader import PrototypeLoader


def main():
    loader = PrototypeLoader()

    if len(sys.argv) > 1:
        module_name = sys.argv[1]
        proto = loader.get_prototype(module_name)
        if proto:
            print(f"截取原型：{proto['name']}")
            paths = loader.capture_prototype(module_name)
            print(f"  已保存 {len(paths)} 张截图")
        else:
            print(f"未找到 '{module_name}' 的原型配置")
            print(f"请编辑 inputs/online_prototypes.yaml 添加配置")
        return

    results = loader.capture_all()
    if not results:
        print("未配置任何在线原型，请编辑 inputs/online_prototypes.yaml")
    for module, paths in results.items():
        print(f"  {module}: {len(paths)} 张截图已保存")


if __name__ == "__main__":
    main()
