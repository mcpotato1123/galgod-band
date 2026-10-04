# -*- coding: utf-8 -*-
"""
同步后自检：确认目标目录（通常是本地 git 仓库）确实是当前版本

用法:
  python tools/verify_repo.py <要检查的目录> [用于对比的导出目录]

不传第二个参数时，只检查该目录自身的关键标记是否齐全。
传了就逐文件比对（文本忽略行尾符，二进制按原始字节）。
"""
import hashlib
import io
import json
import os
import sys

SKIP_DIRS = {'node_modules', '.git', 'dist', 'build', '__pycache__', '.temp_'}


def read(p):
    try:
        return io.open(p, encoding='utf-8').read()
    except (OSError, UnicodeDecodeError):
        return None


def check_markers(root):
    """检查这个目录是不是当前版本"""
    ok = True

    def need(cond, label, extra=''):
        nonlocal ok
        print('  %-34s %s%s' % (label, 'OK' if cond else '缺失', extra))
        if not cond:
            ok = False

    # manifest
    mf = os.path.join(root, 'src', 'manifest.json')
    if not os.path.isfile(mf):
        print('  !! 找不到 src/manifest.json')
        return False
    m = json.loads(read(mf))
    ver, vc = m.get('versionName'), m.get('versionCode')
    print('  %-34s %s / vc%s' % ('版本号', ver, vc))
    pages = m.get('router', {}).get('pages', {})
    for p in ('pages/index', 'pages/game', 'pages/saves', 'pages/chapters',
              'pages/cg', 'pages/settings', 'pages/about'):
        need(p in pages, '路由 ' + p)

    # 关于页
    ab = read(os.path.join(root, 'src', 'pages', 'about', 'about.ux'))
    if ab is None:
        need(False, 'src/pages/about/about.ux')
    else:
        need("APP_VER = '" + str(ver) + "'" in ab,
             "about.ux APP_VER 与 manifest 一致")
        for k in ('故事梗概', '版权信息', 'MIT 协议', '诺提拉观察所',
                  'tapTitle', 'unlockAfter', 'unlockCg'):
            need(k in ab, 'about.ux 含 ' + k)

    # 协议文件
    for f in ('LICENSE', 'NOTICE.md'):
        need(os.path.isfile(os.path.join(root, f)), f)
    lic = read(os.path.join(root, 'LICENSE')) or ''
    need('MIT License' in lic, 'LICENSE 是 MIT')

    # 正文页几何（2.1 起的版面）
    g = read(os.path.join(root, 'src', 'pages', 'game', 'game.ux')) or ''
    need('NAME_TOP = 292' in g, 'game.ux 说话人 292')
    need('PANEL_TOP = 330' in g, 'game.ux 底板 330')

    # 公共逻辑
    r = read(os.path.join(root, 'src', 'common', 'reader.js')) or ''
    for k in ('export function wrapText', 'export function paginateText',
              'loadCleared', 'markCleared'):
        need(k in r, 'reader.js 有 ' + k.split()[-1])

    # 说话人修复：正文里不应再出现角色名开头的句子
    fixed = broken = 0
    story = os.path.join(root, 'src', 'common', 'story')
    if os.path.isdir(story):
        for f in sorted(os.listdir(story)):
            if not f.startswith('chunk-'):
                continue
            try:
                nodes = json.loads(read(os.path.join(story, f)))
            except (ValueError, TypeError):
                continue
            for n in nodes:
                if n.get('t') != 's':
                    continue
                if (n.get('n') or '') in ('同学A', '同学B', '班主任', '???',
                                          '远处的声音', '众人'):
                    fixed += 1
                if (n.get('x') or '').startswith(('同学A', '同学B', '班主任',
                                                  '远处的声音')):
                    broken += 1
    need(fixed == 61 and broken == 0,
         '剧本说话人 正常%d / 拼进正文%d (期望 61/0)' % (fixed, broken))

    # README
    rd = read(os.path.join(root, 'README.md')) or ''
    for k in (str(ver) + '.rpk', '关于页与彩蛋', 'MIT 协议',
              '诺提拉观察所', 'Astrobox', 'a3436370081@163.com'):
        need(k in rd, 'README 含 ' + k)
    for bad in ('CHARS_PER_LINE', 'mcpotato1123'):
        need(bad not in rd, 'README 无过时内容 ' + bad)

    return ok


def compare(a, b):
    """逐文件比对两个目录"""
    def snap(root):
        out = {}
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for f in fn:
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, root)
                try:
                    raw = open(p, 'rb').read()
                except OSError:
                    continue
                try:
                    out[rel] = ('t', raw.decode('utf-8').replace('\r\n', '\n'))
                except UnicodeDecodeError:
                    out[rel] = ('b', hashlib.md5(raw).hexdigest())
        return out

    x, y = snap(a), snap(b)
    only_a = sorted(set(x) - set(y))
    only_y = sorted(set(y) - set(x))
    diff = sorted(k for k in set(x) & set(y) if x[k] != y[k])
    print()
    print('  对比 %s' % a)
    print('    仅导出有 %d 个: %s' % (len(only_a), ', '.join(only_a[:6]) or '-'))
    print('    仅目标有 %d 个: %s' % (len(only_y), ', '.join(only_y[:6]) or '-'))
    print('    内容不同 %d 个: %s' % (len(diff), ', '.join(diff[:10]) or '-'))
    return not diff


def main(argv):
    if not argv:
        sys.exit(__doc__)
    root = os.path.abspath(argv[0])
    print('检查目录: %s' % root)
    print()
    ok = check_markers(root)
    if len(argv) > 1:
        ok = compare(os.path.abspath(argv[1]), root) and ok
    print()
    print('  自检结果: %s' % ('全部通过' if ok else '有不一致'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
