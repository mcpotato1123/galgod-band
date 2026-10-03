# -*- coding: utf-8 -*-
"""
GalGod 手环版 —— 剧本编译器

把 Ren'Py 的 scenes/*.rpy 编译成 Vela 快应用运行时吃的分块剧本：
    src/common/story/index.txt        (JSON 内容，.txt 扩展名避免被打包器当模块处理)
    src/common/story/chunk-000.txt    (每块 CHUNK_SIZE 个节点)

节点格式（键名尽量短，减小 rpk 体积）：
    {t:"s",  n:"林曦", p:[页1, 页2], bg?, cs?, cg?}    一句台词；p 为预分页文本，页内 \\n 分行
    {t:"o",  o:[{x:"选项", j:目标下标, c?:[flag,op,n]}], bg?, cs?, cg?}   分支
    {t:"j",  j:下标}                                   跳转
    {t:"cj", v:flag, op:">=", n:7, j:下标}              条件跳转（条件成立才跳）
    {t:"f",  v:flag, n:1}                              标记累加
    {t:"e",  x:"结局标题", bg?, cs?, cg?}               结局（回标题）

用法:
    python gen_story.py <renpy_raw_dir> <项目根目录>
"""
import io, os, re, sys, json

CHUNK_SIZE = 128

# 画布 336x480（designWidth 336 → 1px = 1 物理像素）
# 正文区宽 312px、字号 20px，312/20 = 15.6 → 保守取 14 字/行
CHARS_PER_LINE = 14
LINES_PER_PAGE = 5

SPEAKER_NAMES = {
    "cz": "陈舟", "me": "我", "zhengke": "政客",
    "lx": "林曦", "jwq": "江晚晴", "xl": "小涟", "xl_l": "小涟",
    "noctella": "诺提拉", "nt": "诺提拉",
    "xy_a": "校友A", "xy_b": "校友B", "xy_c": "校友C", "ty_a": "健壮男生",
    "reporter_a": "记者A", "reporter_b": "记者B", "reporter_c": "记者C",
    "staff": "工作人员", "man_parent": "成熟男士", "woman_parent": "贵气妇人",
    "banzhuren": "班主任", "n": "", "centered": "", "vcentered": "", "narrator": "",
}

KEYWORDS = {
    "play", "stop", "queue", "voice", "window", "scene", "show", "hide", "with",
    "call", "jump", "if", "elif", "else", "while", "menu", "python", "init",
    "define", "default", "return", "label", "nvl", "pause", "extend", "transform",
    "screen", "style", "translate", "pass", "at", "image", "use", "timer", "key",
    "on", "add", "bar", "vbox", "hbox", "grid", "fixed", "frame", "vpgrid",
    "textbutton", "text", "side", "viewport", "null", "for", "in", "del", "class",
    "import", "from", "try", "except", "finally", "raise", "global", "assert",
    "print", "renpy", "layer", "camera", "predict", "solid", "input", "set",
    "has", "as", "and", "or", "not", "block", "xpos", "xalign",
}

MAIN = ["1_1", "1_2", "1_3", "1_4", "2_1", "interlude1", "interlude2",
        "2_2", "2_3", "2_4", "3_1", "3_2", "3_3", "3_4"]

CHAPTER_TITLES = {
    "1_1": "第一幕 · 月幕", "1_2": "第一幕 · 教室", "1_3": "第一幕 · 夜谈",
    "1_4": "第一幕 · 霁光", "2_1": "第二幕 · 校园", "interlude1": "间章 · 小涟的日常",
    "interlude2": "间章 · 回到学校", "2_2": "第二幕 · 茶餐厅", "2_3": "第二幕 · 街道",
    "2_4": "第二幕 · 雨夜", "3_1": "第三幕 · 抉择", "3_2": "第三幕 · 河畔",
    "3_3": "第三幕 · 心意", "3_4": "第三幕 · 天选试", "interlude-interview": "间章 · 面试",
    "end_te": "真结局 · 这片月幕", "end_ne1": "结局 · 二人的世界",
    "end_ne2": "结局 · 回归日常", "after_story_noctella": "后日谈 · 诺提拉",
}

LABEL_FILE = {
    "scene_1_1": "1_1", "scene_1_2": "1_2", "scene_1_3": "1_3", "scene_1_4": "1_4",
    "scene_2_1": "2_1", "scene_2_2": "2_2", "scene_2_3": "2_3", "scene_2_4": "2_4",
    "scene_3_1": "3_1", "scene_3_2": "3_2", "scene_3_3": "3_3", "scene_3_4": "3_4",
    "interlude1": "interlude1", "interlude2": "interlude2",
    "interlude_interview": "interlude-interview",
    "end1": "end_te", "end2": "end_ne1", "end3": "end_ne2",
    "after_story_noctella": "after_story_noctella",
}

# 结局章节不在「章节选择」里露出——结局应该是玩出来的，不该能直接跳
CHAPTER_HIDE = {"end_te", "end_ne1", "end_ne2"}
# 后日谈是真结局的奖励，通关前不出现
CHAPTER_NEED_CLEAR = {"after_story_noctella"}

RE_TAG = re.compile(r"\{[^{}]*\}")
RE_SPACE = re.compile(r"\{space=\d+\}")
RE_CALLTEXT = re.compile(r'centered_left_text\(\s*"((?:[^"\\]|\\.)*)"')
RE_BLOCKKW = re.compile(r"^(transform|screen|style|python|init|image|layeredimage|"
                        r"translate|define|default)\b.*:\s*$")

WARNINGS = []


# ---------------------------------------------------------------- 文本工具

def unescape(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "'": "'",
                        "\\": "\\", " ": " ", "{": "{", "[": "["}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def clean_text(s):
    t = unescape(s)
    t = t.replace("{{", "\x01").replace("[[", "\x02")
    t = RE_SPACE.sub(" ", t)
    t = RE_TAG.sub("", t)
    t = t.replace("\x01", "{").replace("\x02", "[")
    return t.strip()


def strip_comment(s):
    out, i, in_str = [], 0, False
    while i < len(s):
        c = s[i]
        if in_str:
            if c == "\\" and i + 1 < len(s):
                out.append(s[i:i + 2]); i += 2; continue
            if c == '"':
                in_str = False
            out.append(c)
        else:
            if c == '"':
                in_str = True; out.append(c)
            elif c == "#":
                break
            else:
                out.append(c)
        i += 1
    return "".join(out)


def parse_quoted(s, i):
    assert s[i] == '"'
    j, buf = i + 1, []
    while j < len(s):
        c = s[j]
        if c == "\\" and j + 1 < len(s):
            buf.append(s[j:j + 2]); j += 2; continue
        if c == '"':
            return "".join(buf), j + 1
        buf.append(c); j += 1
    return "".join(buf), j


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def paginate(text):
    """按 14 字/行、5 行/页预分页，保证运行时不需要滚动或截断。"""
    if not text:
        return [""]
    lines = []
    for raw in text.split("\n"):
        if raw == "":
            lines.append("")
            continue
        while len(raw) > CHARS_PER_LINE:
            cut = CHARS_PER_LINE
            # 尽量断在标点之后，避免标点跑到下一行行首
            for k in range(CHARS_PER_LINE, max(2, CHARS_PER_LINE - 8), -1):
                if raw[k - 1] in "，。！？；：、）」』…—":
                    cut = k
                    break
            lines.append(raw[:cut])
            raw = raw[cut:]
        lines.append(raw)
    pages = []
    for i in range(0, len(lines), LINES_PER_PAGE):
        pages.append("\n".join(lines[i:i + LINES_PER_PAGE]))
    return pages or [""]


def parse_cond(expr):
    if not expr:
        return None
    m = re.match(r"^\s*([A-Za-z_]\w*)\s*(>=|<=|==|>|<)\s*(\d+)\s*$", expr)
    if m:
        return [m.group(1), m.group(2), int(m.group(3))]
    return None


# ---------------------------------------------------------------- 单行解析

def parse_one(s, ln):
    """解析一行，返回 (item, warnings)"""
    w = []

    if s.startswith("$"):
        if "full_restart" in s:
            return ("ending", "Bad End · 未能触碰的世界"), w
        m = re.match(r"^\$\s*([A-Za-z_]\w*)\s*\+=\s*(\d+)", s)
        if m:
            return ("flag", m.group(1), int(m.group(2))), w
        # $ flag = True / False / 数字（例如 true_end_finish = True）
        m = re.match(r"^\$\s*([A-Za-z_]\w*)\s*=\s*(True|False|\d+)\s*$", s)
        if m:
            v = m.group(2)
            n = 1 if v == "True" else (0 if v == "False" else int(v))
            return ("setflag", m.group(1), n), w
        m = re.match(r'^\$\s*([A-Za-z_]\w*)\.show\(\s*"([^"]*)"(.*)\)\s*$', s)
        if m:
            mp = re.search(r"pos\s*=\s*([A-Za-z_]+)", m.group(3))
            return ("show", m.group(1), m.group(2), mp.group(1) if mp else None), w
        m = re.match(r"^\$\s*([A-Za-z_]\w*)\.hide\(", s)
        if m:
            return ("hide", m.group(1)), w
        return None, w

    if s.startswith("hide "):
        m = re.match(r"^hide\s+(?:cg|sdcg)\b", s)
        if m:
            return ("cg", ""), w
        m = re.match(r"^hide\s+([A-Za-z_]\w*)", s)
        if m and (m.group(1) in SPRITE_CODES):
            return ("hide", m.group(1)), w
        return None, w

    if s.startswith("scene ") or s.startswith("show "):
        m = re.match(r"^(?:scene|show)\s+bg\s+(\w+)", s)
        if m:
            return ("bg", m.group(1)), w
        m = re.match(r"^scene\s+(black|white)\b", s)
        if m:
            return ("bg", m.group(1)), w
        m = re.match(r"^(?:scene|show)\s+cg\s+(\w+)", s)
        if m:
            return ("cg", "cg_" + m.group(1)), w
        m = re.match(r"^(?:scene|show)\s+sdcg\s+(\w+)", s)
        if m:
            return ("cg", "sd_" + m.group(1)), w
        if s.startswith("show cinematic_black_overlay"):
            return ("bg", "black"), w
        # show layer master at memory_filter / reset_filter —— 回忆滤镜
        m = re.match(r"^show\s+layer\s+\w+\s+at\s+(\w+)", s)
        if m:
            return ("tint", "memory" if m.group(1) == "memory_filter" else ""), w
        # 雨层特效：手环版不做（属演出增强，不影响剧情）
        if re.match(r"^show\s+(rainback|rainfront)\b", s):
            return None, w
        # show <code> [expr] [at ...]
        m = re.match(r"^show\s+([A-Za-z_]\w*)(?:\s+([^\s:#]+))?", s)
        if m:
            code, expr = m.group(1), m.group(2)
            if code in SPRITE_CODES:
                table = SPRITE_EXPR.get(code, {})
                if expr is None or expr not in table:
                    expr = next(iter(table), None)
                if expr:
                    return ("show", code, expr, None), w
                return None, w
            if code in BG_TAGS:
                return ("bg", code), w
        return None, w

    if s.startswith('"'):
        text, j = parse_quoted(s, 0)
        rest = s[j:].strip()
        while rest.startswith('"'):
            more, j2 = parse_quoted(rest, 0)
            text += more
            rest = rest[j2:].strip()
        if rest and not rest.startswith(("with", "nointeract", "id")):
            w.append("旁白尾部: " + s)
        return ("say", "", clean_text(text)), w

    m = RE_CALLTEXT.search(s)
    if m:
        return ("say", "", clean_text(m.group(1))), w

    m = re.match(r"^([A-Za-z_]\w*)\s+", s)
    if m and m.group(1) not in KEYWORDS:
        code = m.group(1)
        pos = m.end()
        if pos < len(s) and s[pos] == '"':
            text, j = parse_quoted(s, pos)
            rest = s[j:].strip()
            while rest.startswith('"'):
                more, j2 = parse_quoted(rest, 0)
                text += more
                rest = rest[j2:].strip()
            name = SPEAKER_NAMES.get(code)
            if name is None:
                w.append("未知角色码: " + s)
                name = code
            return ("say", name, clean_text(text)), w

    m = re.match(r"^jump\s+([A-Za-z_]\w*)", s)
    if m:
        return ("jump", m.group(1)), w
    m = re.match(r"^call\s+([A-Za-z_]\w*)", s)
    if m and m.group(1) != "screen":
        return ("call", m.group(1)), w
    if re.match(r"^return\b", s):
        return ("return",), w

    if re.match(r"^(play|stop|queue|voice|window|with|pause|nvl|camera|pass|"
                r"elif|else|define|default|init|image|transform|screen|style|"
                r"translate|layeredimage|at)\b", s):
        return None, w

    w.append("未识别: " + s)
    return None, w


# ---------------------------------------------------------------- 缩进块解析

def skip_block(lines, i, min_indent):
    """把缩进 >= min_indent 的整块行直接跳过（不解析），返回下一行下标"""
    while i < len(lines):
        raw = strip_comment(lines[i])
        s = raw.strip()
        if not s:
            i += 1
            continue
        if indent_of(raw) < min_indent:
            break
        i += 1
    return i


def parse_block(lines, i, min_indent):
    """解析缩进 >= min_indent 的语句块，返回 (items, next_i)"""
    items = []
    while i < len(lines):
        raw = strip_comment(lines[i])
        s = raw.strip()
        if not s:
            i += 1
            continue
        ind = indent_of(raw)
        if ind < min_indent:
            break

        if re.match(r"^menu\s*:", s):
            menu_item, i = parse_menu(lines, i + 1, ind)
            if menu_item:
                items.append(menu_item)
            continue

        m = re.match(r"^if\s+(.+?)\s*:\s*$", s)
        if m:
            cond = parse_cond(m.group(1))
            if cond is None:
                WARNINGS.append("无法解析的 if: " + s)
            body, i = parse_block(lines, i + 1, ind + 1)
            else_body = []
            while i < len(lines):
                raw2 = strip_comment(lines[i])
                s2 = raw2.strip()
                if not s2:
                    i += 1
                    continue
                if indent_of(raw2) != ind:
                    break
                if re.match(r"^else\s*:\s*$", s2):
                    eb, i = parse_block(lines, i + 1, ind + 1)
                    else_body += eb
                    continue
                mel = re.match(r"^elif\s+(.+?)\s*:\s*$", s2)
                if mel:
                    c2 = parse_cond(mel.group(1))
                    b2, i = parse_block(lines, i + 1, ind + 1)
                    else_body.append(("if", c2, b2, []))
                    continue
                break
            items.append(("if", cond, body, else_body))
            continue

        if RE_BLOCKKW.match(s):
            i = skip_block(lines, i + 1, ind + 1)
            continue

        it, w = parse_one(s, i + 1)
        WARNINGS.extend(w)
        if it:
            items.append(it)
        i += 1
        # 叶子语句后面若挂着更深的缩进块（ATL / with 参数），整块跳过
        j = i
        while j < len(lines) and not strip_comment(lines[j]).strip():
            j += 1
        if j < len(lines) and indent_of(strip_comment(lines[j])) > ind:
            i = skip_block(lines, i, ind + 1)
    return items, i


def parse_menu(lines, i, menu_indent):
    """解析 menu 块，返回 (("menu", options) | None, next_i)；提问句作为 say 前置返回"""
    options = []
    captions = []
    while i < len(lines):
        raw = strip_comment(lines[i])
        s = raw.strip()
        if not s:
            i += 1
            continue
        ind = indent_of(raw)
        if ind <= menu_indent:
            break
        mo = re.match(r'^"((?:[^"\\]|\\.)*)"\s*(?:if\s+([^:]*?))?\s*:\s*$', s)
        if mo:
            cond = parse_cond(mo.group(2)) if mo.group(2) else None
            body, i = parse_block(lines, i + 1, ind + 1)
            options.append({"x": clean_text(mo.group(1)), "c": cond, "body": body})
            continue
        mc = re.match(r'^"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"\s*$', s)
        if mc:
            captions.append(("say", clean_text(mc.group(1)), clean_text(mc.group(2))))
            i += 1
            continue
        WARNINGS.append("menu 内未识别: " + s)
        i += 1
    if not options:
        return None, i
    return ("menu", options, captions), i


def parse_file(path):
    lines = io.open(path, encoding="utf-8").read().splitlines()
    items = []
    i = 0
    while i < len(lines):
        raw = strip_comment(lines[i])
        s = raw.strip()
        if not s:
            i += 1
            continue
        ind = indent_of(raw)
        m = re.match(r"^label\s+([A-Za-z_]\w*)\s*:", s)
        if m:
            items.append(("label", m.group(1)))
            body, i = parse_block(lines, i + 1, ind + 1)
            items += body
            continue
        if RE_BLOCKKW.match(s):
            i = skip_block(lines, i + 1, ind + 1)
            continue
        it, w = parse_one(s, i + 1)
        WARNINGS.extend(w)
        if it:
            items.append(it)
        i += 1
    return items


# ---------------------------------------------------------------- 编译为节点

class Compiler(object):
    def __init__(self):
        self.out = []
        self.patches = []
        self.label_index = {}
        self.chapters = []
        self.pending = {}

    def emit(self, node, visible=False):
        if visible and self.pending:
            node.update(self.pending)
            self.pending = {}
        self.out.append(node)
        return len(self.out) - 1

    def jmp(self, target_label):
        idx = self.emit({"t": "j", "j": -1})
        self.patches.append((idx, target_label))

    def chapter_rec(self, key, start):
        rec = {"id": key, "title": CHAPTER_TITLES.get(key, key), "start": start}
        if key in CHAPTER_HIDE:
            rec["hide"] = 1
        if key in CHAPTER_NEED_CLEAR:
            rec["need"] = 1
        return rec

    def set_bg(self, key):
        if key in BG_SOLID:
            self.pending["bg"] = BG_SOLID[key]
        else:
            idx = IMG_INDEX.get(("bg", key))
            if idx is None:
                WARNINGS.append("未知背景: " + key)
                return
            self.pending["bg"] = idx

    def set_cg(self, key):
        if not key:
            self.pending["cg"] = -1
            return
        idx = IMG_INDEX.get(("cg", key))
        if idx is None:
            WARNINGS.append("未知 CG: " + key)
            return
        self.pending["cg"] = idx

    def show(self, code, expr, pos):
        idx = IMG_INDEX.get(("sp", "%s|%s" % (code, expr)))
        if idx is None:
            WARNINGS.append("未知立绘: %s|%s" % (code, expr))
            return
        cs = self.pending.setdefault("cs", [])
        for c in cs:
            if c["k"] == code:
                c["i"] = idx
                if pos:
                    c["s"] = pos
                return
        cs.append({"k": code, "i": idx, "s": pos or "c"})

    def hide(self, code):
        cs = self.pending.setdefault("cs", [])
        self.pending["cs"] = [c for c in cs if c["k"] != code]

    def compile_items(self, items, ret_target=None):
        for it in items:
            kind = it[0]
            if kind == "label":
                self.label_index[it[1]] = len(self.out)
            elif kind == "bg":
                self.set_bg(it[1])
            elif kind == "cg":
                self.set_cg(it[1])
            elif kind == "show":
                self.show(it[1], it[2], it[3])
            elif kind == "hide":
                self.hide(it[1])
            elif kind == "tint":
                self.pending["tint"] = it[1]
            elif kind == "say":
                if it[2]:
                    self.emit({"t": "s", "n": it[1], "p": paginate(it[2])}, visible=True)
            elif kind == "flag":
                self.emit({"t": "f", "v": it[1], "n": it[2]})
            elif kind == "setflag":
                self.emit({"t": "sf", "v": it[1], "n": it[2]})
            elif kind == "ending":
                self.emit({"t": "e", "x": it[1]}, visible=True)
            elif kind == "jump":
                self.jmp(it[1])
            elif kind == "call":
                self.compile_call(it[1])
            elif kind == "return":
                if ret_target == "fall":
                    pass              # 主序列里的 return 直接落进下一章
                elif isinstance(ret_target, dict):
                    # 内联 call：先把跳转占位发出去，等被调块编译完再回填目标
                    ret_target["call"].append(self.emit({"t": "j", "j": -1}))
                elif ret_target is not None:
                    self.emit({"t": "j", "j": ret_target})
                else:
                    self.jmp("__end__")
            elif kind == "if":
                self.compile_if(it, ret_target)
            elif kind == "menu":
                self.compile_menu(it, ret_target)
            else:
                raise RuntimeError("unknown item " + str(kind))

    def compile_call(self, target):
        """把被调章节原地内联：落到它的第一句，它内部的 return 跳回调用点之后"""
        target_file = LABEL_FILE.get(target)
        if not target_file or target_file not in FILE_ITEMS:
            WARNINGS.append("未知 call 目标: " + target)
            return
        slot = {"call": []}
        self.compile_items(FILE_ITEMS[target_file], ret_target=slot)
        after = len(self.out)
        for idx in slot["call"]:
            self.out[idx]["j"] = after

    def compile_if(self, item, ret_target=None):
        _, cond, body, else_body = item
        v, op, n = cond if cond else ("__never__", "==", 0)
        cj = self.emit({"t": "cj", "v": v, "op": op, "n": n, "j": -1})
        self.compile_items(else_body, ret_target)
        skip_idx = self.emit({"t": "j", "j": -1})   # 无条件跳过 then 块
        then_start = len(self.out)
        self.out[cj]["j"] = then_start
        self.compile_items(body, ret_target)
        after = len(self.out)
        self.patches.append((skip_idx, ("abs", after)))

    def compile_menu(self, item, ret_target=None):
        _, options, captions = item
        for cap in captions:
            if cap[2]:
                self.emit({"t": "s", "n": cap[1], "p": paginate(cap[2])}, visible=True)
        menu_idx = self.emit({"t": "o", "o": []}, visible=True)
        after_label = "__menu_after_%d__" % menu_idx
        for opt in options:
            start = len(self.out)
            self.out[menu_idx]["o"].append({"x": opt["x"], "j": start, "c": opt["c"]})
            self.compile_items(opt["body"], ret_target)
            # 选项体末尾若是无条件跳转，就不用再补落空跳转（否则是死代码）
            last = self.out[-1] if len(self.out) > start else None
            if not last or last.get("t") != "j":
                self.jmp(after_label)
        self.label_index[after_label] = len(self.out)


FILE_ITEMS = {}

# CG 鉴赏分组：(显示名, 解锁所需图, 该组包含的图)
# 与原作 screens/gallery.rpy 的 9 个 g.button 一一对应
GALLERY = [
    ("政客",              "sd_001", ["sd_001", "sd_002"]),
    ("林曦 · 教室",       "sd_004", ["sd_004", "sd_005", "sd_006", "sd_007", "sd_008",
                                     "sd_009", "sd_010", "sd_011", "sd_012", "sd_013"]),
    ("小涟",              "cg_001", ["cg_001", "cg_002", "cg_003"]),
    ("球场",              "sd_019", ["sd_019"]),
    ("林曦 · 冰激凌",     "sd_014", ["sd_014", "sd_015", "sd_016", "sd_017", "sd_018"]),
    ("林曦 · 推倒",       "cg_004", ["cg_004", "cg_005"]),
    ("江晚晴 · 雨",       "cg_006", ["cg_006"]),
    ("林曦 · 告白",       "cg_007", ["cg_007", "cg_008", "cg_009", "cg_010",
                                     "cg_011", "cg_012", "cg_013"]),
    ("诺提拉",            "cg_noctella_descend", ["cg_noctella_descend"]),
]
BG_TAGS = set()
SPRITE_EXPR = {}
SPRITE_CODES = set()
IMG_LIST = []          # [{kind,key,src,out}]
IMG_INDEX = {}         # (kind,key) -> idx
BG_SOLID = {}          # key -> -1(黑) / -2(白)


def load_asset_maps(raw_dir):
    """先读资源定义，供解析阶段判断 show/hide 的目标类型；并建立图片索引表"""
    global BG_TAGS, SPRITE_EXPR, SPRITE_CODES, IMG_LIST, IMG_INDEX, BG_SOLID
    bgs, sprites, cgs = collect_assets(raw_dir)

    IMG_LIST, IMG_INDEX, BG_SOLID = [], {}, {}
    BG_SOLID["black"] = -1
    BG_SOLID["white"] = -2

    for key in sorted(bgs):
        src = bgs[key]
        if not src:
            continue
        out = "/common/img/b/%s.png" % key
        IMG_INDEX[("bg", key)] = len(IMG_LIST)
        IMG_LIST.append({"kind": "bg", "key": key, "src": src, "out": out})

    for key in sorted(sprites):
        code, expr = key.split("|", 1)
        out = "/common/img/s/%03d.png" % len([x for x in IMG_LIST if x["kind"] == "sp"])
        IMG_INDEX[("sp", key)] = len(IMG_LIST)
        IMG_LIST.append({"kind": "sp", "key": key, "src": sprites[key], "out": out})

    for key in sorted(cgs):
        out = "/common/img/c/%s.png" % key
        IMG_INDEX[("cg", key)] = len(IMG_LIST)
        IMG_LIST.append({"kind": "cg", "key": key, "src": cgs[key], "out": out})

    BG_TAGS = set(bgs.keys())
    SPRITE_EXPR = {}
    for k in sprites:
        code, expr = k.split("|", 1)
        SPRITE_EXPR.setdefault(code, {})[expr] = sprites[k]
    SPRITE_CODES = set(SPRITE_EXPR.keys())


def build(raw_dir, out_dir):
    load_asset_maps(raw_dir)
    scenes = os.path.join(raw_dir, "scenes")
    for key in sorted(set(LABEL_FILE.values())):
        path = os.path.join(scenes, key + ".rpy")
        if not os.path.isfile(path):
            WARNINGS.append("缺少场景文件: " + path)
            continue
        before = len(WARNINGS)
        FILE_ITEMS[key] = parse_file(path)
        for k in range(before, len(WARNINGS)):
            WARNINGS[k] = key + ": " + WARNINGS[k]

    c = Compiler()

    for key in MAIN:
        c.chapters.append(c.chapter_rec(key, len(c.out)))
        c.compile_items(FILE_ITEMS[key], ret_target="fall")

    for key in ["end_te", "end_ne1", "end_ne2"]:
        c.chapters.append(c.chapter_rec(key, len(c.out)))
        ret = c.emit({"t": "j", "j": -1})
        c.compile_items(FILE_ITEMS[key], ret_target=ret)
        c.out[ret]["j"] = len(c.out)
        # 结局收尾：通关真结局才接后日谈，否则直接进终点
        # 注意必须显式补一条跳向终点的跳转，否则条件不成立会直接落进下一个结局章
        cj = c.emit({"t": "cj", "v": "true_end_finish", "op": "==", "n": 1, "j": -1})
        c.patches.append((cj, "__after_story__"))
        c.jmp("__end__")

    c.label_index["__after_story__"] = len(c.out)
    c.chapters.append(c.chapter_rec("after_story_noctella", len(c.out)))
    c.compile_items(FILE_ITEMS["after_story_noctella"])

    c.label_index["__end__"] = len(c.out)
    c.emit({"t": "e", "x": "—— 全剧终 ——"}, visible=True)

    for idx, lbl in c.patches:
        if isinstance(lbl, tuple):
            target = lbl[1]
        else:
            target = c.label_index.get(lbl)
            if target is None:
                WARNINGS.append("未找到 label: %s" % lbl)
                target = c.label_index["__end__"]
        c.out[idx]["j"] = target

    # 章节排序

    # ---------------------------------------------------------- 写文件
    story_dir = os.path.join(out_dir, "src", "common", "story")
    os.makedirs(story_dir, exist_ok=True)
    for f in os.listdir(story_dir):
        if f.startswith("chunk-") or f == "index.txt":
            os.remove(os.path.join(story_dir, f))

    chunks = []
    for i in range(0, len(c.out), CHUNK_SIZE):
        part = c.out[i:i + CHUNK_SIZE]
        name = "chunk-%03d.txt" % (i // CHUNK_SIZE)
        with io.open(os.path.join(story_dir, name), "w",
                     encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(part, ensure_ascii=False, separators=(",", ":")))
        chunks.append({"file": "/common/story/" + name, "start": i, "count": len(part)})

    index = {
        "ver": 1, "title": "GalGod", "nodeCount": len(c.out),
        "chunkSize": CHUNK_SIZE, "entry": 0,
        "chapters": c.chapters, "chunks": chunks,
    }
    with io.open(os.path.join(story_dir, "index.txt"), "w",
                 encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    # ---------------------------------------------------------- 资源索引表
    os.makedirs(os.path.join(out_dir, "tools"), exist_ok=True)
    with io.open(os.path.join(out_dir, "tools", "assets.json"), "w",
                 encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(IMG_LIST, ensure_ascii=False, indent=1))

    # 运行时用的图片索引（数组下标 = 剧本里的资源号）
    js = ["// 由 tools/gen_story.py 自动生成，请勿手改",
          "// 图片索引表：下标即剧本节点里的资源号",
          "export const IMG = ["]
    for it in IMG_LIST:
        js.append('  "%s",' % it["out"])
    js.append("]")
    js.append("")
    js.append("// 背景代号 -> 图片下标（-1 纯黑 / -2 纯白）")
    js.append("export const BG = {")
    for key, idx in sorted(BG_SOLID.items()):
        js.append('  %s: %d,' % (json.dumps(key), idx))
    for (kind, key), idx in sorted(IMG_INDEX.items()):
        if kind == "bg":
            js.append('  %s: %d,' % (json.dumps(key), idx))
    js.append("}")
    js.append("")
    js.append("// 立绘 \"角色码|表情\" -> 图片下标")
    js.append("export const SP = {")
    for (kind, key), idx in sorted(IMG_INDEX.items()):
        if kind == "sp":
            js.append('  %s: %d,' % (json.dumps(key, ensure_ascii=False), idx))
    js.append("}")
    js.append("")
    with io.open(os.path.join(out_dir, "src", "common", "assets.js"), "w",
                 encoding="utf-8", newline="\n") as f:
        f.write("\n".join(js))

    # ---------------------------------------------------------- CG 鉴赏清单
    # 分组与解锁条件照抄原作 screens/gallery.rpy 里的 9 个 gallery 按钮：
    #   g.button("xia_cg_1"); g.condition("renpy.seen_image('cg 001')"); g.display(cg 001..003)
    # 这里只把「看过哪张图就解锁哪一组」的语义搬过来。
    gall = []
    miss = []
    for idx, (name, unlock, imgs) in enumerate(GALLERY):
        u = IMG_INDEX.get(("cg", unlock))
        im = []
        for k in imgs:
            v = IMG_INDEX.get(("cg", k))
            if v is None:
                miss.append(k)
            else:
                im.append(v)
        if u is None:
            miss.append(unlock)
        if im:
            gall.append({"n": name, "th": "/common/img/t/g%d.png" % idx,
                         "u": u if u is not None else im[0], "im": im})
    with io.open(os.path.join(out_dir, "src", "common", "cglist.js"), "w",
                 encoding="utf-8", newline="\n") as f:
        f.write("// 由 tools/gen_story.py 自动生成，请勿手改\n"
                "// 分组与解锁条件取自原作 screens/gallery.rpy\n"
                "export const CGG = " +
                json.dumps(gall, ensure_ascii=False, separators=(",", ":")) + "\n")
    if miss:
        WARNINGS.append("CG 鉴赏里有未收录的图: " + ", ".join(sorted(set(miss))))

    # ---------------------------------------------------------- 报告
    stat = {}
    for n in c.out:
        stat[n["t"]] = stat.get(n["t"], 0) + 1
    print("节点总数 : %d" % len(c.out))
    print("分块     : %d 块 (%d/块)" % (len(chunks), CHUNK_SIZE))
    print("章节     : %d" % len(c.chapters))
    print("节点类型 : %s" % stat)
    kinds = {}
    for it in IMG_LIST:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
    print("图片索引 : %s  共 %d 张" % (kinds, len(IMG_LIST)))
    if WARNINGS:
        print("\n!! 待核查 %d 条:" % len(WARNINGS))
        seen = set()
        for a in WARNINGS:
            if a in seen:
                continue
            seen.add(a)
            print("   " + a)
    else:
        print("未发现未解析语句 / 未解析资源")
    return WARNINGS


def collect_assets(raw_dir):
    res = io.open(os.path.join(raw_dir, "resources.rpy"), encoding="utf-8").read()
    bgs = {}
    for m in re.finditer(r'image\s+bg\s+(\w+)\s*=\s*(?:bg_fit|bg_focus)\("([^"]+)"', res):
        bgs[m.group(1)] = m.group(2)
    for m in re.finditer(r'image\s+(\w+)\s*=\s*bg_fit\("(images/bg/[^"]+)"', res):
        bgs.setdefault(m.group(1), m.group(2))
    bgs["black"] = None
    bgs["white"] = None
    cfg = io.open(os.path.join(raw_dir, "config", "character_config.rpy"),
                  encoding="utf-8").read()
    sprites = {}
    for m in re.finditer(r'"(\w+)":\s*\{(.*?)\n        \}', cfg, re.S):
        code, body = m.group(1), m.group(2)
        for em in re.finditer(r'"([^"]+)":\s*"(images/characters/[^"]+)"', body):
            sprites["%s|%s" % (code, em.group(1))] = em.group(2)
    # 杂鱼/剪影立绘（resources.rpy 里的 image <code> <expr> = "images/characters/other/..."）
    for m in re.finditer(r'image\s+(\w+)\s+(\w+)\s*=\s*"(images/characters/other/[^"]+)"', res):
        sprites["%s|%s" % (m.group(1), m.group(2))] = m.group(3)

    # CG / SDCG：cg 001..013、sdcg 001..019（resources.rpy 定义）
    cgs = {}
    for m in re.finditer(r'image\s+cg\s+(\w+)\s*=\s*bg_fit\("(images/cg/[^"]+)"', res):
        cgs["cg_" + m.group(1)] = m.group(2)
    for m in re.finditer(r'image\s+sdcg\s+(\w+)\s*=\s*bg_focus\("(images/sdcg/[^"]+)"', res):
        cgs["sd_" + m.group(1)] = m.group(2)
    for m in re.finditer(r'image\s+(\w+)\s*=\s*bg_fit\("(images/cg/[^"]+)"', res):
        cgs.setdefault(m.group(1), m.group(2))
    # image cg <name> = "images/cg/xxx" 形式（noctella_descend 等）
    for m in re.finditer(r'image\s+cg\s+(\w+)\s*=\s*"(images/cg/[^"]+)"', res):
        cgs.setdefault("cg_" + m.group(1), m.group(2))
    return bgs, sprites, cgs


def _cli():
    raw = os.path.abspath(sys.argv[1] if len(sys.argv) > 1
                          else os.path.join("..", "_extract", "raw"))
    proj = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else ".")
    if not os.path.isdir(os.path.join(raw, "scenes")):
        sys.exit("找不到 Ren'Py 资源目录: %s\n"
                 "用法: python tools/gen_story.py <GalGod 的 game 目录> <本工程目录>\n"
                 "（需要先解包 PC 版 GalGod，把它的 game/ 目录路径传进来；"
                 "该目录下应有 scenes/ resources.rpy config/）" % raw)
    build(raw, proj)


if __name__ == "__main__":
    _cli()
