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

// ---- 全景背景：这是一个跨三个文件的三元约束，特别容易改一半
//      gen_assets.py 的 BG_W  −  屏幕宽  ==  game.ux 的 PAN_RANGE  ==  CSS .bgw 的 width
const genAssets = path.join(proj, 'tools', 'gen_assets.py');
if (fs.existsSync(genAssets)) {
  const ga = fs.readFileSync(genAssets, 'utf8');
  const mBgw = ga.match(/^BG_W\s*=\s*(\d+)/m);
  const mScr = ga.match(/^SCREEN_W,\s*SCREEN_H\s*=\s*(\d+),\s*(\d+)/m);
  const mPan = src.match(/const PAN_RANGE\s*=\s*(\d+)/);
  const cssBgw = src.match(/\.bgw \{[^}]*?width:\s*(\d+)px/);
  if (!mBgw || !mScr || !mPan || !cssBgw) {
    console.error('✖ 读不全全景背景的参数：' +
      'gen_assets.BG_W=' + (mBgw && mBgw[1]) +
      ' SCREEN_W=' + (mScr && mScr[1]) +
      ' game.ux PAN_RANGE=' + (mPan && mPan[1]) +
      ' CSS .bgw width=' + (cssBgw && cssBgw[1]));
    process.exit(1);
  }
  const bgw = Number(mBgw[1]);
  const scr = Number(mScr[1]);
  const pan = Number(mPan[1]);
  const cssW = Number(cssBgw[1]);
  const bad = [];
  if (bgw - scr !== pan) bad.push('BG_W(' + bgw + ') - 屏幕宽(' + scr +
    ') = ' + (bgw - scr) + ' ≠ PAN_RANGE(' + pan + ')');
  if (cssW !== bgw) bad.push('CSS .bgw width(' + cssW + ') ≠ BG_W(' + bgw + ')');
  if (pan <= 0) bad.push('PAN_RANGE 必须为正，否则背景不会动');
  if (bad.length) {
    console.error('✖ 全景背景参数不一致：\n    ' + bad.join('\n    '));
    process.exit(1);
  }
  const mPanMs = src.match(/const PAN_MS\s*=\s*(\d+)/);
  const cssDur = src.match(/\.bgw \{[^}]*?transition-duration:\s*(\d+)ms/);
  if (mPanMs && cssDur && Number(mPanMs[1]) !== Number(cssDur[1])) {
    console.error('✖ 平移时长不一致：PAN_MS=' + mPanMs[1] +
      ' 但 CSS transition-duration=' + cssDur[1] + 'ms');
    process.exit(1);
  }
  console.log('全景背景参数 ✔  BG_W=' + bgw + ' 屏幕宽=' + scr +
    ' 平移 ' + pan + 'px  单程 ' + (mPanMs ? mPanMs[1] : '?') + 'ms');
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
