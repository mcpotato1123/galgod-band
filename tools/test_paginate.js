#!/usr/bin/env node
/**
 * 运行时分页测试
 *
 * 分页逻辑已经从构建期搬到 game.ux 的 layout()/paginate() —— 也就是说这段代码
 * 只会在手环上跑。这里把这两个函数的**源码原文**从 .ux 里抠出来直接执行，
 * 而不是另外抄一份，保证测的就是设备上跑的那份。
 *
 * 校验三件事（字号 14~30 全跑一遍）：
 *   1. 没有一行超过当前字号下的每行字数
 *   2. 没有一页超过当前字号下的行数上限
 *   3. 所有页拼回去 == 原文（去掉换行），即没有丢字
 *
 * 用法: node tools/test_paginate.js
 */
const fs = require('fs');
const path = require('path');

const proj = path.resolve(__dirname, '..');
const ux = path.join(proj, 'src', 'pages', 'game', 'game.ux');

function extract(src, name) {
  const re = new RegExp('\\n  ' + name + '\\([^)]*\\) \\{([\\s\\S]*?)\\n  \\},');
  const m = src.match(re);
  if (!m) throw new Error('抠不出 ' + name + '()，检查 game.ux 的写法是否变了');
  return m[1];
}

const src = fs.readFileSync(ux, 'utf8');
const layoutBody = extract(src, 'layout');
const paginateBody = extract(src, 'paginate');

// layout() 里用 this.settings，这里换成传入的参数
const layout = new Function('S', layoutBody.replace(/this\.settings/g, 'S'));
// paginate() 第一行是 const L = this.layout()，去掉，改成由外部传入 L
if (paginateBody.indexOf('const L = this.layout()') < 0) {
  throw new Error('paginate() 里没找到 const L = this.layout()，抽取逻辑需要更新');
}
const paginate = new Function('L', 'text',
  paginateBody.replace('const L = this.layout()', ''));

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
const rows = [];
for (let size = 14; size <= 30; size++) {
  const L = layout({ size: size });
  let lines = 0, pages = 0, overLen = 0, overPage = 0, lost = 0, sample = null;

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
  }

  const ok = (overLen === 0 && overPage === 0 && lost === 0);
  if (!ok) bad++;
  rows.push({ size, cpl: L.cpl, lpp: L.lpp,
    lines, pages, avg: (pages / texts.length).toFixed(2),
    overLen, overPage, lost, ok, sample });

  console.log(
    '  字号 ' + String(size).padStart(2) + '  每行' + String(L.cpl).padStart(2) + '字' +
    '  每页' + L.lpp + '行' +
    '  总行数 ' + String(lines).padStart(6) +
    '  总页数 ' + String(pages).padStart(6) +
    '  页/句 ' + (pages / texts.length).toFixed(2) +
    '  ' + (ok ? '✔' : ('✖ 超行首 ' + overLen + ' 超页 ' + overPage + ' 丢字 ' + lost)));
}

console.log('');
if (bad) {
  const s = rows.find((r) => !r.ok);
  console.error('✖ ' + bad + ' 个字号有问题，例如 ' + s.size + 'px：' + JSON.stringify(s.sample));
  process.exit(1);
}
console.log('✔ 字号 14~30 全部通过：不超行、不超页、不丢字');
