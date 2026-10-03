# -*- coding: utf-8 -*-
"""
导出「可上传 GitHub 的精简源码目录」

排除：node_modules / build / dist / .temp_* / 较大的 QA 截图 / Python 缓存
保留：源码、生成脚本、已生成好的资源（否则别人构建不出可运行的包）、预览图

用法: python tools/export_repo.py <目标目录>
"""
import io, os, shutil, sys

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 顶层直接复制的内容
FILES = [
    "README.md",
    "package.json",
    "package-lock.json",
]
# 目录（整棵复制）
TREES = [
    "src",
    "tools",
    ".vscode",
]
# 单独挑的文件
PICK = [
    "preview/ui-preview.png",     # README 里引用的界面预览；cg-check.png 是过程稿，不传
]
# 明确排除
SKIP_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db"}
SKIP_EXT = {".pyc", ".pyo"}

GITIGNORE = """# deps & build output
node_modules/
dist/
build/
.temp_*/
sign/
*.rpk

# python
__pycache__/
*.pyc
*.pyo

# editor / os
.DS_Store
Thumbs.db
"""


def copytree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in SKIP_NAMES or os.path.splitext(name)[1] in SKIP_EXT:
            continue
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(s):
            copytree(s, d)
        else:
            shutil.copy2(s, d)


def main(dst):
    if os.path.exists(dst):
        sys.exit("目标目录已存在，先删掉再跑: " + dst)
    os.makedirs(dst)

    for f in FILES:
        s = os.path.join(SRC_ROOT, f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dst, f))
        else:
            print("  !! 缺少 " + f)

    for t in TREES:
        s = os.path.join(SRC_ROOT, t)
        if os.path.isdir(s):
            copytree(s, os.path.join(dst, t))
        else:
            print("  !! 缺少目录 " + t)

    for p in PICK:
        s = os.path.join(SRC_ROOT, p.replace("/", os.sep))
        d = os.path.join(dst, p.replace("/", os.sep))
        if os.path.isfile(s):
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)

    with io.open(os.path.join(dst, ".gitignore"), "w",
                 encoding="utf-8", newline="\n") as f:
        f.write(GITIGNORE)

    # 汇总
    total = 0
    count = 0
    per = {}
    for root, dirs, files in os.walk(dst):
        dirs[:] = [d for d in dirs if d not in SKIP_NAMES]
        for n in files:
            p = os.path.join(root, n)
            sz = os.path.getsize(p)
            total += sz
            count += 1
            top = os.path.relpath(p, dst).split(os.sep)[0]
            a = per.setdefault(top, [0, 0])
            a[0] += 1
            a[1] += sz

    print("导出到: " + dst)
    print("文件 %d 个，合计 %.2f MB\n" % (count, total / 1048576.0))
    for k in sorted(per, key=lambda x: -per[x][1]):
        print("  %-16s %4d 个  %7.2f MB" % (k, per[k][0], per[k][1] / 1048576.0))
    if total > 100 * 1048576:
        print("\n⚠ 超过 100 MB，GitHub 会警告")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SRC_ROOT, "..", "galgod-band")
    sys.exit(main(os.path.abspath(target)))
