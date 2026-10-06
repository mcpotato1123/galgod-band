# -*- coding: utf-8 -*-
"""
UI 效果预览图生成器

没法上真机截图，这里用真实的游戏资源、按 src/pages/game/game.ux 里的 CSS 数值
1:1 合成界面效果图，用来核对布局、字号、配色与留白。

产出: preview/ui-preview.png
用法: python preview_ui.py <Ren'Py原始目录> <项目根目录>
"""
import io, os, re, sys, json

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 336, 480

# 单张截图的画布尺寸。
# 上架平台的预览框比例和设备屏（336:480 = 0.7）不一致，它会**按框拉满** ——
# 真机反馈过：336x480 的图在平台里被横向拉伸。
# 实测平台框约 0.8（4:5），所以出图时把整屏截图居中放进 384x480 的画布，
# 两侧用自身模糊放大补边：既不变形，也不像生硬的黑边。
# 平台比例若不是 4:5，只改这两个数即可。
SHOT_BOX_W, SHOT_BOX_H = 384, 480
SP_W, SP_H = 143, 380
SP_X = {"left": 10, "center": 96, "right": 182}
SP_TOP = 100

# 与 game.ux 顶部的几何常量保持一致
PANEL_TOP, PANEL_H = 330, 150
NAME_TOP, NAME_LEFT = 292, 12
LINE_TOP, LINE_STEP, LINE_LEFT, LINE_W = 338, 24, 10, 316
MORE_AT = 462


def font(path, size):
    return ImageFont.truetype(path, size)


def load_index(proj):
    story_dir = os.path.join(proj, "src", "common", "story")
    index = json.load(io.open(os.path.join(story_dir, "index.txt"), encoding="utf-8"))
    nodes = []
    for c in sorted(index["chunks"], key=lambda x: x["start"]):
        p = os.path.join(proj, "src", "common",
                         c["file"].replace("/common/", "").replace("/", os.sep))
        nodes += json.load(io.open(p, encoding="utf-8"))
    return index, nodes


def load_assets(proj):
    js = io.open(os.path.join(proj, "src", "common", "assets.js"), encoding="utf-8").read()
    img = re.findall(r'"([^"]+)"', js.split("export const IMG = [")[1].split("]")[0])
    bg = {}
    sp = {}
    for name, body in (("BG", bg), ("SP", sp)):
        block = js.split("export const %s = {" % name)[1].split("}")[0]
        for m in re.finditer(r'(?:"([^"]+)"|(\w+)):\s*(-?\d+)', block):
            key = m.group(1) if m.group(1) else m.group(2)
            body[key] = int(m.group(3))
    return img, bg, sp


def px(proj, path):
    return os.path.join(proj, "src", "common", path.replace("/common/", "").replace("/", os.sep))


def base_screen(proj, img, bgidx):
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    if bgidx == -1:
        return canvas
    if bgidx == -2:
        return Image.new("RGBA", (W, H), (255, 255, 255, 255))
    if bgidx is None or bgidx < 0:
        return canvas
    b = Image.open(px(proj, img[bgidx])).convert("RGBA")
    # 对齐运行时的 object-fit: cover —— 居中裁切。
    # 背景现在是正好 336×480 的图块不用管，但 CG 是 854 宽的全图，
    # 直接贴 (0,0) 会变成左对齐裁切，和真机上看到的画面不一样。
    if b.size != (W, H):
        k = max(W / float(b.size[0]), H / float(b.size[1]))
        nw = max(W, int(round(b.size[0] * k)))
        nh = max(H, int(round(b.size[1] * k)))
        b = b.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - W) // 2, (nh - H) // 2
        b = b.crop((left, top, left + W, top + H))
    canvas.alpha_composite(b, (0, 0))
    return canvas


def draw_sprites(canvas, proj, img, cs):
    for ch in cs:
        src = img[ch["i"]]
        s = Image.open(px(proj, src)).convert("RGBA")
        canvas.alpha_composite(s, (SP_X.get(ch["s"], 96), SP_TOP))


def draw_hud(canvas, f_title, f_prog, title, progress):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tw = d.textlength(title, font=f_title) + d.textlength(progress, font=f_prog) + 28
    d.rounded_rectangle([12, 10, 12 + tw, 36], radius=13, fill=(0, 0, 0, 140))
    d.text((22, 13), title, font=f_title, fill=(255, 230, 239))
    d.text((22 + d.textlength(title, font=f_title) + 8, 15), progress,
           font=f_prog, fill=(185, 176, 182))
    # 右上角菜单按钮：放大到 52x52（原来 36，手环上不好点）
    d.rounded_rectangle([278, 6, 330, 58], radius=26, fill=(27, 21, 32, 209))
    ow = d.textlength("≡", font=font(FONT, 30))
    d.text((278 + (52 - ow) / 2, 14), "≡", font=font(FONT, 30), fill=(255, 216, 230))
    canvas.alpha_composite(layer)


def draw_panel(canvas, f_name, f_body, speaker, lines, can_tap=True):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, PANEL_TOP, W, H], fill=(18, 13, 19, 204))
    if speaker:
        # 说话人自带一块跟着文字宽度走的半透明底板（对应 .name 的 padding+background）
        f_sp = font(FONT, 20)
        tw = d.textlength(speaker, font=f_sp)
        d.rounded_rectangle([NAME_LEFT, NAME_TOP, NAME_LEFT + tw + 20, NAME_TOP + 32],
                            radius=9, fill=(16, 11, 18, 189))
        d.text((NAME_LEFT + 10, NAME_TOP + 5), speaker, font=f_sp, fill=(255, 216, 230))
    for i, ln in enumerate(lines[:5]):
        d.text((LINE_LEFT, LINE_TOP + i * LINE_STEP), ln, font=f_body, fill=(255, 255, 255))
    if can_tap:
        d.text((308, MORE_AT), "▼", font=font(FONT, 16), fill=(255, 158, 196))
    canvas.alpha_composite(layer)


# 剧本节点里的台词在 "x" 字段，"p" 是**运行时算出来的分页**，静态数据里永远是空的。
# 之前预览脚本读的是 "p"，所以正文和 CG 面板一直画不出台词（空底板）。
# 这里按 reader.js 的 wrapText 规则自己折行，保证预览和真机显示一致。
BREAK_AFTER = '，。！？；：、）」』…—'


def first_page(text, cpl=15, lpp=5):
    """按 reader.js 的 wrapText + paginateText 取第一页（字号 20 时 cpl=15, lpp=5）"""
    lines = []
    for raw in str(text or '').split('\n'):
        s = raw
        if s == '':
            lines.append('')
            continue
        while len(s) > cpl:
            cut = cpl
            lo = max(2, cpl - 8)
            k = cpl
            while k > lo:
                if BREAK_AFTER.find(s[k - 1]) >= 0:
                    cut = k
                    break
                k -= 1
            lines.append(s[:cut])
            s = s[cut:]
        lines.append(s)
    if not lines:
        lines = ['']
    return lines[:lpp]


def draw_choices(canvas, f_body, labels):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y = 96
    for lb in labels:
        h = 52
        d.rounded_rectangle([16, y, 320, y + h], radius=12, fill=(36, 26, 43, 240))
        d.text((26, y + 13), lb, font=f_body, fill=(255, 230, 239))
        y += h + 8
    canvas.alpha_composite(layer)


def draw_menu(canvas, f_title, f_sub, f_btn):
    """与 game.ux 的菜单保持一致：6 个整行 + 2 行双按钮 + 退出，36px 高 / 5px 间距"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, 0, W, H], fill=(20, 15, 23, 255))
    tw = d.textlength("阅读菜单", font=f_title)
    d.text(((W - tw) / 2, 14), "阅读菜单", font=f_title, fill=(255, 216, 230))
    sub = "第三幕 · 天选试 · 42%"
    d.text(((W - d.textlength(sub, font=f_sub)) / 2, 50), sub, font=f_sub, fill=(164, 151, 159))
    items = [("继续阅读", True), ("保存进度", False), ("读取存档", False),
             ("自动播放：关", False), ("快进：开", False), ("跳到下一章", False)]
    y = 75
    for txt, main in items:
        d.rounded_rectangle([48, y, 288, y + 36], radius=18,
                            fill=(185, 80, 121, 255) if main else (44, 33, 51, 255))
        tw2 = d.textlength(txt, font=f_btn)
        d.text((48 + (240 - tw2) / 2, y + 8), txt, font=f_btn, fill=(255, 255, 255))
        y += 41
    for pair in (("章节", "CG"), ("设置", "主页")):
        for i, txt in enumerate(pair):
            x = 48 + i * 124
            d.rounded_rectangle([x, y, x + 116, y + 36], radius=18, fill=(44, 33, 51, 255))
            tw3 = d.textlength(txt, font=f_btn)
            d.text((x + (116 - tw3) / 2, y + 8), txt, font=f_btn, fill=(255, 255, 255))
        y += 41
    d.rounded_rectangle([48, y + 4, 288, y + 40], radius=18, fill=(36, 26, 43, 255))
    tw4 = d.textlength("退出", font=f_btn)
    d.text((48 + (240 - tw4) / 2, y + 12), "退出", font=f_btn, fill=(255, 255, 255))
    canvas.alpha_composite(layer)


def label(img, txt, f):
    d = ImageDraw.Draw(img)
    d.text((8, 8), txt, font=f, fill=(255, 220, 120))
    return img


FONT = None


def main(raw, proj):
    global FONT
    FONT = os.path.join(raw, "SourceHanSansCN-Medium.otf")
    f_name = font(FONT, 22)
    f_body = font(FONT, 20)
    f_small = font(FONT, 17)
    f_tiny = font(FONT, 15)
    f_btn = font(FONT, 19)
    f_big = font(FONT, 24)
    f_tag = font(FONT, 16)

    index, nodes = load_index(proj)
    img, bg, sp = load_assets(proj)

    # 挑一个真实的双人对话场景
    scene = None
    for i, n in enumerate(nodes):
        if n.get("t") == "s" and n.get("bg") is not None and len(n.get("cs") or []) == 2:
            scene = (i, n)
            break
    if scene is None:
        for i, n in enumerate(nodes):
            if n.get("t") == "s" and n.get("cs"):
                scene = (i, n)
                break

    # 找一个 CG 场景。
    # 默认取剧本里第一处 CG，但那张刚好是张张开大嘴的搞笑图，当宣传图不合适；
    # 所以优先挑这几张氛围好的（存在就用），都不在才退回第一处。
    # **必须同时有台词** —— 只挂 CG 没有文本的节点做出来是一块空底板，很难看。
    PREFER_CG = ("cg_notella_descend_full", "cg_notella_descend", "cg_006", "cg_005")

    def has_text(n):
        return bool((n.get("x") or "").strip())

    cgscene = None
    for want in PREFER_CG:
        for i, n in enumerate(nodes):
            if n.get("t") != "s" or n.get("cg") is None or n["cg"] < 0:
                continue
            if not has_text(n):
                continue
            if os.path.basename(img[n["cg"]]).startswith(want):
                cgscene = (i, n)
                break
        if cgscene:
            break
    if cgscene is None:
        for i, n in enumerate(nodes):
            if (n.get("t") == "s" and n.get("cg") is not None and n["cg"] >= 0
                    and has_text(n)):
                cgscene = (i, n)
                break
    if cgscene:
        print("  CG 面板用: %s" % os.path.basename(img[cgscene[1]["cg"]]))

    # 找一个分支
    choices = None
    for n in nodes:
        if n.get("t") == "o":
            choices = n
            break

    panels = []

    # 1. 正文（双人 + 对白）
    ci, cn = scene
    c = base_screen(proj, img, cn.get("bg"))
    draw_sprites(c, proj, img, cn.get("cs") or [])
    ch = index["chapters"]
    cur = 0
    for k, cc in enumerate(ch):
        if ci >= cc["start"]:
            cur = k
    draw_hud(c, f_small, f_tiny, ch[cur]["title"], "38%")
    draw_panel(c, f_name, f_body, cn.get("n") or "", first_page(cn.get("x")))
    panels.append((c, "① 正文（背景 + 双立绘 + 对白）"))

    # 2. 分支选择
    c2 = base_screen(proj, img, cn.get("bg"))
    draw_sprites(c2, proj, img, cn.get("cs") or [])
    draw_hud(c2, f_small, f_tiny, ch[cur]["title"], "46%")
    opts = [o["x"] for o in (choices or {}).get("o", [])][:5]
    draw_choices(c2, f_body, opts or ["（无分支）"])
    panels.append((c2, "② 分支选项（覆盖在画面上）"))

    # 3. CG
    c3 = base_screen(proj, img, -1)
    if cgscene:
        cgimg = Image.open(px(proj, img[cgscene[1]["cg"]])).convert("RGBA")
        c3.alpha_composite(cgimg, (0, 0))
        draw_panel(c3, f_name, f_body, cgscene[1].get("n") or "", first_page(cgscene[1].get("x")))
    panels.append((c3, "③ CG 插入（满屏铺满，底板变透）"))

    # 4. 阅读菜单
    c4 = base_screen(proj, img, cn.get("bg"))
    draw_sprites(c4, proj, img, cn.get("cs") or [])
    draw_menu(c4, f_big, f_tiny, f_btn)
    panels.append((c4, "④ 阅读菜单"))

    # 5. 主页
    # 顶部不再有 "GalGod" 与副标题文字：现在 home.png 本身就是原图那张
    # 「logo 在左、女孩在右」的完整构图，再叠文字会盖住它、内容也重复。
    c5 = Image.open(px(proj, "/common/home.png")).convert("RGBA")
    shade = Image.new("RGBA", (W, H), (13, 9, 16, 87))
    c5 = Image.alpha_composite(c5, shade)
    d = ImageDraw.Draw(c5)
    d.rectangle([0, 240, W, H], fill=(21, 15, 25, 240))
    d.text((84, 252), "最近进度 · 第4章", font=f_tiny, fill=(185, 167, 179))
    for i, (txt, main, wide) in enumerate([("开始阅读", True, True), ("继续阅读", False, True)]):
        y = 276 + i * 48
        d.rounded_rectangle([50, y, 286, y + 40], radius=20,
                            fill=(185, 80, 121, 255) if main else (50, 36, 58, 255))
        tw = d.textlength(txt, font=f_btn)
        d.text((50 + (236 - tw) / 2, y + 9), txt, font=f_btn, fill=(255, 255, 255))
    for i, txt in enumerate(("存档", "章节", "CG", "设置", "关于")):
        x = 50 + i * 47
        d.rounded_rectangle([x, 372, x + 46, 412], radius=20, fill=(50, 36, 58, 255))
        tw = d.textlength(txt, font=font(FONT, 16))
        d.text((x + (46 - tw) / 2, 383), txt, font=font(FONT, 16), fill=(255, 255, 255))
    d.rounded_rectangle([50, 418, 286, 458], radius=20, fill=(36, 26, 43, 255))
    tw = d.textlength("退出", font=f_btn)
    d.text((50 + (236 - tw) / 2, 427), "退出", font=f_btn, fill=(255, 255, 255))
    panels.append((c5, "⑤ 主页"))

    # 6. 章节选择（<list> 大条目，一屏 4 条）
    c6 = Image.new("RGBA", (W, H), (20, 16, 26, 255))
    d = ImageDraw.Draw(c6)
    tw = d.textlength("章节选择", font=f_big)
    d.text(((W - tw) / 2, 10), "章节选择", font=f_big, fill=(255, 216, 230))
    hint = "共 14 章 · 上下滑动 · 点按开始"
    tw2 = d.textlength(hint, font=f_tiny)
    d.text(((W - tw2) / 2, 44), hint, font=f_tiny, fill=(156, 143, 155))
    f_no = font(FONT, 17)
    f_nm = font(FONT, 24)
    for i, cc in enumerate(index["chapters"][:4]):
        y = 74 + i * 86
        d.rounded_rectangle([12, y, 324, y + 74], radius=16, fill=(36, 28, 44, 255))
        d.text((26, y + 25), str(i + 1), font=f_no, fill=(207, 158, 192))
        d.text((64, y + 18), cc["title"], font=f_nm, fill=(255, 230, 239))
        if i == 1:
            d.text((296, y + 27), "▶", font=f_no, fill=(126, 232, 224))
    # 第 5 条露一点，暗示还能滑
    d.rounded_rectangle([12, 418, 324, 426], radius=4, fill=(36, 28, 44, 255))
    d.rounded_rectangle([50, 432, 286, 472], radius=20, fill=(50, 36, 58, 255))
    tw3 = d.textlength("返回", font=f_btn)
    d.text(((W - tw3) / 2, 441), "返回", font=f_btn, fill=(255, 255, 255))
    panels.append((c6, "⑥ 章节选择（<list> 大条目，上下滑动）"))

    # 7. CG 鉴赏（<list> 缩略图 + 解锁状态）
    cgg = []
    cglist_path = os.path.join(proj, "src", "common", "cglist.js")
    if os.path.isfile(cglist_path):
        cgg = json.loads(io.open(cglist_path, encoding="utf-8").read()
                         .split("export const CGG =", 1)[1].strip())
    c7 = Image.new("RGBA", (W, H), (20, 16, 26, 255))
    d = ImageDraw.Draw(c7)
    tw = d.textlength("CG 鉴赏", font=f_big)
    d.text(((W - tw) / 2, 10), "CG 鉴赏", font=f_big, fill=(255, 216, 230))
    hint = "已解锁 3 / %d 组 · 点按查看" % max(1, len(cgg))
    tw2 = d.textlength(hint, font=f_tiny)
    d.text(((W - tw2) / 2, 44), hint, font=f_tiny, fill=(156, 143, 155))
    f_nm2 = font(FONT, 21)
    f_st = font(FONT, 14)
    for i in range(4):
        y = 74 + i * 86
        d.rounded_rectangle([12, y, 324, y + 74], radius=16, fill=(36, 28, 44, 255))
        g = cgg[i] if i < len(cgg) else None
        unlocked = i < 3
        if g and unlocked:
            th = Image.open(px(proj, g["th"])).convert("RGB").resize((96, 54), Image.LANCZOS)
            c7.paste(th, (22, y + 10))
        else:
            d.rounded_rectangle([22, y + 10, 118, y + 64], radius=8, fill=(25, 19, 32, 255))
            q = "?"
            d.text((22 + (96 - d.textlength(q, font=font(FONT, 26))) / 2, y + 20), q,
                   font=font(FONT, 26), fill=(76, 64, 85))
        name = g["n"] if g else "——"
        d.text((130, y + 24), name, font=f_nm2, fill=(255, 230, 239))
        st = ("%d 张" % len(g["im"])) if (g and unlocked) else "未解锁"
        d.text((324 - 14 - d.textlength(st, font=f_st), y + 30), st, font=f_st,
               fill=(156, 143, 155))
    d.rounded_rectangle([50, 432, 286, 472], radius=20, fill=(50, 36, 58, 255))
    tw3 = d.textlength("返回", font=f_btn)
    d.text(((W - tw3) / 2, 441), "返回", font=f_btn, fill=(255, 255, 255))
    panels.append((c7, "⑦ CG 鉴赏（缩略图 + 解锁状态）"))

    # 8. CG 鉴赏：打开大图
    # CG 是一张 854 宽的宽图，查看器 336 宽、靠 left 决定看哪一段；
    # 打开时停在正中间（cg.ux 里 setPan(CG_PAN_RANGE / 2)）。
    c8cg = Image.new("RGB", (W, H), (0, 0, 0))
    CGW = 854
    pan = (CGW - W) // 2                     # 居中 -> 259
    # 用第 3 组（「小涟」，3 张）—— 图好看，而且有 3 张才能体现 ‹ › 换差分与张数计数。
    # 它在上面的列表里也是解锁状态，两格不矛盾。
    vgroup = cgg[2] if len(cgg) > 2 else (cgg[0] if cgg else None)
    vgname = vgroup["n"] if vgroup else ""
    vtotal = len(vgroup["im"]) if vgroup else 0
    vpage = 2 if vtotal >= 2 else 1
    vimg = vgroup["im"][vpage - 1] if vgroup else None
    if vimg is not None:
        src_path = img[vimg]
        big = Image.open(px(proj, src_path)).convert("RGB")
        big = big.resize((CGW, H), Image.LANCZOS) if big.size != (CGW, H) else big
        c8cg.paste(big, (-pan, 0))           # 负偏移，超出部分自动裁掉
    c8cg = c8cg.convert("RGBA")
    d = ImageDraw.Draw(c8cg)
    # 顶部：组名 + 第几张
    d.text((14, 12), vgname or "", font=font(FONT, 16), fill=(255, 230, 239))
    vnum = "%d / %d" % (vpage, vtotal)
    d.text((14 + d.textlength(vgname or "", font=font(FONT, 16)) + 10, 13), vnum,
           font=font(FONT, 15), fill=(216, 203, 210))
    # 关闭
    d.rounded_rectangle([262, 10, 326, 44], radius=17, fill=(0, 0, 0, 158))
    tw4 = d.textlength("关闭", font=font(FONT, 17))
    d.text((262 + (64 - tw4) / 2, 17), "关闭", font=font(FONT, 17), fill=(255, 230, 239))
    # 拖动提示（下面垫一层半透明底板：浅色 CG 上纯文字看不清）
    d.rounded_rectangle([14, 384, 322, 422], radius=12, fill=(0, 0, 0, 128))
    hint = "按住画面左右拖动，看被裁掉的部分"
    d.text(((W - d.textlength(hint, font=font(FONT, 13))) / 2, 392), hint,
           font=font(FONT, 13), fill=(232, 222, 230, 235))
    # 位置指示条：轨道 240，滑块 94（= 屏幕宽/图宽），居中时在正中间
    d.rounded_rectangle([48, 412, 288, 417], radius=3, fill=(255, 255, 255, 71))
    tx = 48 + int((240 - 94) * (float(pan) / (CGW - W)))
    d.rounded_rectangle([tx, 412, tx + 94, 417], radius=3, fill=(255, 216, 230, 255))
    # 底栏：‹ 换一张差分 ›
    d.rounded_rectangle([22, 428, 314, 470], radius=21, fill=(0, 0, 0, 158))
    for bx, ch in ((28, "‹"), (262, "›")):
        d.rounded_rectangle([bx, 432, bx + 46, 466], radius=17, fill=(50, 36, 58, 255))
        cw = d.textlength(ch, font=font(FONT, 22))
        d.text((bx + (46 - cw) / 2, 437), ch, font=font(FONT, 22), fill=(255, 255, 255))
    lbl = "换一张差分"
    d.text(((W - d.textlength(lbl, font=font(FONT, 14))) / 2, 441), lbl,
           font=font(FONT, 14), fill=(226, 214, 224, 204))
    panels.append((c8cg, "⑧ CG 鉴赏「打开大图」（可拖动看全图）"))

    # 8. 设置（滑块 + 步进按钮）
    c8 = Image.new("RGBA", (W, H), (20, 16, 26, 255))
    d = ImageDraw.Draw(c8)
    tw = d.textlength("设置", font=f_big)
    d.text(((W - tw) / 2, 2), "设置", font=font(FONT, 21), fill=(255, 216, 230))
    f_lab = font(FONT, 16)
    f_val = font(FONT, 15)
    f_small2 = font(FONT, 12)

    def slider(y, lo, hi, val):
        cx0, cx1, cy = 24, 312, y + 17
        d.rounded_rectangle([cx0, cy - 3, cx1, cy + 3], radius=3, fill=(58, 46, 68, 255))
        t = (val - lo) / float(hi - lo)
        d.rounded_rectangle([cx0, cy - 3, cx0 + int((cx1 - cx0) * t), cy + 3],
                            radius=3, fill=(185, 80, 121, 255))
        kx = cx0 + int((cx1 - cx0 - 22) * t)
        d.ellipse([kx, cy - 11, kx + 22, cy + 11], fill=(255, 216, 230, 255))

    def stepper(y, val):
        for x, s in ((196, "−"), (286, "＋")):
            d.rounded_rectangle([x, y, x + 32, y + 26], radius=13, fill=(50, 36, 58, 255))
            ow = d.textlength(s, font=font(FONT, 17))
            d.text((x + (32 - ow) / 2, y + 2), s, font=font(FONT, 17), fill=(255, 255, 255))
        vw = d.textlength(val, font=f_val)
        d.text((232 + (50 - vw) / 2, y + 4), val, font=f_val, fill=(255, 179, 205))

    rows = [
        (34, 30, "字体大小", "20", 60, 14, 30, 20),
        (98, 94, "播放速度", "28", 124, 0, 120, 28),
        (162, 158, "自动播放速度", "关闭", 188, 0, 200, 0),
    ]
    for ly, sy, label, val, ky, lo, hi, v in rows:
        d.text((14, ly), label, font=f_lab, fill=(207, 194, 203))
        stepper(sy, val)
        slider(ky, lo, hi, v)
    # 两个开关行：屏幕常亮 / 长按隐藏界面（快进不在这里，它在阅读菜单里）
    for ly, ky, label in ((228, 226, "屏幕常亮"), (262, 260, "长按隐藏界面")):
        d.text((14, ly), label, font=f_lab, fill=(207, 194, 203))
        for i, (t, on) in enumerate((("关", False), ("开", True))):
            x = 228 + i * 50
            d.rounded_rectangle([x, ky, x + 44, ky + 30], radius=15,
                                fill=(185, 80, 121, 255) if on else (44, 33, 51, 255))
            ow = d.textlength(t, font=font(FONT, 15))
            d.text((x + (44 - ow) / 2, ky + 7), t, font=font(FONT, 15),
                   fill=(255, 255, 255) if on else (203, 188, 198))
    d.text((14, 296), "字号 14~30 px，显示的数字就是 px", font=f_small2, fill=(139, 127, 137))
    d.text((14, 310), "播放速度＝每字毫秒；自动播放速度＝每句停留毫秒",
           font=f_small2, fill=(139, 127, 137))
    # 实时预览
    d.rounded_rectangle([12, 326, 324, 414], radius=14, fill=(18, 13, 19, 235))
    d.text((24, 330), "林曦", font=font(FONT, 18), fill=(255, 216, 230))
    d.text((24, 356), "想成为Galgame领域大神！！！", font=f_body, fill=(255, 255, 255))
    for i, t in enumerate(("重置", "返回")):
        x = 50 + i * 122
        d.rounded_rectangle([x, 420, x + 114, 460], radius=20, fill=(50, 36, 58, 255))
        ow = d.textlength(t, font=font(FONT, 18))
        d.text((x + (114 - ow) / 2, 430), t, font=font(FONT, 18), fill=(255, 255, 255))
    panels.append((c8, "⑨ 设置（3 滑块 + 屏幕常亮 / 长按隐藏）"))

    # 9. 关于（正文）
    def about_base(with_dots):
        c = Image.new("RGBA", (W, H), (20, 16, 26, 255))
        dd = ImageDraw.Draw(c)
        dd.text(((W - dd.textlength("关于", font=font(FONT, 22))) / 2, 4), "关于",
                font=font(FONT, 22), fill=(255, 216, 230))
        if with_dots:
            dd.text((286, 10), "···", font=font(FONT, 15), fill=(255, 158, 196))
        # 版本号从 manifest.json 读，不要在脚本里写死 ——
        # 写死过，结果截图里还挂着 v2.3.6 而实际已经是 2.3。
        try:
            _mf = json.load(io.open(os.path.join(proj, "src", "manifest.json"),
                                    encoding="utf-8"))
            _ver = _mf.get("versionName", "?")
        except Exception:
            _ver = "?"
        sub = "GalGod · 小米手环 9 Pro 版 · v%s" % _ver
        dd.text(((W - dd.textlength(sub, font=font(FONT, 12))) / 2, 36), sub,
                font=font(FONT, 12), fill=(156, 143, 155))
        rows = [
            ("s", "故事梗概"),
            ("p", "在一个由「天选试」决定一切的世界里——"),
            ("p", "国家每三年举办一次天选试，一次录取"),
            ("p", "一千人，考核内容全部是美少女游戏"),
            ("p", "（Galgame）。"),
            ("g", ""),
            ("p", "主角陈舟是个不折不扣的 Galgame 废萌"),
            ("p", "党。比起上学，他更想打游戏。"),
            ("g", ""),
            ("p", "林曦是他的青梅竹马兼「好哥们」，比谁"),
            ("p", "都温柔，却对 Galgame 既无兴趣也无才能。"),
            ("g", ""),
            ("p", "还有小涟——只有他能看见的纯白少女，"),
            ("p", "与月光同在。"),
        ]
        fr = font(FONT, 15)
        for i, (k, t) in enumerate(rows):
            col = (255, 179, 205) if k == "s" else (217, 205, 214)
            dd.text((14, 58 + i * 25 + 5), t, font=fr, fill=col)
        dd.rounded_rectangle([50, 432, 286, 472], radius=20, fill=(50, 36, 58, 255))
        tw = dd.textlength("返回", font=f_btn)
        dd.text(((W - tw) / 2, 441), "返回", font=f_btn, fill=(255, 255, 255))
        return c

    panels.append((about_base(False), "⑩ 关于（故事梗概 / 版权信息，可滚动）"))

    # 10. 彩蛋菜单
    c10 = about_base(True)
    d = ImageDraw.Draw(c10)
    d.rectangle([0, 0, W, H], fill=(8, 6, 10, 184))
    d.rounded_rectangle([32, 132, 304, 344], radius=18, fill=(36, 28, 44, 255))
    d.text((32 + (272 - d.textlength("？？？", font=font(FONT, 17))) / 2, 146),
           "？？？", font=font(FONT, 17), fill=(126, 232, 224))
    for i, t in enumerate(("解锁 · 后日谈", "解锁 · 全部 CG", "关闭")):
        y = 175 + i * 48
        d.rounded_rectangle([60, y, 276, y + 40], radius=20,
                            fill=(42, 32, 51, 255) if i == 2 else (58, 43, 69, 255))
        tw = d.textlength(t, font=font(FONT, 17))
        d.text((60 + (216 - tw) / 2, y + 10), t, font=font(FONT, 17), fill=(255, 255, 255))
    panels.append((c10, "⑪ 彩蛋：连点「关于」7 次"))

    # 拼图（标签放在每格上方的独立条里，避免压住界面）
    cols, gap, pad, lab = 3, 10, 16, 26
    rows = (len(panels) + cols - 1) // cols
    cw, chh = W + gap, H + lab + gap
    sheet = Image.new("RGB", (pad * 2 + cols * cw - gap,
                              pad * 2 + rows * chh - gap + 34), (26, 24, 30))
    d = ImageDraw.Draw(sheet)
    for i, (p, txt) in enumerate(panels):
        r, cc = divmod(i, cols)
        x = pad + cc * cw
        y = pad + 34 + r * chh
        d.text((x + 2, y + 4), txt, font=f_tag, fill=(255, 220, 120))
        sheet.paste(p.convert("RGB"), (x, y + lab))
    d.text((pad, 8), "GalGod · 小米手环 9 Pro（336×480）界面效果预览 —— 按 game.ux 的 CSS 数值 1:1 合成",
           font=font(FONT, 19), fill=(240, 235, 220))

    out = os.path.join(proj, "preview")
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, "ui-preview.png")
    sheet.save(dst, "PNG", optimize=True)
    print("已生成: %s  %dx%d  %.0f KB" % (dst, sheet.width, sheet.height,
                                          os.path.getsize(dst) / 1024))

    # 另外把每格单独存成一张图 —— 上架平台要的是**多张截图**，不是拼图。
    # 尺寸就是设备原生分辨率 336x480，和真机截图一致。
    # 优先放到同级的上架素材目录（用户直接拿去上传）；仓库里没有那个目录时，
    # 退回 preview/shots/，免得往仓库外面乱写。
    ab = os.path.abspath(os.path.join(proj, "..", "AstroBox上架"))
    shots = os.path.join(ab, "截图") if os.path.isdir(ab) else os.path.join(out, "shots")
    os.makedirs(shots, exist_ok=True)
    for f in os.listdir(shots):
        # 只删自己产出的那 10 张（01- ~ 10-）；
        # 00-版权声明.png 是上架素材里的另一张，由 AstroBox上架/tools/gen_cover.py 生成，
        # 不能顺手删掉。
        if f.endswith(".png") and re.match(r"^(0[1-9]|1[01])-", f):
            os.remove(os.path.join(shots, f))
    names = ["正文", "分支选项", "CG插入", "阅读菜单", "主页",
             "章节选择", "CG鉴赏", "CG查看", "设置", "关于", "彩蛋"]

    # 上架平台的预览框比例和设备屏不一致，会把图**拉满**导致变形
    # （真机上反馈过：336x480 的截图在平台里被横向拉伸）。
    # 所以出图时把整屏截图放进 SHOT_BOX 比例的画布里，两侧用自身模糊放大补边 ——
    # 既不变形，也不像生硬的黑边。
    BOX_W, BOX_H = SHOT_BOX_W, SHOT_BOX_H
    for i, (p, txt) in enumerate(panels):
        nm = names[i] if i < len(names) else ("panel%d" % (i + 1))
        f = os.path.join(shots, "%02d-%s.png" % (i + 1, nm))
        shot = p.convert("RGB").resize((W, H), Image.LANCZOS)
        bg = shot.resize((BOX_W, BOX_H), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(20))
        bg = ImageEnhance.Brightness(bg).enhance(0.42)
        bg.paste(shot, ((BOX_W - W) // 2, (BOX_H - H) // 2))
        bg.save(f, "PNG", optimize=True)
    print("单张截图 %d 张 -> %s  (画布 %dx%d，设备屏 %dx%d 居中)"
          % (len(panels), shots, BOX_W, BOX_H, W, H))


def _cli():
    raw = os.path.abspath(sys.argv[1] if len(sys.argv) > 1
                          else os.path.join("..", "_extract", "raw"))
    proj = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else ".")
    if not os.path.isfile(os.path.join(raw, "SourceHanSansCN-Medium.otf")):
        sys.exit("找不到 Ren'Py 资源目录: %s\n"
                 "用法: python tools/preview_ui.py <GalGod 的 game 目录> <本工程目录>\n"
                 "（合成预览图需要原版字体 SourceHanSansCN-Medium.otf）" % raw)
    main(raw, proj)


if __name__ == "__main__":
    _cli()
