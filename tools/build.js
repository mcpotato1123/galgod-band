#!/usr/bin/env node
/**
 * 构建包装脚本
 *
 * aiot-toolkit 会先把工程复制到同级目录 `../.temp_<工程名>` 再编译，收尾时用 rimraf
 * 删这个临时工程；而临时工程里的 node_modules 是软链接（junction），Windows 上
 * rimraf 删它常常报 EPERM，导致构建虽然成功、退出码却是 1，还留下垃圾目录。
 *
 * 这里在构建前后各清理一次，并对产物做完整性校验。
 *
 *   node tools/build.js           # debug 包
 *   node tools/build.js release   # release 包（需要 sign/ 下的证书）
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const proj = path.resolve(__dirname, '..');
const name = path.basename(proj);
const temp = path.resolve(proj, '..', '.temp_' + name);
const mode = process.argv[2] === 'release' ? 'release' : 'build';

function rmTemp() {
  if (!fs.existsSync(temp)) return;
  if (process.platform === 'win32') {
    spawnSync('cmd', ['/c', 'rmdir', '/s', '/q', temp], { stdio: 'ignore' });
  } else {
    spawnSync('rm', ['-rf', temp], { stdio: 'ignore' });
  }
}

function fail(msg) {
  console.error('\n✖ ' + msg);
  process.exit(1);
}

// ---------------------------------------------------------------- 构建前静态检查
// 这里挡的是「编译器不报错、真机运行时才抛错」的两个 Vela 陷阱：
//   1. data 与 public/protected/private 同时存在 → 运行时直接抛错，页面 VM 创建失败，
//      表现是「点按钮完全没反应」
//   2. export default 顶层的字面量属性（story/chunkCache 之类）不保证会挂到页面实例上，
//      若在赋值前就被读取，会 undefined[...] 抛错
function preflight() {
  const pagesDir = path.join(proj, 'src', 'pages');
  const problems = [];
  const warns = [];
  if (!fs.existsSync(pagesDir)) return;

  const walk = (dir) => {
    for (const name of fs.readdirSync(dir)) {
      const p = path.join(dir, name);
      if (fs.statSync(p).isDirectory()) { walk(p); continue; }
      if (!name.endsWith('.ux')) continue;

      const src = fs.readFileSync(p, 'utf8');
      const m = src.match(/<script>([\s\S]*?)<\/script>/);
      if (!m) continue;
      const script = m[1];
      const rel = path.relative(proj, p);

      // 取 export default 对象的第一层键（本工程格式固定为 2 空格缩进）
      const vmDecl = [];
      const literals = [];
      for (const line of script.split(/\r?\n/)) {
        const km = line.match(/^ {2}([A-Za-z_$][\w$]*)\s*:\s*(.*)$/);
        if (!km) continue;
        const key = km[1];
        const rest = km[2].trim();
        if (['data', 'public', 'protected', 'private'].includes(key)) {
          vmDecl.push(key);
        } else if (/^(\{|\[|null\b|\d|'|"|true\b|false\b)/.test(rest)) {
          literals.push(key);
        }
      }

      if (vmDecl.includes('data') && vmDecl.some((k) => k !== 'data')) {
        problems.push(rel + ' 同时声明了 ' + vmDecl.join(' / ') +
          '\n     → 运行时抛「属性data不可与public,protected,private同时存在」，' +
          '页面 VM 建不起来，表现为点按钮毫无反应。请统一只用 protected。');
      }
      if (literals.length) {
        warns.push(rel + ' 顶层字面量属性: ' + literals.join(', ') +
          '\n     → 这些键不保证会挂到页面实例上；请在 onInit() 里显式赋值，且读取前兜底');
      }
    }
  };
  walk(pagesDir);

  for (const w of warns) console.log('⚠ ' + w);
  if (problems.length) {
    fail('构建前检查未通过：\n  ' + problems.join('\n  '));
  }
  console.log('✔ 构建前检查通过（页面 VM 声明无冲突）\n');
}

preflight();

rmTemp();

const cli = path.join(proj, 'node_modules', 'aiot-toolkit', 'lib', 'bin.js');
if (!fs.existsSync(cli)) fail('没有安装依赖，先跑 npm install');

console.log('▶ aiot ' + mode + ' …\n');
const res = spawnSync(process.execPath, [cli, mode].concat(process.argv.slice(3)), {
  cwd: proj,
  stdio: 'inherit'
});

rmTemp();

if (res.status !== 0) {
  // rimraf 删软链接失败会让退出码变 1，但只要产物在就当作成功
  console.log('\n（aiot 退出码 ' + res.status + '，通常是临时目录清理失败，忽略）');
}

// ---------------------------------------------------------------- 产物校验
const dist = path.join(proj, 'dist');
if (!fs.existsSync(dist)) fail('没有生成 dist/ 目录');
const rpks = fs.readdirSync(dist).filter((f) => f.endsWith('.rpk'));
if (!rpks.length) fail('dist/ 里没有 .rpk');

const rpk = path.join(dist, rpks.sort().pop());
const size = fs.statSync(rpk).size;
console.log('\n▶ 产物: ' + path.relative(proj, rpk));
console.log('  体积: ' + (size / 1048576).toFixed(2) + ' MB');
if (size > 10 * 1048576) console.log('  ⚠ 超过 10MB 参考上限');

// 直接解析 zip 中央目录列出 rpk 内容，不依赖外部 tar
function zipList(file) {
  const buf = fs.readFileSync(file);
  let eocd = -1;
  for (let i = buf.length - 22; i >= 0 && i > buf.length - 70000; i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) return null;
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  const names = [];
  for (let i = 0; i < count; i++) {
    if (p + 46 > buf.length || buf.readUInt32LE(p) !== 0x02014b50) break;
    const nlen = buf.readUInt16LE(p + 28);
    const elen = buf.readUInt16LE(p + 30);
    const clen = buf.readUInt16LE(p + 32);
    names.push(buf.toString('utf8', p + 46, p + 46 + nlen));
    p += 46 + nlen + elen + clen;
  }
  return names;
}

const list = zipList(rpk);
if (list) {
  const jpg = list.filter((f) => /\.jpe?g$/i.test(f));
  const png = list.filter((f) => /\.png$/i.test(f));
  const chunks = list.filter((f) => /story\/chunk-\d+\.txt$/.test(f));
  const hasIndex = list.some((f) => /story\/index\.txt$/.test(f));
  console.log('  条目: ' + list.length + '  PNG: ' + png.length + '  剧本块: ' + chunks.length);
  if (jpg.length) console.log('  ⚠ 含 JPEG（真机解码不可靠）: ' + jpg.length + ' 个');
  if (!hasIndex) fail('rpk 里没有 common/story/index.txt');
  if (!chunks.length) fail('rpk 里没有剧本分块');
} else {
  console.log('  （无法解析 rpk 目录，跳过内容校验）');
}

console.log('\n✔ 完成');
