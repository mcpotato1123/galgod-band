# -*- coding: utf-8 -*-
"""
剧本校验器 —— 在打包前抓出坏引用

检查：
  1. 分块覆盖完整、不重叠，总数等于 nodeCount
  2. 每个节点的 bg / cg / 立绘 下标都在图片表范围内
  3. 每个跳转（j / cj / o 选项 / 章节起始）都落在 [0, nodeCount)
  4. 从入口出发全图可达（没有孤岛节点）
  5. 结局节点数、选项条件格式

用法: python validate_story.py <项目根目录>
"""
import io, os, sys, json

MAX_IMG = None


def main(proj):
    story_dir = os.path.join(proj, "src", "common", "story")
    index = json.load(io.open(os.path.join(story_dir, "index.txt"), encoding="utf-8"))

    # 图片表条目数：从生成的 assets.js 里数 IMG 数组
    assets_js = io.open(os.path.join(proj, "src", "common", "assets.js"), encoding="utf-8").read()
    img_count = assets_js.split("export const IMG = [")[1].split("]")[0].count('"/common/img/')

    errors, warns = [], []
    total = index["nodeCount"]
    chunks = index["chunks"]

    # 1. 分块
    expect = 0
    nodes = [None] * total
    for c in sorted(chunks, key=lambda x: x["start"]):
        if c["start"] != expect:
            errors.append("分块不连续: %s start=%d 期望 %d" % (c["file"], c["start"], expect))
        p = os.path.join(proj, "src", "common", c["file"].replace("/common/", "").replace("/", os.sep))
        if not os.path.isfile(p):
            errors.append("缺分块文件: " + p)
            continue
        part = json.load(io.open(p, encoding="utf-8"))
        if len(part) != c["count"]:
            errors.append("%s 实际 %d 条，索引写 %d 条" % (c["file"], len(part), c["count"]))
        for i, n in enumerate(part):
            nodes[c["start"] + i] = n
        expect = c["start"] + c["count"]
    if expect != total:
        errors.append("分块合计 %d，nodeCount %d" % (expect, total))
    if any(n is None for n in nodes):
        errors.append("存在空节点槽位")

    # 2/3. 引用与跳转
    for i, n in enumerate(nodes):
        if n is None:
            continue
        for key in ("bg", "cg"):
            if key in n and n[key] is not None:
                if not (-2 <= n[key] < img_count):
                    errors.append("#%d %s 下标越界: %s" % (i, key, n[key]))
        for ch in n.get("cs", []):
            if not (0 <= ch.get("i", -1) < img_count):
                errors.append("#%d 立绘下标越界: %s" % (i, ch))
            if ch.get("s") not in ("left", "center", "right", "c", "l", "r"):
                warns.append("#%d 立绘位置异常: %s" % (i, ch.get("s")))
        if n["t"] in ("j", "cj"):
            if not (0 <= n.get("j", -1) < total):
                errors.append("#%d 跳转越界: %s" % (i, n.get("j")))
        if n["t"] == "o":
            for o in n.get("o", []):
                if not (0 <= o.get("j", -1) < total):
                    errors.append("#%d 选项跳转越界: %s" % (i, o))
                if o.get("c") and len(o["c"]) != 3:
                    errors.append("#%d 选项条件格式错误: %s" % (i, o["c"]))

    for ch in index["chapters"]:
        if not (0 <= ch["start"] < total):
            errors.append("章节 %s 起始越界: %s" % (ch["id"], ch["start"]))

    # 4. 全图可达
    seen = set()
    stack = [index.get("entry", 0)]
    while stack:
        i = stack.pop()
        if i in seen or not (0 <= i < total):
            continue
        seen.add(i)
        n = nodes[i]
        if n is None:
            continue
        t = n["t"]
        nxt = []
        if t == "j":
            nxt = [n["j"]]
        elif t == "cj":
            nxt = [n["j"], i + 1]
        elif t == "o":
            nxt = [o["j"] for o in n.get("o", [])]
        elif t != "e":
            nxt = [i + 1]
        for k in nxt:
            if 0 <= k < total:
                stack.append(k)
    unreachable = total - len(seen)
    if unreachable > 0:
        sample = [i for i in range(total) if i not in seen][:10]
        errors.append("有 %d 个不可达节点，例如 %s" % (unreachable, sample))

    # 5. 统计
    kinds = {}
    for n in nodes:
        if n:
            kinds[n["t"]] = kinds.get(n["t"], 0) + 1

    print("节点      : %d" % total)
    print("分块      : %d" % len(chunks))
    print("章节      : %d" % len(index["chapters"]))
    print("图片表    : %d 张" % img_count)
    print("节点类型  : %s" % kinds)
    print("可达      : %d / %d" % (len(seen), total))
    print("结局节点  : %d" % kinds.get("e", 0))
    for w in warns[:10]:
        print("  警告: " + w)
    if errors:
        print("\n✖ 校验失败 %d 项:" % len(errors))
        for e in errors[:30]:
            print("   " + e)
        return 1
    print("\n✔ 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")))
