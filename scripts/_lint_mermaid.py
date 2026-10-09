"""Mermaid 代码块静态校验：配平 / 标签完整性 / 孤立节点。

用法：python scripts/_lint_mermaid.py <文件或目录> [...]
只做文档内 mermaid 块的浅层静态检查，不替代 mermaid 渲染器。
"""
import io
import os
import re
import sys

BLOCK = re.compile(r"```mermaid\n(.*?)\n```", re.S)
DECL = re.compile(r"([A-Za-z]\w*)\s*(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})")
SUB = re.compile(r"^\s*subgraph\s+([A-Za-z]\w*)", re.M)
NODE = r"([A-Za-z]\w*)(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})?"
ARROW = r"(?:<-->|-->|---|-\.\->|==>)"


def check(path):
    text = io.open(path, encoding="utf-8").read()
    bad = 0
    fences = text.count("```")
    if fences % 2:
        print(f"  [FAIL] ``` 数量为奇数，代码块未闭合：{path}")
        bad += 1
    for bi, block in enumerate(BLOCK.findall(text), 1):
        for ln, line in enumerate(block.split("\n"), 1):
            if not line.strip() or line.strip().startswith("%%"):
                continue
            errs = []
            if line.count('"') % 2:
                errs.append("引号不成对")
            for op, cl in (("[", "]"), ("(", ")"), ("{", "}")):
                if line.count(op) != line.count(cl):
                    errs.append(f"{op}{cl} 不成对")
            if "<br" in line:
                errs.append("含 <br> HTML 标签，部分渲染器会原样输出")
            if "\t" in line:
                errs.append("含 Tab")
            if errs:
                bad += 1
                print(f"  [FAIL] {path} 块{bi} 第{ln}行 {errs}: {line.strip()[:60]}")
        body = re.sub(r":::[\w-]+", "", block)  # 去掉类绑定，避免把类名当节点
        declared = set(DECL.findall(body))
        subgraphs = set(SUB.findall(block))
        edges = re.findall(ARROW, body)
        used = set(re.findall(NODE + r"\s*" + ARROW, body)) | set(
            re.findall(ARROW + r"\s*(?:\|[^|]*\|\s*)?" + NODE, body)
        )
        if not used and not edges:
            bad += 1
            print(f"  [FAIL] 块{bi} 无可识别的节点与连线，不是合法 mermaid（将报错或原样显示）")
        no_label = sorted(n for n in used if n not in declared and n not in subgraphs)
        if no_label:
            print(f"  [WARN] 块{bi} 边上的节点无标签，会渲染成裸 ID：{no_label}")
        orphan = sorted(n for n in declared if n not in used and n not in subgraphs)
        if orphan:
            print(f"  [WARN] 块{bi} 存在无连线的孤立节点：{orphan}")
        print(f"  块{bi}: 节点 {len(declared)}，连线 {len(edges)}")
    return bad


def main(argv):
    targets = []
    for a in argv:
        if os.path.isdir(a):
            for root, _dirs, files in os.walk(a):
                targets += [os.path.join(root, f) for f in files if f.endswith(".md")]
        elif os.path.isfile(a):
            targets.append(a)
    total = 0
    for p in targets:
        n = BLOCK.search(io.open(p, encoding="utf-8").read() if os.path.isfile(p) else "")
        if n is None and "```mermaid" not in io.open(p, encoding="utf-8").read():
            continue
        print(f"{p}")
        total += check(p)
    print("RESULT:", "PASS" if total == 0 else f"FAIL ({total} 处硬错误)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
