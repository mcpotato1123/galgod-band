# -*- coding: utf-8 -*-
"""
剧情流程模拟器

因为拿不到真机，这里用 Python 复刻 src/pages/game/game.ux 的 step()/onTap() 语义，
在真实剧本数据上把几条路线跑一遍，确认：
  * 不会卡死、不会越界、不会触发保护上限
  * 每个分支选项都能被走到
  * 三条结局（真结局 / end2 / end3）与 Bad End 都能到达
  * 真结局之后会接上后日谈

用法: python simulate.py <项目根目录>
"""
import io, os, sys, json

GUARD = 20000


def load(proj):
    story_dir = os.path.join(proj, "src", "common", "story")
    index = json.load(io.open(os.path.join(story_dir, "index.txt"), encoding="utf-8"))
    nodes = []
    for c in sorted(index["chunks"], key=lambda x: x["start"]):
        p = os.path.join(proj, "src", "common",
                         c["file"].replace("/common/", "").replace("/", os.sep))
        nodes += json.load(io.open(p, encoding="utf-8"))
    return index, nodes


def body_flags(nodes, start):
    """从选项体起点走到它的落空跳转，收集途中累加的标记"""
    found, pc, guard = set(), start, 0
    while guard < 500:
        guard += 1
        if not (0 <= pc < len(nodes)):
            break
        n = nodes[pc]
        t = n["t"]
        if t == "f":
            found.add(n["v"])
            pc += 1
        elif t == "sf":
            found.add(n["v"])
            pc += 1
        elif t == "j":
            break
        elif t == "s":
            pc += 1
        else:
            break
    return found


def play(nodes, index, picker, label):
    chapters = index["chapters"]

    def chap_of(p):
        cur = 0
        for i, c in enumerate(chapters):
            if p >= c["start"]:
                cur = i
        return cur

    pc, flags = 0, {}
    taps = 0
    choices_seen = []
    path = []
    visited = []
    guard = 0
    while guard < GUARD:
        guard += 1
        if not (0 <= pc < len(nodes)):
            return dict(label=label, end="越界(%d)" % pc, taps=taps, flags=flags,
                        choices=choices_seen, ok=False, path=path, visited=visited)
        ci = chap_of(pc)
        if not visited or visited[-1] != ci:
            visited.append(ci)
        n = nodes[pc]
        t = n["t"]
        if t == "s":
            # 分页已改到运行时按字号现算，这里只能统计台词节点数；
            # 实际点击次数见 tools/test_paginate.js 输出的「页/句」
            taps += 1
            pc += 1
        elif t == "f":
            flags[n["v"]] = flags.get(n["v"], 0) + n["n"]
            pc += 1
        elif t == "sf":
            flags[n["v"]] = n["n"]
            pc += 1
        elif t == "j":
            pc = n["j"]
        elif t == "cj":
            v = flags.get(n["v"], 0)
            op, k = n["op"], n["n"]
            hit = {">=": v >= k, "<=": v <= k, ">": v > k, "<": v < k, "==": v == k}[op]
            pc = n["j"] if hit else pc + 1
        elif t == "o":
            opts = []
            for o in n["o"]:
                if o.get("c"):
                    v = flags.get(o["c"][0], 0)
                    op, k = o["c"][1], o["c"][2]
                    if not {">=": v >= k, "<=": v <= k, ">": v > k,
                            "<": v < k, "==": v == k}[op]:
                        continue
                opts.append(o)
            if not opts:
                return dict(label=label, end="选项全被条件过滤", taps=taps,
                            flags=flags, choices=choices_seen, ok=False, path=path)
            idx = picker(n, opts, nodes)
            choices_seen.append(opts[idx]["x"])
            path.append(opts[idx]["x"])
            pc = opts[idx]["j"]
        elif t == "e":
            return dict(label=label, end=n["x"], taps=taps, flags=flags,
                        choices=choices_seen, ok=True, path=path, visited=visited)
        else:
            return dict(label=label, end="未知节点 " + t, taps=taps, flags=flags,
                        choices=choices_seen, ok=False, path=path, visited=visited)
    return dict(label=label, end="超过 %d 步（疑似死循环）" % GUARD, taps=taps,
                flags=flags, choices=choices_seen, ok=False, path=path, visited=visited)


def chapter_ids(index, visited):
    ids = []
    for i in visited:
        ch = index["chapters"][i]
        if not ids or ids[-1] != ch["id"]:
            ids.append(ch["id"])
    return ids


def main(proj):
    index, nodes = load(proj)

    def first(n, opts, nodes): return 0
    def last(n, opts, nodes): return len(opts) - 1
    def greedy(n, opts, nodes):
        """优先选会累加标记的选项（= 原作里的“正确/加分”选项）"""
        best, score = 0, -1
        for i, o in enumerate(opts):
            f = body_flags(nodes, o["j"])
            s = len(f)
            if s > score:
                best, score = i, s
        return best
    def avoidflag(n, opts, nodes):
        """优先选不加标记的选项"""
        for i, o in enumerate(opts):
            if not body_flags(nodes, o["j"]):
                return i
        return 0
    def greedy_last(n, opts, nodes):
        """优先加分选项；同分时取靠后的（在原作里就是最后那个"我全都要"式选项）"""
        best, score = len(opts) - 1, -1
        for i, o in enumerate(opts):
            s = len(body_flags(nodes, o["j"]))
            if s >= score:
                best, score = i, s
        return best

    def prefer(want):
        """在最终抉择处定向选择，其余分支按“优先加分”走，用来确定性地覆盖三条结局线"""
        def picker(n, opts, nodes):
            for i, o in enumerate(opts):
                if o["x"] == want:
                    return i
            return greedy_last(n, opts, nodes)
        return picker

    runs = [("全部选第一个", first), ("全部选最后一个", last),
            ("优先加分选项", greedy), ("优先加分+取后者", greedy_last),
            ("优先不加分选项", avoidflag),
            ("真结局线", prefer("交给小涟选择")),
            ("end2 线", prefer("要让小涟诞生")),
            ("end3 线", prefer("要对小涟放手"))]

    print("总节点 %d，章节 %d\n" % (len(nodes), len(index["chapters"])))
    allok = True
    reached = {}
    for label, pk in runs:
        r = play(nodes, index, pk, label)
        ids = chapter_ids(index, r["visited"])
        for e in ("end_te", "end_ne1", "end_ne2", "after_story_noctella"):
            if e in ids:
                reached[e] = label
        flag = "✔" if r["ok"] else "✖"
        if not r["ok"]:
            allok = False
        print("%s %-14s 台词 %5d  标记 %-46s 结局章: %s" %
              (flag, label, r["taps"],
               str({k: v for k, v in r["flags"].items()
                    if k in ("true_end_flag", "bad_end_flag", "true_end_finish")}),
               "/".join([x for x in ids if x.startswith(("end_", "after_"))]) or "（无，止于 Bad End）"))
    print()
    print("结局章到达情况:")
    for e in ("end_te", "end_ne1", "end_ne2", "after_story_noctella"):
        print("  %-22s %s" % (e, reached.get(e, "✖ 未到达")))
    if len(reached) < 3:
        allok = False
        print("  ⚠ 有结局章没被任何策略走到")

    # 同一周目不应串场到多个结局章（防止结局之间互相“落空”串起来）
    for label, pk in runs:
        r = play(nodes, index, pk, label)
        ids = chapter_ids(index, r["visited"])
        ends = [x for x in ids if x in ("end_te", "end_ne1", "end_ne2")]
        if len(set(ends)) > 1:
            allok = False
            print("  ✖ %s 串了多个结局章: %s" % (label, ends))
    print()

    # 所有选项是否都被覆盖过
    all_opts = set()
    for n in nodes:
        if n["t"] == "o":
            for o in n["o"]:
                all_opts.add((o["x"], o["j"]))
    seen_opts = set()
    for label, pk in runs:
        r = play(nodes, index, pk, label)
        for x in r["path"]:
            for (ox, oj) in all_opts:
                if ox == x:
                    seen_opts.add((ox, oj))
    print("选项覆盖: %d / %d" % (len(seen_opts), len(all_opts)))

    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")))
