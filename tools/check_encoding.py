# -*- coding: utf-8 -*-
"""
上传前自检

1. 逐个文本文件按 UTF-8 严格解码，抓出编码坏掉的文件
   （中文内容一旦被按 GBK 读写就会静默损坏，GitHub 上看到的就是乱码）
2. 检查有没有混进不该上传的东西（node_modules / dist / rpk / 大文件）
3. 检查 README 里引用的本地图片是否存在

用法: python tools/check_encoding.py <要检查的目录>
"""
import io, os, sys

# 输出里带 ✔/✖，Windows 控制台默认是 GBK，直接 print 会抛 UnicodeEncodeError 把脚本打断
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TEXT_EXT = {".md", ".json", ".js", ".ux", ".py", ".txt", ".css", ".html", ".yml", ".yaml"}
TEXT_NAME = {".gitignore", ".npmrc", "LICENSE"}
BAD_DIRS = {"node_modules", "build", "dist", "__pycache__", ".git"}
BIG = 5 * 1024 * 1024


def main(root):
    bad_enc, bad_files, big = [], [], []
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in BAD_DIRS and not d.startswith(".temp_")]
        for name in filenames:
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root)
            ext = os.path.splitext(name)[1].lower()
            size = os.path.getsize(p)
            if size > BIG:
                big.append((rel, size))
            if ext in TEXT_EXT or name in TEXT_NAME:
                n += 1
                try:
                    with io.open(p, "rb") as f:
                        raw = f.read()
                    raw.decode("utf-8")
                except UnicodeDecodeError as e:
                    bad_enc.append((rel, str(e)))
            elif ext in (".rpk", ".zip", ".pem"):
                bad_files.append(rel)

    print("检查文本文件 %d 个" % n)
    if bad_enc:
        print("\n✖ 不是合法 UTF-8 的文本文件 %d 个:" % len(bad_enc))
        for rel, err in bad_enc[:20]:
            print("   %s\n     %s" % (rel, err))
    else:
        print("✔ 所有文本文件都是合法 UTF-8")

    if bad_files:
        print("\n⚠ 混进了不该上传的文件: %s" % ", ".join(bad_files))
    if big:
        print("\n⚠ 超过 5MB 的文件:")
        for rel, size in big:
            print("   %-50s %6.2f MB" % (rel, size / 1048576.0))

    # README 引用的本地图片
    readme = os.path.join(root, "README.md")
    if os.path.isfile(readme):
        import re
        txt = io.open(readme, encoding="utf-8").read()
        miss = []
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", txt):
            t = m.group(1)
            if t.startswith("http"):
                continue
            if not os.path.isfile(os.path.join(root, t.replace("/", os.sep))):
                miss.append(t)
        if miss:
            print("\n✖ README 引用了不存在的图片: %s" % ", ".join(miss))
        else:
            print("✔ README 引用的本地图片都在")

    return 1 if (bad_enc or bad_files) else 0


if __name__ == "__main__":
    sys.exit(main(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")))
