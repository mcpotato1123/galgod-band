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

# ---- 背景：全景
# 出一张宽幅（BG_W 宽），运行时用**定时器逐帧推进 left**做平移。
#
# 为什么不用更"聪明"的办法：真机上试过两条，都失败
#   1) 宽图 + left + CSS transition → 画面中间出竖向接缝
#      （接缝位置正好等于平移距离，疑似过渡中间态被渲染成两个位置叠加）
#   2) 预切整屏图块 + <swiper autoplay> → 幻灯片不贴合（中间留黑带）、画面被放大
# left 本身是能正确渲染的（方案 1 里画面位置是对的，坏的只是 transition 补间），
# 所以现在改成自己按固定间隔小步推进 left，完全不碰 transition。
#
#   BG_W = SCREEN_W  → 不平移
#   BG_W = 672       → 可平移 336px（当前，2 屏宽）
BG_W = 672

# ---- CG：拖动看全图
# 出一张完整 16:9 的宽图（高 480 → 宽 854），运行时靠 touchmove 连续拖左右看全图。
#
# 为什么不再预切多张：切块只能「翻页」，一格一格硬跳，观感生硬。
# Vela 的 commonEvents 里有 touchstart/touchmove/touchend，能拿到坐标，
# 所以改成连续拖动 —— 和背景那边「不许用 transition」的教训不冲突，
# 因为这里改的是 left（能正确渲染），不是补间。
CG_W = 854

SPRITE_W, SPRITE_H = 143, 380
# 背景要出 672 宽的宽幅、CG 要出 3 张，体积都涨，调色板相应收一点留余量。
# 真机上实测过的图片预算是 < 9 MB —— 别贴着上限跑，留出以后加素材的空间。
BG_COLORS = 80
SP_COLORS = 128
CG_COLORS = 56
THUMB_W, THUMB_H = 96, 54      # CG 鉴赏缩略图（16:9）
THUMB_COLORS = 64

# 主页真正露出来的画面区高度：下面 240 被 index.ux 的按钮面板盖住。
# 必须与 index.ux 里 .panel 的 top 一致（npm run test 会核对）。
HOME_TOP_H = 240


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

    # 先清空 img/ 再生成。
    # 派生文件名是按后缀拼的（CG 的 _l/_r 等），改了命名规则之后旧文件不会被覆盖，
    # 会**留在包里**白白占体积、还可能被误用到。踩过一次：背景从「2 块图块」
    # 改回「1 张宽图」后，旧的 38 张图块还躺在 img/b 里，体积虚高 1.6 MB。
    # home.png / icon.png 在 common/ 下、不在 img/，不受影响。
    if os.path.isdir(out_root):
        import shutil as _shutil
        removed = 0
        for d in os.listdir(out_root):
            p = os.path.join(out_root, d)
            if os.path.isdir(p):
                removed += len(os.listdir(p))
                _shutil.rmtree(p)
        print("  已清空 img/（删掉 %d 个旧文件，避免改名后的残留留在包里）" % removed)

    for it in assets:
        src = os.path.join(raw_dir, it["src"].replace("/", os.sep))
        if not os.path.isfile(src):
            print("  !! 缺少源图: %s" % src)
            continue
        dst = os.path.join(proj, "src", "common", it["out"].replace("/common/", "").replace("/", os.sep))
        im = Image.open(src)
        kind = it["kind"]

        if kind == "bg":
            # 一张宽幅，运行时靠定时器推进 left 平移。
            # 纵向偏上取景，因为底部会被对话底板挡住。
            im = cover(im, BG_W, SCREEN_H, bias_y=0.42)
            save_palette(im, dst, BG_COLORS, alpha=False)
        elif kind == "sp":
            im = contain(im, SPRITE_W, SPRITE_H, bg=None, anchor="bottom")
            save_palette(im, dst, SP_COLORS, alpha=True)
        else:  # cg
            # 一张完整 16:9 宽图。剧情正文用它 + object-fit:cover 自动居中裁成满屏，
            # 鉴赏页则靠 touchmove 连续拖动左右看全图 —— 一份素材两处用。
            im = cover(im, CG_W, SCREEN_H, bias_y=0.5)
            save_palette(im, dst, CG_COLORS, alpha=False)

        # 现在每张源图只对应一个输出文件（CG 不再预切），直接取大小即可
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

    # 主页画
    # 用户指定的构图就是原图按 **3:2 居中裁切**（和 Steam 头图一致），
    # 也就是「logo 锁排在左、女孩在右」那张。
    #
    # 关键：主页真正露出来的画面区只有**上面 336x240**（下面 240 被按钮面板盖住），
    # 而 3:2 裁切是 1.5:1、336x240 是 1.4:1，两者几乎一致 ——
    # 所以整张构图能几乎完整地铺进去，两边都不丢。
    title_src = os.path.join(raw_dir, "images", "cg", "main_screen.avif")
    if os.path.isfile(title_src):
        art = Image.open(title_src).convert("RGB")
        aw, ah = art.size                          # 1920x1080
        cw = int(round(ah * 1.5))                  # 1620，3:2
        x0 = (aw - cw) // 2
        art = art.crop((x0, 0, x0 + cw, ah))
        # 按**宽度**完整铺下（不做 cover 裁切）：3:2 的图铺进 336 宽正好是 336x224，
        # 比画面区 240 只差 16px，用渐变补掉就行。
        # 用 cover 会裁掉两侧 —— logo 会被切（试过，用户要的正是 logo 在左的完整构图）。
        fit_h = int(round(SCREEN_W * ah / float(cw)))
        top = art.resize((SCREEN_W, fit_h), Image.LANCZOS)

        canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (13, 9, 16))
        canvas.paste(top, (0, 0))
        # 画面区下面接一段渐变收进底色：
        # 面板是 rgba(21,15,25,0.94)，留一点点透出来的话不能是硬边。
        edge = top.crop((0, fit_h - 1, SCREEN_W, fit_h))
        dark = Image.new("RGB", (SCREEN_W, 1), (13, 9, 16))
        span = float(SCREEN_H - fit_h)
        for y in range(fit_h, SCREEN_H):
            t = min(1.0, ((y - fit_h) / span) * 1.5)
            canvas.paste(Image.blend(edge, dark, t), (0, y))
        save_palette(canvas, os.path.join(common, "home.png"), 96, alpha=False)
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
