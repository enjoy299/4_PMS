# exporters/ — 数据导出器

这个文件夹负责把 AI 生成的数据导出为文件，方便人查看和存档。

## 文件说明

| 文件 | 用途 | 输出格式 |
|------|------|----------|
| `__init__.py` | 包初始化文件，标记 exporters 为 Python 包 |
| `report_exporter.py` | 导出测试报告 | Markdown (.md) + HTML (.html) + Excel (.xlsx) |

## 输出位置

所有输出均写入 `output/` 目录下：

- 测试报告 → `output/06_reports/markdown/`、`output/06_reports/html/`、`output/06_reports/excel/`

报告文件直接放在对应格式目录下，不创建模块子目录，通过时间戳+模块名区分（如 `20260903_125350_知识管理.html`）。

导出的格式可以在 `.env` 中通过 `REPORT_FORMAT` 配置。
