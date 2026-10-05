# -*- coding: utf-8 -*-
"""
GalGod 手环版 —— 美术资源生成器

把 PC 版的大图转成手环 9 Pro（336x480）能承受的尺寸与体积：
  * 只输出 PNG（真机对 JPEG 解码不可靠）
  * 调色板量化：不透明图 64 色 / 带透明通道图 128 色
  * 尺寸与运行时组件尺寸 1:1，引擎不需要缩放

产出：
  src/common/img/b/<背景代号>.png    336x480，cover 裁剪
  src/common/img/s/<序号>.png        143x380，contain 底部对齐、透明补边
  src/common/img/c/<CG 代号>.png     336x480，contain 居中、黑边
  src/common/home.png                336x480 标题画
  src/common/icon.png                192x192 应用图标

用法:
    python gen_assets.py <renpy_raw_dir> <项目根目录>
"""
import io, os, sys, json

from PIL import Image, ImageDraw, ImageFont

# 画布与运行时组件尺寸（与 src/pages/game/game.ux 的 CSS 保持一致）
SCREEN_W, SCREEN_H = 336, 480

# 背景生成成「宽幅」，运行时在 game.ux 里用 CSS transition 缓慢左右平移做全景效果，
# 而不是死死裁成一块 336×480。
#   BG_W = 336  → 不平移（回到老行为）
#   BG_W = 504  → 可平移 168px（默认，1.5 屏宽）
#   BG_W = 672  → 可平移 336px，画面更宽，但背景体积接近翻倍
# 平移距离 = BG_W - SCREEN_W，必须和 game.ux 的 PAN_RANGE 一致。
BG_W = 504

SPRITE_W, SPRITE_H = 143, 380
BG_COLORS = 128
SP_COLORS = 128
CG_COLORS = 128
THUMB_W, THUMB_H = 96, 54      # CG 鉴赏缩略图（16:9）
THUMB_COLORS = 64


def cover(im, w, h, bias_y=0.5):
    """等比缩放到刚好覆盖 w x h，然后居中裁剪"""
    sw, sh = im.size
    scale = max(float(w) / sw, float(h) / sh)
    nw, nh = max(w, int(round(sw * scale))), max(h, int(round(sh * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = int(round((nh - h) * bias_y))
    top = max(0, min(nh - h, top))
    return im.crop((left, top, left + w, top + h))


def contain(im, w, h, bg=None, anchor="center"):
    """等比缩放到完全放进 w x h，留边"""
    sw, sh = im.size
    scale = min(float(w) / sw, float(h) / sh)
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    if bg is None:
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        canvas = Image.new("RGBA", (w, h), bg)
    left = (w - nw) // 2
    if anchor == "bottom":
        top = h - nh
    else:
        top = (h - nh) // 2
    canvas.paste(im, (left, top), im if im.mode == "RGBA" else None)
    return canvas


def save_palette(im, path, colors, alpha):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if alpha:
        im = im.convert("RGBA")
        q = im.quantize(colors=colors, method=Image.FASTOCTREE)
    else:
        im = im.convert("RGB")
        q = im.quantize(colors=colors, method=Image.MEDIANCUT,
                        dither=Image.FLOYDSTEINBERG)
    q.save(path, "PNG", optimize=True)


def main(raw_dir, proj):
    common = os.path.join(proj, "src", "common")
    assets = json.load(io.open(os.path.join(proj, "tools", "assets.json"),
                               encoding="utf-8"))
    out_root = os.path.join(common, "img")
    total = 0
    report = {}

    for it in assets:
        src = os.path.join(raw_dir, it["src"].replace("/", os.sep))
        if not os.path.isfile(src):
            print("  !! 缺少源图: %s" % src)
            continue
        dst = os.path.join(proj, "src", "common", it["out"].replace("/common/", "").replace("/", os.sep))
        im = Image.open(src)
        kind = it["kind"]

        if kind == "bg":
            # 出成宽幅（BG_W 宽），运行时左右平移做全景；
            # 纵向仍然偏上取景，因为底部会被对话底板挡住
            im = cover(im, BG_W, SCREEN_H, bias_y=0.42)
            save_palette(im, dst, BG_COLORS, alpha=False)
        elif kind == "sp":
            im = contain(im, SPRITE_W, SPRITE_H, bg=None, anchor="bottom")
            save_palette(im, dst, SP_COLORS, alpha=True)
        else:  # cg
            # 满屏铺满（cover 裁两侧）。原先用 contain 留黑边，16:9 的图在 336×480 上
            # 只剩中间 336×189 一条，上下六成全黑，看起来跟没显示一样。
            im = cover(im, SCREEN_W, SCREEN_H, bias_y=0.5)
            save_palette(im, dst, CG_COLORS, alpha=False)

        n = os.path.getsize(dst)
        total += n
        report.setdefault(kind, [0, 0])
        report[kind][0] += 1
        report[kind][1] += n

    # CG 鉴赏缩略图（9 组，每组一张 16:9 小图）
    cglist_path = os.path.join(proj, "src", "common", "cglist.js")
    if os.path.isfile(cglist_path):
        import re as _re
        src_js = io.open(cglist_path, encoding="utf-8").read()
        cgg = json.loads(src_js.split("export const CGG =", 1)[1].strip())
        thumb_dir = os.path.join(common, "img", "t")
        os.makedirs(thumb_dir, exist_ok=True)
        # 用 IMG 数组把下标还原成源文件路径
        assets_js = io.open(os.path.join(common, "assets.js"), encoding="utf-8").read()
        img_paths = _re.findall(r'"(/common/img/[^"]+)"',
                               assets_js.split("export const IMG = [")[1].split("]")[0])
        by_out = {}
        for it in assets:
            by_out[it["out"]] = it["src"]
        for gi, g in enumerate(cgg):
            out = img_paths[g["im"][0]]
            src = os.path.join(raw_dir, by_out.get(out, "").replace("/", os.sep))
            if not os.path.isfile(src):
                continue
            t = cover(Image.open(src), THUMB_W, THUMB_H, bias_y=0.5)
            save_palette(t, os.path.join(thumb_dir, "g%d.png" % gi),
                         THUMB_COLORS, alpha=False)
            total += os.path.getsize(os.path.join(thumb_dir, "g%d.png" % gi))

    # 标题画与图标
    title_src = os.path.join(raw_dir, "images", "cg", "main_screen.avif")
    if os.path.isfile(title_src):
        im = cover(Image.open(title_src), SCREEN_W, SCREEN_H, bias_y=0.5)
        save_palette(im, os.path.join(common, "home.png"), 96, alpha=False)
        total += os.path.getsize(os.path.join(common, "home.png"))

    moon = os.path.join(raw_dir, "images", "bg", "moon.avif")
    if os.path.isfile(moon):
        im = Image.open(moon).convert("RGB")
        w, h = im.size
        side = int(min(w, h) * 0.62)
        cx, cy = int(w * 0.20), int(h * 0.30)
        l = max(0, cx - side // 2); t = max(0, cy - side // 2)
        im = im.crop((l, t, min(w, l + side), min(h, t + side))).resize((192, 192), Image.LANCZOS)
        mask = Image.new("L", (192, 192), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, 191, 191], radius=44, fill=255)
        out = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
        out.paste(im, (0, 0), mask)
        out.save(os.path.join(common, "icon.png"), "PNG", optimize=True)

    print("图片总量 : %.2f MB" % (total / 1048576.0))
    for k, v in report.items():
        print("  %-3s %3d 张  %6.2f MB  均值 %6.0f B" %
              (k, v[0], v[1] / 1048576.0, v[1] / max(1, v[0])))
    if total > 9 * 1048576:
        print("!! 超过 9MB 预算，需要进一步压缩")
    return total


def _cli():
    raw = os.path.abspath(sys.argv[1] if len(sys.argv) > 1
                          else os.path.join("..", "_extract", "raw"))
    proj = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else ".")
    if not os.path.isdir(os.path.join(raw, "images")):
        sys.exit("找不到 Ren'Py 资源目录: %s\n"
                 "用法: python tools/gen_assets.py <GalGod 的 game 目录> <本工程目录>\n"
                 "（需要先解包 PC 版 GalGod，把它的 game/ 目录路径传进来；"
                 "该目录下应有 images/）" % raw)
    main(raw, proj)


if __name__ == "__main__":
    _cli()
