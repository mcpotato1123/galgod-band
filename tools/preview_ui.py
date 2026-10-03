# -*- coding: utf-8 -*-
"""
UI 效果预览图生成器

没法上真机截图，这里用真实的游戏资源、按 src/pages/game/game.ux 里的 CSS 数值
1:1 合成界面效果图，用来核对布局、字号、配色与留白。

产出: preview/ui-preview.png
用法: python preview_ui.py <Ren'Py原始目录> <项目根目录>
"""
import io, os, re, sys, json

from PIL import Image, ImageDraw, ImageFont

W, H = 336, 480
SP_W, SP_H = 143, 380
SP_X = {"left": 10, "center": 96, "right": 182}
SP_TOP = 100

PANEL_TOP, PANEL_H = 312, 168
LINE_TOP, LINE_STEP, LINE_LEFT, LINE_W = 350, 24, 14, 308


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
    d.rounded_rectangle([290, 8, 326, 44], radius=18, fill=(27, 21, 32, 209))
    d.text((301, 14), "≡", font=font(FONT, 24), fill=(255, 216, 230))
    canvas.alpha_composite(layer)


def draw_panel(canvas, f_name, f_body, speaker, lines, can_tap=True):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, PANEL_TOP, W, H], fill=(18, 13, 19, 204))
    if speaker:
        d.text((LINE_LEFT, 318), speaker, font=f_name, fill=(255, 216, 230))
    for i, ln in enumerate(lines[:5]):
        d.text((LINE_LEFT, LINE_TOP + i * LINE_STEP), ln, font=f_body, fill=(255, 255, 255))
    if can_tap:
        d.text((308, 456), "▼", font=font(FONT, 16), fill=(255, 158, 196))
    canvas.alpha_composite(layer)


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
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, 0, W, H], fill=(20, 15, 23, 255))
    d.text((113, 18), "阅读菜单", font=f_title, fill=(255, 216, 230))
    d.text((88, 50), "第三幕 · 天选试 · 42%", font=f_sub, fill=(164, 151, 159))
    items = [("继续阅读", True), ("保存进度", False), ("读取存档", False),
             ("自动播放：关", False), ("跳到下一章", False)]
    y = 78
    for txt, main in items:
        d.rounded_rectangle([48, y, 288, y + 42], radius=21,
                            fill=(185, 80, 121, 255) if main else (44, 33, 51, 255))
        tw = d.textlength(txt, font=f_btn)
        d.text((48 + (240 - tw) / 2, y + 10), txt, font=f_btn, fill=(255, 255, 255))
        y += 50
    for i, txt in enumerate(("章节", "主页")):
        x = 48 + i * 124
        d.rounded_rectangle([x, y, x + 116, y + 42], radius=21, fill=(44, 33, 51, 255))
        tw = d.textlength(txt, font=f_btn)
        d.text((x + (116 - tw) / 2, y + 10), txt, font=f_btn, fill=(255, 255, 255))
    d.rounded_rectangle([48, y + 50, 288, y + 92], radius=21, fill=(36, 26, 43, 255))
    d.text((142, y + 60), "退出", font=f_btn, fill=(255, 255, 255))
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

    # 找一个 CG 场景
    cgscene = None
    for i, n in enumerate(nodes):
        if n.get("t") == "s" and n.get("cg") is not None and n["cg"] >= 0:
            cgscene = (i, n)
            break

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
    draw_panel(c, f_name, f_body, cn.get("n") or "", (cn.get("p") or [""])[0].split("\n"))
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
        draw_panel(c3, f_name, f_body, cgscene[1].get("n") or "",
                   (cgscene[1].get("p") or [""])[0].split("\n"))
    panels.append((c3, "③ CG 插入（满屏铺满，底板变透）"))

    # 4. 阅读菜单
    c4 = base_screen(proj, img, cn.get("bg"))
    draw_sprites(c4, proj, img, cn.get("cs") or [])
    draw_menu(c4, f_big, f_tiny, f_btn)
    panels.append((c4, "④ 阅读菜单"))

    # 5. 主页
    c5 = Image.open(px(proj, "/common/home.png")).convert("RGBA")
    shade = Image.new("RGBA", (W, H), (13, 9, 16, 87))
    c5 = Image.alpha_composite(c5, shade)
    d = ImageDraw.Draw(c5)
    d.text((104, 54), "GalGod", font=font(FONT, 46), fill=(255, 233, 241))
    d.text((110, 116), "月幕 · 手环版", font=f_small, fill=(214, 188, 200))
    d.rectangle([0, 240, W, H], fill=(21, 15, 25, 240))
    d.text((84, 252), "最近进度 · 第4章", font=f_tiny, fill=(185, 167, 179))
    for i, (txt, main, wide) in enumerate([("开始阅读", True, True), ("继续阅读", False, True)]):
        y = 276 + i * 48
        d.rounded_rectangle([50, y, 286, y + 40], radius=20,
                            fill=(185, 80, 121, 255) if main else (50, 36, 58, 255))
        tw = d.textlength(txt, font=f_btn)
        d.text((50 + (236 - tw) / 2, y + 9), txt, font=f_btn, fill=(255, 255, 255))
    for i, txt in enumerate(("存档", "章节", "CG")):
        x = 50 + i * 81
        d.rounded_rectangle([x, 372, x + 74, 412], radius=20, fill=(50, 36, 58, 255))
        tw = d.textlength(txt, font=f_btn)
        d.text((x + (74 - tw) / 2, 381), txt, font=f_btn, fill=(255, 255, 255))
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
    hint = "已解锁 2 / %d 组 · 点按查看" % max(1, len(cgg))
    tw2 = d.textlength(hint, font=f_tiny)
    d.text(((W - tw2) / 2, 44), hint, font=f_tiny, fill=(156, 143, 155))
    f_nm2 = font(FONT, 21)
    f_st = font(FONT, 14)
    for i in range(4):
        y = 74 + i * 86
        d.rounded_rectangle([12, y, 324, y + 74], radius=16, fill=(36, 28, 44, 255))
        g = cgg[i] if i < len(cgg) else None
        unlocked = i < 2
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
