#!/usr/bin/env node
/**
 * 运行时分页测试
 *
 * 分页逻辑已经从构建期搬到 game.ux 的 layout()/paginate() —— 也就是说这段代码
 * 只会在手环上跑。这里把这两个函数的**源码原文**从 .ux 里抠出来直接执行，
 * 而不是另外抄一份，保证测的就是设备上跑的那份。
 * 它们依赖的几何常量（TEXT_TOP / TEXT_BOX_H 等）也一并从 game.ux 里抠出来注入，
 * 所以改了版面数值这个测试会跟着变，不会两边失配。
 *
 * 校验（字号 14~30 全跑一遍）：
 *   1. 没有一行超过当前字号下的每行字数
 *   2. 没有一页超过当前字号下的行数上限
 *   3. 所有页拼回去 == 原文（去掉换行），即没有丢字
 *   4. 正文不会压到 .more 的「继续」提示
 *
 * 用法: node tools/test_paginate.js
 */
const fs = require('fs');
const path = require('path');

const proj = path.resolve(__dirname, '..');
const ux = path.join(proj, 'src', 'pages', 'game', 'game.ux');
const readerJs = path.join(proj, 'src', 'common', 'reader.js');

function extract(src, name) {
  const re = new RegExp('\\n  ' + name + '\\([^)]*\\) \\{([\\s\\S]*?)\\n  \\},');
  const m = src.match(re);
  if (!m) throw new Error('抠不出 ' + name + '()，检查写法是否变了');
  return m[1];
}

// 从 reader.js 里抠出换行/分页函数（export function xxx(...) { ... }）
function extractExport(src, name) {
  const re = new RegExp('export function ' + name + '\\(([^)]*)\\) \\{([\\s\\S]*?)\\n\\}');
  const m = src.match(re);
  if (!m) throw new Error('reader.js 里抠不出 ' + name + '()');
  return { args: m[1].split(',').map((s) => s.trim()).filter(Boolean), body: m[2] };
}

const src = fs.readFileSync(ux, 'utf8');
const readerSrc = fs.readFileSync(readerJs, 'utf8');

// ---- 从 game.ux 里抠出正文区几何常量
const NAMES = ['PANEL_TOP', 'PANEL_H', 'NAME_TOP', 'TEXT_TOP',
               'TEXT_BOX_W', 'TEXT_PAD', 'TEXT_BOX_H', 'MAX_LINES'];
const geom = {};
for (const n of NAMES) {
  const m = src.match(new RegExp('const ' + n + '\\s*=\\s*(\\d+)'));
  if (!m) throw new Error('game.ux 里找不到常量 ' + n);
  geom[n] = Number(m[1]);
}
// .more（继续提示）的位置也从 CSS 里读，避免测试和样式脱节
const moreM = src.match(/\.more \{[^}]*top:\s*(\d+)px/);
if (!moreM) throw new Error('读不出 .more 的 top');
geom.MORE_TOP = Number(moreM[1]);

const layoutBody = extract(src, 'layout');

// "不许再出现"这类检查必须**先剥掉注释**再看，否则注释里提到 swiper / scrollview
// 就会误报（那些文件里恰好写了大段"为什么不用它"的说明）。
// 剥 // 时要避开 https:// 里的双斜杠。
// 定义在顶层，因为下面好几个检查块都要用。
const stripComments = (t) => t
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/(^|[^:])\/\/[^\n]*/g, '$1 ');

// 真正的换行 + 分页算法在 reader.js，正文页和关于页共用
const wrap = extractExport(readerSrc, 'wrapText');
const pag = extractExport(readerSrc, 'paginateText');
const BREAK = readerSrc.match(/const BREAK_AFTER = '([^']*)'/);
if (!BREAK) throw new Error('reader.js 里找不到 BREAK_AFTER');

// layout() 里用 this.settings，这里换成传入的参数
const layoutFn = new Function(...NAMES, 'S', layoutBody.replace(/this\.settings/g, 'S'));

// 把 reader.js 里的两个函数按原名拼出来再执行
const fnSrc = (e, name) =>
  'function ' + name + '(' + e.args.join(', ') + ') {' + e.body + '\n}';
const pagFn = new Function(
  'const BREAK_AFTER = ' + JSON.stringify(BREAK[1]) + ';\n' +
  fnSrc(wrap, 'wrapText') + '\n' +
  fnSrc(pag, 'paginateText') + '\n' +
  'return paginateText;'
)();

const GV = NAMES.map((n) => geom[n]);
const layout = (size) => layoutFn(...GV, { size });
const paginate = (L, t) => pagFn(t, L.cpl, L.lpp);

// 顺带核对：CSS 里的底板/说话人位置和常量是否一致
// 注意用惰性匹配 —— 贪心会取到最后一个 top:，加了 padding-top 之后就会读错
const cssNum = (cls, prop) => {
  const m = src.match(new RegExp('\\.' + cls + ' \\{[^}]*?' + prop + ':\\s*(\\d+)px'));
  return m ? Number(m[1]) : null;
};
const cssPanel = cssNum('panel', 'top');
const cssPanelH = cssNum('panel', 'height');
const cssName = cssNum('name', 'top');
if (cssPanel !== geom.PANEL_TOP || cssPanelH !== geom.PANEL_H || cssName !== geom.NAME_TOP) {
  console.error('✖ CSS 与 JS 常量不一致：' +
    'CSS .panel top=' + cssPanel + ' height=' + cssPanelH + ' .name top=' + cssName +
    ' / JS PANEL_TOP=' + geom.PANEL_TOP + ' PANEL_H=' + geom.PANEL_H +
    ' NAME_TOP=' + geom.NAME_TOP);
  process.exit(1);
}
console.log('几何常量与 CSS 一致 ✔  ' +
  NAMES.map((n) => n + '=' + geom[n]).join(' ') + ' MORE_TOP=' + geom.MORE_TOP);

// ---- 全景背景 / CG 全图：几处跨文件约束，特别容易只改一半
//      这两个功能一路上踩了三次坑（left+transition 出接缝、swiper 幻灯片不贴合、
//      scrollview 拖不动），所以把每个"不许再出现"的写法都做成断言。
const genAssets = path.join(proj, 'tools', 'gen_assets.py');
if (fs.existsSync(genAssets)) {
  const ga = fs.readFileSync(genAssets, 'utf8');
  const num = (re, s) => { const m = s.match(re); return m ? Number(m[1]) : null; };
  const bad = [];

  // stripComments 定义在文件顶层，这里直接用
  const code = stripComments(src);

  const scrW = num(/^SCREEN_W,\s*SCREEN_H\s*=\s*(\d+)/m, ga);
  const scrH = num(/^SCREEN_W,\s*SCREEN_H\s*=\s*\d+,\s*(\d+)/m, ga);
  const bgW = num(/^BG_W\s*=\s*(\d+)/m, ga);
  const cgW = num(/^CG_W\s*=\s*(\d+)/m, ga);

  if (scrW === null || scrH === null || bgW === null || cgW === null || false) {
    console.error('✖ gen_assets.py 里读不到 SCREEN_W / SCREEN_H / BG_W / CG_W / CG_TILES');
    process.exit(1);
  }

  // ---- 背景是「一张宽图 + 定时器推进 left」，不许再出现前世的各种写法
  const gameBgW = num(/const BG_W\s*=\s*(\d+)/, code);
  const gameRange = num(/const BG_PAN_RANGE\s*=\s*BG_W\s*-\s*(\d+)/, code);
  const cssBgW = num(/\.bgwide \{[^}]*?width:\s*(\d+)px/, code);
  if (gameBgW !== bgW) {
    bad.push('game.ux 的 BG_W(' + gameBgW + ') ≠ gen_assets.BG_W(' + bgW +
      ')：素材宽度对不上，平移会露边或走不满');
  }
  if (cssBgW !== bgW) {
    bad.push('CSS .bgwide width(' + cssBgW + ') ≠ BG_W(' + bgW + ')');
  }
  if (gameRange !== scrW) {
    bad.push('game.ux 的 BG_PAN_RANGE 是用 BG_W - ' + gameRange + ' 算的，' +
      '应该减屏幕宽 ' + scrW);
  }
  if (!/const BG_STEP_PX\s*=\s*\d+/.test(code) || !/const BG_TICK_MS\s*=\s*\d+/.test(code)) {
    bad.push('game.ux 缺少 BG_STEP_PX / BG_TICK_MS（逐帧推进的步长与间隔）');
  }
  // 真机上踩过：给宽图加 transition 会在画面中间渲染出竖向接缝（位置等于平移距离）
  const bgwideBlock = (code.match(/\.bgwide \{[^}]*\}/) || [''])[0];
  if (/transition|animation/.test(bgwideBlock)) {
    bad.push('CSS .bgwide 上出现了 transition/animation：' +
      '真机实测会给宽图渲染出接缝，背景必须靠定时器逐帧推进 left');
  }
  if (/<swiper/.test(code) || /\.bgsw\s*\{/.test(code) || /\.bgslide\s*\{/.test(code)) {
    bad.push('game.ux 里还有 swiper 背景的痕迹：真机实测幻灯片不贴合（中间留黑带）' +
      '且画面被放大');
  }
  if (/buildBgFrames|startBgSwap|BG_TILE_COUNT/.test(code)) {
    bad.push('game.ux 里还有「轮换背景 src」那版的残留代码');
  }
  if (!/startBgPan/.test(code) || !/bgPanTick/.test(code)) {
    bad.push('game.ux 里找不到 startBgPan / bgPanTick（背景平移的核心）');
  }
  // 真机上踩过：背景图 672 宽而页面 336 宽，页面又没 overflow:hidden，
  // 运行时就把它当成横向可滚动区域，玩家一拖整个背景就被拖走了。
  {
    const pageBlock = (code.match(/\.page \{[^}]*\}/) || [''])[0];
    if (!/overflow:\s*hidden/.test(pageBlock)) {
      bad.push('game.ux 的 .page 没有 overflow:hidden：背景图比屏幕宽，' +
        '运行时会把它当作横向可滚动内容，玩家一拖就把背景拖走');
    }
  }

  // ---- CG 是「一张宽图 + touchmove 连续拖动」，不许再退回预切翻页 / scrollview
  if (cgW <= scrW) {
    bad.push('CG_W(' + cgW + ') 必须大于屏幕宽(' + scrW + ')，否则没有可拖的横向内容');
  }
  const cgPath = path.join(proj, 'src', 'pages', 'cg', 'cg.ux');
  if (fs.existsSync(cgPath)) {
    const cgCode = stripComments(fs.readFileSync(cgPath, 'utf8'));
    if (/scrollview/.test(cgCode)) {
      bad.push('cg.ux 里还在用 scrollview：真机实测它的拖动完全不响应');
    }
    if (!/ontouchmove="onCgTouchMove"/.test(cgCode)) {
      bad.push('cg.ux 的大图没有挂 ontouchmove（连续拖动失效，会退化成硬跳）');
    }
    if (!/ontouchstart="onCgTouchStart"/.test(cgCode)) {
      bad.push('cg.ux 缺少 ontouchstart（拖动起点取不到，拖了也不动）');
    }
    // 兜底手势必须留着：touchmove 万一在别的固件上不派发，还有路可走
    if (!/onswipe="onPanSwipe"/.test(cgCode)) {
      bad.push('cg.ux 缺少 onswipe 兜底（touchmove 不灵时就没法看全图了）');
    }
    if (!/onclick="panPrev"/.test(cgCode) || !/onclick="panNext"/.test(cgCode)) {
      bad.push('cg.ux 缺少点击兜底热区（panPrev / panNext）');
    }
    const rootTag = (cgCode.match(/<div class="page"[^>]*>/) || [''])[0];
    if (/onswipe/.test(rootTag)) {
      bad.push('cg.ux 根节点挂了 onswipe（' + rootTag.trim() + '）：会把滑动手势吃掉');
    }
    const bigBlock = (cgCode.match(/\.big \{[^}]*\}/) || [''])[0];
    const bigW = num(/width:\s*(\d+)px/, bigBlock);
    if (bigW !== cgW) {
      bad.push('cg.ux 的 .big width(' + bigW + ') ≠ gen_assets.CG_W(' + cgW + ')');
    }
    // 真机上踩过：.big 不写 object-fit 时 Vela 的 <image> 会按**原始尺寸**画，
    // 结果只占屏幕左边一块、右边全黑。
    if (!/object-fit/.test(bigBlock)) {
      bad.push('CSS .big 没有写 object-fit：Vela 的 <image> 默认不缩放，' +
        '会按原始尺寸绘制，画面只占左侧一块、其余全黑');
    }
    if (!/overflow:\s*hidden/.test(cgCode)) {
      bad.push('cg.ux 的查看器没有 overflow:hidden，比屏幕宽的图不会被裁住');
    }
    // 拖动增益够不够：分母是**手指的实际可用行程**，不是屏宽。
    // 从屏幕中间起手最多只能挪到边缘，也就是 scrW/2。
    // 真机上踩过：按"整屏 336"算出增益 1.8，实际一次只能拖 58%，
    // 表现为「只能拖一半」。
    const gainM = cgCode.match(/const CG_DRAG_GAIN\s*=\s*([\d.]+)/);
    const gain = gainM ? Number(gainM[1]) : null;
    if (gain === null) {
      bad.push('cg.ux 里找不到 CG_DRAG_GAIN（拖动放大倍数）');
    } else {
      const travel = scrW / 2;                 // 从屏幕中间起手的可用行程
      const reach = gain * travel;
      const range = cgW - scrW;
      if (reach < range) {
        bad.push('CG_DRAG_GAIN=' + gain + ' 不够：从屏幕中间起手手指只能走 ' +
          travel + 'px，最多拖动 ' + Math.round(reach) + 'px，' +
          '小于可拖范围 ' + range + 'px（只有 ' +
          Math.round(reach * 100 / range) + '%）—— 真机上会表现为「只能拖一半」。' +
          '至少要 ' + Math.ceil(range / travel * 10) / 10);
      }
    }
    // 一张 CG 就是一张宽图，靠拖动看两侧；不要再退回「切成多张翻页」那版。
    // 分块翻页是一次跳一整块，观感生硬，而且每张 CG 要出 3 个文件、体积也涨。
    if (/_l'|_r'|"_l"|"_r"|buildPanTiles/.test(cgCode)) {
      bad.push('cg.ux 里出现了 _l / _r 分块的痕迹：' +
        'CG 应该是一张宽图靠拖动看，不要切块翻页');
    }
  }

  if (bad.length) {
    console.error('✖ 全景背景 / CG 全图 参数不一致：\n    ' + bad.join('\n    '));
    process.exit(1);
  }
  console.log('全景背景 ✔  BG_W=' + bgW + ' 平移 ' + (bgW - scrW) + 'px（定时器逐帧推进 left）；CG 全图 ✔ ' + cgW + 'x' + scrH + ' 宽图（touchmove 连续拖动）');

  // ---- 派生文件名是纯字符串拼接（运行时不查表），必须齐全且不能撞名
  const assetsPath = path.join(proj, 'src', 'common', 'assets.js');
  if (fs.existsSync(assetsPath)) {
    const ap = fs.readFileSync(assetsPath, 'utf8');
    const cssDir = path.join(proj, 'src', 'common');
    const toFs = (p) => path.join(cssDir, p.replace('/common/', '').split('/').join(path.sep));

    const check = (list, suffixes, label) => {
      const names = list.map((p) => path.basename(p).replace(/\.[^.]+$/, ''));
      const clash = [];
      for (const suf of suffixes) {
        for (const n of names) {
          if (n.endsWith(suf)) clash.push(n + ' 以 ' + suf + ' 结尾');
        }
      }
      if (clash.length) {
        console.error('✖ ' + label + '名与派生后缀冲突（会静默覆盖别的文件）：\n    ' +
          clash.join('\n    '));
        process.exit(1);
      }
      const missing = [];
      for (const p of list) {
        for (const suf of suffixes) {
          const f = toFs(p).replace(/\.[^.]+$/, '') + suf + path.extname(p);
          if (!fs.existsSync(f)) missing.push(path.basename(f));
        }
      }
      if (missing.length) {
        console.error('✖ ' + label + '派生文件缺失 ' + missing.length + ' 个' +
          '（运行时会出现空白画面）：\n    ' + missing.slice(0, 8).join('\n    '));
        process.exit(1);
      }
      return names.length;
    };

    const cgs = (ap.match(/"[^"]*\/c\/[^"]+"/g) || []).map((x) => x.slice(1, -1));
    const nCg = check(cgs, [], 'CG');
    console.log('CG 全图 ✔  ' + nCg + ' 组，文件全部存在且无重名');

    // 背景现在是「一张宽图」，索引表里那张就是最终产物，没有派生文件要查
    const bgs = (ap.match(/"[^"]*\/b\/[^"]+"/g) || []).map((x) => x.slice(1, -1));
    const bgMissing = bgs.filter((p) => !fs.existsSync(toFs(p)));
    if (bgMissing.length) {
      console.error('✖ 背景文件缺失 ' + bgMissing.length + ' 个:\n    ' +
        bgMissing.slice(0, 6).join('\n    '));
      process.exit(1);
    }
    console.log('背景素材 ✔  ' + bgs.length + ' 张宽图全部存在');
  }
}

// ---- 所有页面：给定了宽高的 <image> 必须写 object-fit
//      真机上踩过：Vela 的 <image> 默认**不缩放**，按图片原始像素尺寸绘制，
//      没写 object-fit 的图会只占一块、其余留黑（CG 页出现过）。
{
  const pagesDir = path.join(proj, 'src', 'pages');
  const offenders = [];
  for (const pg of fs.readdirSync(pagesDir)) {
    const f = path.join(pagesDir, pg, pg + '.ux');
    if (!fs.existsSync(f)) continue;
    const code2 = stripComments(fs.readFileSync(f, 'utf8'));
    const blocks = {};
    let mm;
    const reBlock = /\.([a-zA-Z0-9_-]+)\s*\{([^}]*)\}/g;
    while ((mm = reBlock.exec(code2))) blocks[mm[1]] = mm[2];
    const reTag = /<image\b[^>]*>/g;
    while ((mm = reTag.exec(code2))) {
      const cm = /class="([^"]+)"/.exec(mm[0]);
      if (!cm) continue;
      for (const cls of cm[1].split(/\s+/)) {
        const body = blocks[cls] || '';
        if (!/width:\s*\d+px/.test(body) || !/height:\s*\d+px/.test(body)) continue;
        if (!/object-fit/.test(body)) offenders.push(pg + ' .' + cls);
      }
    }
  }
  if (offenders.length) {
    console.error('✖ 这些 <image> 给了宽高却没写 object-fit（真机上会按原始尺寸绘制）：\n    ' +
      offenders.join('\n    '));
    process.exit(1);
  }
  console.log('图片 object-fit ✔  所有给定宽高的 <image> 都写了');
}

// ---- 每个设置项都要登记「由哪个页面控制」，并核对那个页面真的引用了它
//      加设置项时最容易漏的就是这一步：reader.js 加了键、game.ux 读了它，
//      但没有任何界面能改 —— 用户永远碰不到，而且构建和运行都不报错。
{
  // 新加设置项时必须在这里登记，否则下面第一条就会报错。
  const CONTROL_SITE = {
    size: 'settings',
    speed: 'settings',
    autoMs: 'settings',
    keepOn: 'settings',
    longpress: 'settings',
    // 快进**故意**不放在设置页：阅读时随手在菜单里开关比翻到设置页方便。
    fast: 'game',
  };
  const SITE_FILE = {
    settings: path.join(proj, 'src', 'pages', 'settings', 'settings.ux'),
    game: path.join(proj, 'src', 'pages', 'game', 'game.ux'),
  };

  const rj = fs.readFileSync(path.join(proj, 'src', 'common', 'reader.js'), 'utf8');
  const blk = (rj.match(/DEFAULT_SETTINGS\s*=\s*\{([\s\S]*?)\}/) || [])[1] || '';
  const keys = [];
  let km;
  const reKey = /(\w+)\s*:/g;
  while ((km = reKey.exec(blk))) keys.push(km[1]);

  if (keys.length) {
    const unreg = keys.filter((k) => !CONTROL_SITE[k]);
    if (unreg.length) {
      console.error('✖ 这些设置项没有登记控制入口（tests 里的 CONTROL_SITE）：\n    ' +
        unreg.join('\n    ') +
        '\n    reader.js 的 DEFAULT_SETTINGS 里加了键，但没告诉测试由哪个页面控制它，' +
        '\n    很可能界面里也就忘了加 —— 用户改不到，而且不会报错。');
      process.exit(1);
    }
    const orphan = Object.keys(CONTROL_SITE).filter((k) => keys.indexOf(k) < 0);
    if (orphan.length) {
      console.error('✖ CONTROL_SITE 里登记了 DEFAULT_SETTINGS 里没有的键：\n    ' +
        orphan.join('\n    '));
      process.exit(1);
    }
    const bad = [];
    for (const k of keys) {
      const f = SITE_FILE[CONTROL_SITE[k]];
      const code3 = stripComments(fs.readFileSync(f, 'utf8'));
      if (!new RegExp('\\b' + k + '\\b').test(code3)) {
        bad.push(k + ' 登记在 ' + CONTROL_SITE[k] + '，但那个文件里找不到它');
      }
    }
    if (bad.length) {
      console.error('✖ 设置项与登记的入口对不上：\n    ' + bad.join('\n    '));
      process.exit(1);
    }
    console.log('设置项入口 ✔  ' + keys.length + ' 项：' +
      keys.map((k) => k + '(' + CONTROL_SITE[k] + ')').join(' '));
  }
}

// ---- 关于页：它把每行字数写成常量 CPL，也要核对「CPL × 字号 ≤ 行宽」
const aboutPath = path.join(proj, 'src', 'pages', 'about', 'about.ux');
if (fs.existsSync(aboutPath)) {
  const about = fs.readFileSync(aboutPath, 'utf8');
  const cplM = about.match(/const CPL\s*=\s*(\d+)/);
  const rpM = about.match(/\.r-p \{[^}]*?font-size:\s*(\d+)px[^}]*?width:\s*(\d+)px/);
  const rpM2 = about.match(/\.r-p \{[^}]*?width:\s*(\d+)px[^}]*?font-size:\s*(\d+)px/);
  const fontPx = rpM ? Number(rpM[1]) : (rpM2 ? Number(rpM2[2]) : null);
  const lineW = rpM ? Number(rpM[2]) : (rpM2 ? Number(rpM2[1]) : null);
  if (!cplM || !fontPx || !lineW) {
    console.error('✖ 关于页读不出 CPL 或 .r-p 的 width/font-size');
    process.exit(1);
  }
  const cpl = Number(cplM[1]);
  const need = cpl * fontPx;
  if (need > lineW) {
    console.error('✖ 关于页每行字数超宽：CPL ' + cpl + ' × 字号 ' + fontPx +
      ' = ' + need + 'px > .r-p 宽 ' + lineW + 'px');
    process.exit(1);
  }
  console.log('关于页排版 ✔  CPL=' + cpl + ' × 字号 ' + fontPx + ' = ' + need +
    'px ≤ 行宽 ' + lineW + 'px');
}

// ---------------------------------------------------------------- 载入剧本
const storyDir = path.join(proj, 'src', 'common', 'story');
const index = JSON.parse(fs.readFileSync(path.join(storyDir, 'index.txt'), 'utf8'));
let nodes = [];
for (const c of index.chunks.slice().sort((a, b) => a.start - b.start)) {
  const f = path.join(proj, 'src', 'common', c.file.replace('/common/', ''));
  nodes = nodes.concat(JSON.parse(fs.readFileSync(f, 'utf8')));
}

const texts = [];
for (const n of nodes) {
  if (n.t === 's' && typeof n.x === 'string' && n.x.length) texts.push(n.x);
}
console.log('剧本节点 ' + nodes.length + '，含台词 ' + texts.length + ' 句');

// ---------------------------------------------------------------- 逐个字号检查
let bad = 0;
for (let size = 14; size <= 30; size++) {
  const L = layout(size);
  let lines = 0, pages = 0, overLen = 0, overPage = 0, lost = 0, maxBottom = 0;
  let sample = null;

  for (const t of texts) {
    const ps = paginate(L, t);
    pages += ps.length;
    let all = '';
    for (const pg of ps) {
      if (pg.length > L.lpp) { overPage++; if (!sample) sample = t; }
      for (const ln of pg) {
        lines++;
        all += ln;
        if (ln.length > L.cpl) { overLen++; if (!sample) sample = t; }
      }
    }
    if (all !== t.replace(/\n/g, '')) { lost++; if (!sample) sample = t; }
    const bottom = geom.TEXT_TOP + ps[0].length * L.lineH;
    if (bottom > maxBottom) maxBottom = bottom;
  }

  const overMore = maxBottom > geom.MORE_TOP;
  const ok = (overLen === 0 && overPage === 0 && lost === 0 && !overMore);
  if (!ok) bad++;

  console.log(
    '  字号 ' + String(size).padStart(2) +
    '  每行' + String(L.cpl).padStart(2) + '字' +
    '  每页' + L.lpp + '行' +
    '  总行数 ' + String(lines).padStart(6) +
    '  总页数 ' + String(pages).padStart(6) +
    '  末行底 ' + String(maxBottom).padStart(3) +
    '  ' + (ok ? '✔' : ('✖ 超行 ' + overLen + ' 超页 ' + overPage +
                        ' 丢字 ' + lost + ' 压▼ ' + (overMore ? '是' : '否'))));
}

console.log('');
if (bad) {
  console.error('✖ ' + bad + ' 个字号有问题');
  process.exit(1);
}
console.log('✔ 字号 14~30 全部通过：不超行、不超页、不丢字、不压 ▼');
