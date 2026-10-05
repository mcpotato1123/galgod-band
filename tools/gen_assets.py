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

# ---- 背景：自动全景
# 不再输出一张宽图让运行时自己平移（试过，真机上出接缝），
# 而是把宽幅画面**预切成整屏大小的图块**，运行时用 <swiper autoplay> 轮播。
# 裁切与动画全部交给 swiper 组件，代码里不做任何 overflow 或 left 补间。
#
#   BG_TILES = 1  → 不平移（等于老行为，只出一张）
#   BG_TILES = 2  → 两个位置，来回扫 336px（当前）
#   BG_TILES = 3  → 三个位置，来回扫 672px，背景体积再涨 50%
# 取景宽度 = SCREEN_W * BG_TILES。game.ux 的幻灯片列表必须与这里一致。
BG_TILES = 2

# ---- CG：滑动看全图
# 出成完整 16:9（高 480 → 宽 854），放进 <scrollview scroll-direction="horizontal">，
# 用户可以左右拖动看完整画面；剧情里则靠 object-fit:cover 自动裁成满屏。
CG_W = 854

SPRITE_W, SPRITE_H = 143, 380
# 背景每张要出 BG_TILES 块，块数翻倍体积就翻倍，所以调色板从 128 收到 96 留余量。
# 真机上实测过的图片预算是 < 9 MB，别把余量吃干净。
BG_COLORS = 96
SP_COLORS = 128
CG_COLORS = 64          # CG 要出全宽，像素是原来的 2.5 倍，调色板降到 64 压体积
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
            # 取景成 SCREEN_W*BG_TILES 宽的宽幅，再**预切成整屏大小的图块**，
            # 运行时用 <swiper autoplay> 轮播，扫出全景。
            # 纵向偏上取景，因为底部会被对话底板挡住。
            #   第 0 块写到 assets.json 里的 out（索引表只认这一个文件，下标才不会错位）
            #   第 1..N-1 块写成 <name>_r.png / _r2.png，运行时按后缀推出来
            wide = cover(im, SCREEN_W * BG_TILES, SCREEN_H, bias_y=0.42)
            stem, ext = os.path.splitext(dst)
            for t in range(BG_TILES):
                tile = wide.crop((t * SCREEN_W, 0, (t + 1) * SCREEN_W, SCREEN_H))
                if t == 0:
                    save_palette(tile, dst, BG_COLORS, alpha=False)
                else:
                    suffix = "_r" if t == 1 else ("_r%d" % t)
                    save_palette(tile, stem + suffix + ext, BG_COLORS, alpha=False)
        elif kind == "sp":
            im = contain(im, SPRITE_W, SPRITE_H, bg=None, anchor="bottom")
            save_palette(im, dst, SP_COLORS, alpha=True)
        else:  # cg
            # 出成完整 16:9（高 480 → 宽 854），鉴赏页可以左右拖动看全图。
            # 剧情里用 object-fit:cover 显示，组件会自动裁成满屏，不影响正文观感。
            im = cover(im, CG_W, SCREEN_H, bias_y=0.5)
            save_palette(im, dst, CG_COLORS, alpha=False)

        # 体积统计要把**所有**图块都算上。背景有 BG_TILES 块，
        # 只统计 assets.json 里的那一张会把背景体积少报一半。
        n = os.path.getsize(dst)
        if kind == "bg":
            stem, ext = os.path.splitext(dst)
            for t in range(1, BG_TILES):
                suffix = "_r" if t == 1 else ("_r%d" % t)
                fp = stem + suffix + ext
                if os.path.isfile(fp):
                    n += os.path.getsize(fp)
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
