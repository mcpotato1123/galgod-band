# GalGod · 小米手环 9 Pro 版

把 PC 版 Ren'Py galgame **GalGod 1.0.0** 移植成能在**小米手环 9 Pro**（336×480 矩形 AMOLED）上跑的 **Vela 快应用**。

引擎与 UI 参照开源工程 [mcpotato1123/galgaoshou-vela-compile-](https://github.com/mcpotato1123/galgaoshou-vela-compile-)（《难道你是GAL高手》手环移植）的架构：**索引 + 分块剧本的流式阅读器 + 声明式图片绑定 + storage 存档**。

```
剧本数据  5,569 个节点 / 18 章 / 44 个分块
对话      5,457 句（全量，非删减）
美术      136 张（背景 38 / 立绘 55 / CG 34 / 鉴赏缩略图 9）+ 标题画 + 图标
分支      15 个选择点，3 条结局线 + 1 个 Bad End
CG 鉴赏   9 组 / 32 张差分图，按原作 gallery.rpy 的分组与解锁条件
产物      dist/com.galgod.band.debug.1.1.1.rpk   4.76 MB
```

> **免责声明**：本项目是非官方的个人移植，仅供学习交流。
> 剧本文字与全部美术资源（背景 / 立绘 / CG）版权归 **GalGod** 原开发商所有，
> 本仓库出于「可运行」的需要收录了转码后的资源；请不要用于任何商业用途。
> 本仓库的**代码**部分可自由参考。详见文末「九、版权与免责」。

---

## 一、目录结构

```
GalGod手环版/
├─ package.json              npm 脚本与 aiot-toolkit 依赖
├─ src/                      快应用源码（Vela 固定目录名）
│  ├─ manifest.json          应用清单：包名/图标/路由/features/designWidth
│  ├─ app.ux                 应用入口（本工程不用全局生命周期）
│  ├─ common/
│  │   ├─ assets.js          ← 生成：图片索引表（剧本里的资源号就是数组下标）
│  │   ├─ cglist.js          ← 生成：CG 鉴赏分组与解锁条件
│  │   ├─ reader.js          阅读器公共逻辑：设置项、storage 封装、自动播放时长
│  │   ├─ home.png           标题画（由游戏 main_screen 转出）
│  │   ├─ icon.png           应用图标
│  │   ├─ img/b/*.png        ← 生成：背景 336×480
│  │   ├─ img/s/*.png        ← 生成：立绘 143×380（带透明通道）
│  │   ├─ img/c/*.png        ← 生成：CG / SDCG 336×480（满屏）
│  │   ├─ img/t/g0..8.png    ← 生成：CG 鉴赏缩略图 96×54
│  │   └─ story/
│  │       ├─ index.txt      ← 生成：章节表 + 分块表（内容是 JSON，用 .txt 扩展名）
│  │       └─ chunk-000.txt… ← 生成：44 个分块，每块 128 个节点
│  └─ pages/
│      ├─ index/             主页：继续 / 开始 / 存档 / 章节 / CG / 退出
│      ├─ game/              正文阅读器（引擎核心）
│      ├─ saves/             存档 / 读档（6 个手动槽 + 自动存档）
│      ├─ chapters/          章节选择（18 章）
│      └─ cg/                CG 鉴赏（9 组，含大图查看）
└─ tools/
    ├─ gen_story.py          剧本编译器：Ren'Py .rpy → 分块节点 + 图片索引
    ├─ gen_assets.py         美术生成器：大图 → 手环尺寸 PNG
    ├─ validate_story.py     剧本校验：分块完整性、引用越界、全图可达
    ├─ simulate.py           剧情流程模拟器：把全部路线跑一遍
    ├─ preview_ui.py         用真实资源按 CSS 数值合成界面效果图
    ├─ build.js              构建前静态检查 + 构建包装 + rpk 内容校验
    ├─ export_repo.py        导出「可上传 GitHub 的精简目录」
    └─ check_encoding.py     上传前自检：UTF-8 编码 / 误传文件 / README 图片
```

**仓库里已经带了生成好的剧本与美术资源**（`src/common/story/`、`src/common/img/`），
所以只想改代码的话直接 `npm install && npm run build` 就行，不需要原版游戏。
`gen_story.py` / `gen_assets.py` 是**溯源用**的——它们记录了资源是怎么从原版转出来的。

界面效果预览（`preview/ui-preview.png`，用真实资源按 `game.ux` 的 CSS 数值 1:1 合成）：

![界面预览](preview/ui-preview.png)

---

## 二、构建

```bash
npm install                    # 只有 aiot-toolkit 一个真正的依赖
npm run build                  # → dist/com.galgod.band.debug.1.0.0.rpk
npm run start                  # 起模拟器预览（需要 AIoT-IDE/模拟器环境）
```

`npm run build` 用的是 `tools/build.js` 而不是直接 `aiot build`，原因见第五节。

从 Ren'Py 原始资源重新生成（需要 Python 3 + Pillow，以及 PC 版解包出来的 `game/` 目录）：

```bash
set GALGOD_RAW=D:\path\to\GalGod-1.0.0-win\game
python tools/gen_story.py  "%GALGOD_RAW%" .
python tools/gen_assets.py "%GALGOD_RAW%" .
python tools/validate_story.py .
python tools/simulate.py .
python tools/preview_ui.py "%GALGOD_RAW%" .
```

---

## 三、安装到手环

`dist/` 里的 **debug rpk 可以直接侧载**，不需要签名证书。

1. 手机装 **小米运动健康**
2. 【我的】→【关于】→ 连点进入 **Debug**
3. 【第三方应用】→ 点 `Click to input package name` → 随便输几个字符
4. 【Install third app】→ 选本地 rpk 文件
5. 手环上会出现 **GalGod** 图标

> 官方 FAQ：<https://iot.mi.com/vela/quickapp/zh/guide/other/faq.html>
> 官方真机调试目前只支持 Xiaomi Watch S4，**手环 9 Pro 不在其列**，所以只能走上面这条侧载路径；查看运行日志要用小米运动健康的「拉取固件日志」。

**release 包**需要签名证书，`aiot release` 会报 `there is a problem with the certification path`：

```bash
mkdir sign
openssl req -newkey rsa:2048 -nodes -keyout sign/private.pem -x509 -days 3650 -out sign/certificate.pem
npm run release
```

---

## 四、运行时的设计

### 屏幕与单位

手环 9 Pro 官方参数：**336×480、矩形屏、1.74″、DPR 2.1、逻辑宽度 168dp**。
`manifest.json` 里 `designWidth: 336`，所以 **1px = 1 物理像素**，所有 CSS 数值直接按像素写，不需要换算，也不用媒体查询。

### 画面分层

| 层 | 元素 | 位置/尺寸 |
|---|---|---|
| 背景 | `<image>` `object-fit: cover` | 0,0 · 336×480 |
| 立绘 | 3 个固定槽位 `<image>` | left 10 / center 96 / right 182，宽 143 高 380，底边对齐 480 |
| CG | `<image>` 铺满 | 0,0 · 336×480 |
| 回忆滤镜 | 半透明色块 | 0,0 · 336×480，`opacity 0.22` |
| 顶部信息 | 章节名 + 章节进度 | 10,12 |
| 对白面板 | 半透明底板 | 312,0 · 336×168 |
| 正文 | 5 个固定 `<text>` | 350/374/398/422/446，字号 20、行高 24，宽 308 |

正文**不用滚动**，而是在构建期就把每句台词按「14 字/行、5 行/页」切成页：一句太长就变成多次点击。这样在 336 宽的小屏上永远不会出现「文字被截掉」或「需要在一句话里滚动」的情况。断行会优先落在标点之后，避免标点跑到行首。

### 剧本数据格式

`index.txt` 是索引，每块 128 个节点。节点类型：

| 类型 | 字段 | 含义 |
|---|---|---|
| `s` | `n` 说话人、`p` 预分页文本、可选 `bg`/`cs`/`cg`/`tint` | 一句台词 |
| `o` | `o[]` 选项（`x` 文本 / `j` 目标 / `c` 显示条件） | 分支 |
| `j` | `j` | 无条件跳转 |
| `cj` | `v` 标记、`op`、`n`、`j` | 条件跳转 |
| `f` | `v`、`n` | 标记累加（原作里的好感/答题计数） |
| `sf` | `v`、`n` | 标记赋值（例如 `true_end_finish`） |
| `e` | `x` | 结局，回标题 |

画面变化**只在真的变化时**才写进节点，运行时继承上一个状态（原作是「每个场景一份全量快照」，这里是增量，数据量小很多）。
图片一律用**整数下标**引用，路径只在 `common/assets.js` 里出现一次。

### 性能与内存

- 一次只读一个分块（约 12 KB），命中已加载块时零 I/O、零 `JSON.parse`
- 缓存只保留**当前块 + 下一块**，进入新块后后台预读下一块，随后强制淘汰更远的块
- 同块的并发请求会合并等待者，避免重复读盘
- 打字机用 50ms 一次的时间校正循环（不是每个字一个定时器），并用自增 token 取消过期回调
- 自动存档：每推进 8 次 + 400ms 去抖写一次；`onHide`/`onDestroy` 前强制落盘
- 所有交互按钮都加 400ms 点击锁：Vela 的 click 会冒泡到根节点的「轻触前进」，不加锁会一次点击同时触发按钮和翻页

### 交互

| 操作 | 行为 |
|---|---|
| 轻触任意处 | 文字没打完 → 立即显示完整；本页还有 → 下一页；否则进入下一句 |
| 长按 | 切换沉浸模式（隐藏 UI），再长按恢复 |
| 右上角 ≡ | 阅读菜单：继续 / 保存 / 读取 / 自动播放 / 跳到下一章 / 章节 / 主页 / 退出 |
| 系统返回手势 | 打开/关闭阅读菜单（不会误退出） |

### 长列表用 `<list>`，不要用 `<scroll>`

章节页（18 章）与存档页（7 条）都用 `<list>` + `<list-item>`，条目做成 **86px 高、标题字号 24**，
一屏只放 4 条。原因：

- 336×480 的屏幕上，48px 高的条目 + 7px 间隙太挤，手指很容易点错相邻项
- `<list>` 是原生滚动容器，带惯性；`<scroll>` 在手环上表现不佳
- 打开章节页时会用 `list.scrollTo({ index })` **自动滚到你上次读到的章节**，
  并在该行右侧标一个 `▶`（用空字符串占位，保证每个 `list-item` 结构一致，
  避免在 `list-item` 里写 `if`——官方明确不建议）

### 章节选择只列正片，结局与后日谈不进列表

结局是玩出来的，不该能直接跳；后日谈是真结局的奖励。编译期就在章节记录上打了标记：

```json
{"id":"end_te","title":"真结局 · 这片月幕","start":...,"hide":1}
{"id":"after_story_noctella","title":"后日谈 · 诺提拉","start":...,"need":1}
```

| 状态 | 章节选择里显示 |
|---|---|
| 未通关 | **14 章**（正片，无结局、无后日谈） |
| 通关真结局后 | **15 章**（多出「后日谈 · 诺提拉」） |

- `hide:1`（三个结局）**永不显示**
- `need:1`（后日谈）只在通关后显示
- 通关判定：走到终点节点时 `true_end_finish === 1`（只有真结局线会置位），
  写进 storage 的 `cleared` 键持久化
- 阅读菜单的「跳到下一章」走同一套过滤，**同样不会跳进结局或未解锁的后日谈**，
  在 3-4 会提示「已经是最后一章」

**注意**：`<list>` 必须显式设置高度；`<list-item>` 里的子元素统一用一层 `.card` 包裹来控制圆角和内边距。

### CG：正文满屏 + 鉴赏模式

**正文里的 CG 要满屏铺满，不要留黑边。** 最初用 `contain` 生成，16:9 的 CG 在 336×480 上只剩中间
`336×189` 一条、上下六成全黑，看起来跟"没显示"一样。改成 `cover` 裁两侧后，主体（原作 CG 都是
居中构图）完整保留，画面真正占满屏幕。看 CG 时对话底板还会换成更透的一档（`rgba(...,0.58)`
且高度收窄），尽量让画面露出来。

**CG 鉴赏**按原作 `screens/gallery.rpy` 还原：原作定义了 9 个 gallery 按钮，每个按钮
"看过某张图就解锁"，内部再放若干差分图。本工程把它编译成 `src/common/cglist.js`：

```js
export const CGG = [{"n":"政客","th":"/common/img/t/g0.png","u":108,"im":[108,109]}, ...]
//                  组名    缩略图路径                  解锁所需图下标  该组图片下标
```

- **解锁判定**沿用原作语义（`renpy.seen_image(...)`）：正文里播到某个 CG 节点时，
  把它的图片下标记进 storage 的 `cgSeen`，500ms 去抖写盘；`onHide`/`onDestroy` 前强制落盘
- 鉴赏页用 `<list>` 列 9 组：缩略图 + 组名 + 已解锁张数；未解锁的显示 `?` 且点按提示
- 点进去是全屏大图查看，底部 `‹ 1/2 ›` 在本组差分之间切换
- 入口有两个：主页的「CG」按钮、阅读菜单里的「CG」
- 缩略图是构建期生成的 9 张 96×54 小图（共 28 KB），不额外占用运行时开销

---

## 五、两个已知的坑（都已在代码里绕过）

**1. aiot-toolkit 在 Windows 上构建收尾会报 EPERM。**
它先把工程复制到同级 `../.temp_<工程名>` 再编译，收尾时用 rimraf 删这个临时工程，
而临时工程里的 `node_modules` 是软链接（junction），rimraf 删它必报
`EPERM: operation not permitted, unlink ...node_modules`。
此时 **rpk 其实已经生成好了**，但退出码是 1，还会留下垃圾目录，下次构建开头清理失败会直接中断。
`tools/build.js` 在构建前后各用 `rmdir /s /q` 清一次，并在构建后校验产物内容。

**2. rpk 里的 JSON 资源用 `.txt` 扩展名。**
参考工程也这么做。JSON 会被 webpack 当成模块处理，用 `.txt` 存 JSON 内容可以保证它被当作
纯资源原样复制进包，运行时再用 `@system.file.readText` 读（官方文档明确 `readText` 支持
`/common/xxx` 应用资源路径）。

**3. 不要给「有子节点」的容器加 `opacity`。—— 这条是真机实测出来的。**

首版装到手环 9 Pro 后，主页上半部分（背景图 + `opacity: 0.34` 的压暗层）完全正常，
下半部分却整块变成横向条纹、内容被压扁重复。原因就是 `.panel` 用了
`background-color: #150f19; opacity: 0.94`，而它**内部还有按钮等子节点**：
`opacity` 会让运行时把整棵子树离屏合成，手环固件上这条路径是坏的。空 div 用 `opacity`
则没事（压暗层就是证据）。

参考工程其实一直规避这件事——它的 `.dialogue-panel` 是个**空 div**（只负责半透明底），
说话人和正文都是它的**兄弟节点**，绝不放进带 `opacity` 的容器里。

**本工程的做法**：所有半透明一律改用 `rgba()` 背景色，彻底不用 `opacity`。
`background-color` 走标准 CSS 校验器，`rgba()` 与 `#rrggbbaa` 都合法：

```css
/* 不要这样（容器里有子节点时会渲染成条纹） */
.panel { background-color: #150f19; opacity: 0.94; }
/* 要这样 */
.panel { background-color: rgba(21, 15, 25, 0.94); }
```

顺带修掉的一个真 bug：主页面板内容高度约 236px 塞进了 230px 的容器（轻微溢出），
已把面板改成 `top: 240px; height: 240px`。

**4. `data` 不能与 `public` / `protected` / `private` 同时出现。—— 固件日志实锤。**

现象：点主页「开始阅读」**完全没反应**，界面停在原地。

小米运动健康拉出来的固件日志里直接写着原因：

```
[AIOTJS] [jse_dump_obj:788] Error: 页面VM对象中的属性data不可与"public,protected,private"同时存在，
                                   请使用private替换data名称
    at __scriptModule__ (@aiot/game:1691)
    at <anonymous> (@aiot/game:2570)
```

页面 VM 根本建不起来，所以页面不会渲染、按钮点了也没有任何反馈——每次点击都只是重复抛同一个错。

**本工程的规矩**：每个页面**只用 `protected`**，路由参数和界面状态都写在里面，
全工程不出现 `data`：

```js
export default {
  protected: {
    load: '', auto: '', at: '',     // 路由参数
    badge: '', chapterTitle: '——',  // 界面状态
    ...
  },
  ...
}
```

`tools/build.js` 里加了构建前静态检查，任何页面只要同时出现 `data` 与
`public/protected/private` 就直接拦住、拒绝构建，不会再等到真机上才发现。

**5. 写在 `export default` 顶层的「非绑定属性」不保证会出现在页面实例上。**

这条与第 4 条同源，是推断出来的（没有取到对应日志）：如果像下面这样把非绑定状态写在顶层，
运行时可能不会把它挂到页面实例上，而**纯读取**不会补上属性（只有赋值才会）：

```js
export default {
  chunkCache: {},                        // ← 可能被丢掉
  ...
}
readChunk(chunk, done) {
  if (this.chunkCache[chunk.start]) {}   // undefined[...] → TypeError
}
```

同一个文件里 `flags`、`pc` 都没事，只因为它们都在使用前先赋过值。

**本工程的规矩**：非绑定状态**全部在 `onInit()` 里显式初始化**，并且读取前兜底：

```js
readChunk(chunk, done) {
  if (!this.chunkCache) this.chunkCache = {}
  if (!this.chunkPending) this.chunkPending = {}
  ...
}
```

构建前检查会对顶层字面量属性给出警告。

**6. 诊断能力要提前埋好。**
第 4 条能一次定位，靠的是当时已经具备的三样东西：分阶段 `console.log('[GalGod] …')`、
屏上的状态徽标（而不是全屏遮罩）、以及 `config.logLevel` 不是 `off`。
如果当时还是「全屏遮罩 + 只弹 toast + 关日志」，这个 bug 只能靠猜。

---

## 六、和参考工程不一样的地方（以及为什么）

参考工程的 `小米手环9Pro` 分支实际写的是 `designWidth: 212`、资源按 212×520 出图，
内部文档也自称 "Band 10 layout" —— 那是**手环 10 的规格**，和 9 Pro 的 336×480 对不上。
本工程按官方设备参数表以 **336×480 / designWidth 336** 重新出图和布局，所以没有照抄它的 212。

| 项 | 参考工程 | 本工程 | 原因 |
|---|---|---|---|
| 设计宽度 | 212（+ `@media (shape: rect)` 切成 212×303） | 336（1:1 物理像素） | 9 Pro 就是 336 宽，1:1 最省事也最清晰 |
| 长文本 | 固定 196×82 视口 + 纵向 `<scroll>` | 构建期预分页成多次点击 | 小屏上「一句话要滚动才看得完」体验很差，且容易漏读 |
| 背景 | 692×520 宽幅 + 定时 `scrollTo` 手搓横移 | 静态 336×480 `cover` 裁剪 | 横移靠定时器很脆，收益小；优先保证不闪、不崩 |
| 立绘 | 导出前按包围盒裁到 76% 高度 | 整张全身图 contain 进 143×380 | 裁切系数是原工程的经验值，对另一套立绘不一定合适 |
| 图片格式 | PNG 调色板（背景 64 色） | PNG 调色板（128 色） | 体积预算只用了 3.6/9 MB，把余量花在画质上 |
| 列表容器 | `<list>`（存档页） | 章节页与存档页都用 `<list>` | 最初用了 `<scroll>`，真机上条目又挤又难点、滑动也不跟手；`<list>` 是原生滚动容器，惯性更可靠，条目也能做大 |

---

## 七、验证情况

| 验证 | 手段 | 结果 |
|---|---|---|
| 真机运行 | 小米手环 9 Pro 侧载 debug rpk | ✅ 能安装、能启动、主页与章节页正常渲染；**抓出并修复了两个真机专属 bug**（`opacity` 渲染、`data`/`protected` 冲突），见第五节坑 3、坑 4 |
| 构建前静态检查 | `tools/build.js` 的 `preflight()` | 拦住 `data` 与 `protected` 共存、并警告顶层字面量属性；已用故意违规的探针页面验证过确实会拦截 |
| 剧本完整性 | `tools/validate_story.py` | 44 块覆盖 5569 节点无空洞；**全图可达 5569/5569**；无越界引用 |
| 剧情流程 | `tools/simulate.py`（复刻 `game.ux` 的 `step()`/`onTap()` 语义跑真实数据） | 8 条策略全部正常收尾；**三条结局线 + Bad End 全部可达**；单周目不串结局 |
| 工程可构建 | `aiot build` | 编译通过，rpk 3.85 MB，195 条目 / 129 PNG / 44 剧本块，**无 JPEG**（真机解码 JPEG 不可靠） |
| 语法 | webpack 编译 | `.ux` / `.js` 全部通过编译 |

`simulate.py` 抓出过两个逻辑 bug（每章 `return` 被编译成「直接跳全剧终」、结局之间条件不成立时
互相「落空」串场）；真机 + 固件日志抓出了 `opacity` 渲染 bug 与 `data`/`protected` 冲突。
都已修掉。

**仍需真机确认的点**：

- `text` 组件是否按预期处理我们预先插好的换行；14 字/行是按「字号 20px、可用宽 308px」保守估的，真机字体度量若有偏差，可能出现某行折行导致第 5 行被裁
- 圆角矩形屏四角是否遮挡内容（官方没有 `safeArea` API，本工程左右各留了 10~14px）
- 单页 121 KB 的 `game.js`（debug 未压缩）在真机上的解析耗时
- 连续高频换图时的内存表现（参考工程要求真机连续推进 30 分钟无堆分配失败/无重启，本工程无法验证）

如果真机上发现文字折行导致第 5 行被裁，改 `tools/gen_story.py` 顶部的 `CHARS_PER_LINE` 调小即可（例如 13），
重新跑 `gen_story.py` + `build` 就能生效，不需要动运行时代码。

---

## 八、操作提示

- 生成脚本都要传两个参数：`<Ren'Py 的 game 目录> <本工程目录>`
  ```bash
  python tools/gen_story.py  "D:\path\to\GalGod-1.0.0-win\game" .
  python tools/gen_assets.py "D:\path\to\GalGod-1.0.0-win\game" .
  python tools/preview_ui.py "D:\path\to\GalGod-1.0.0-win\game" .
  ```
  仓库里已经带了生成好的资源，**只是改代码的话不需要跑这些脚本**，直接 `npm run build` 即可。
- 想改台词呈现：`tools/gen_story.py` 里的 `CHARS_PER_LINE` / `LINES_PER_PAGE`
- 想改画质与体积：`tools/gen_assets.py` 里的 `BG_COLORS` / `SP_COLORS` / `CG_COLORS` 与 `SPRITE_W`/`SPRITE_H`
  （改 `SPRITE_W`/`SPRITE_H` 必须同步改 `src/pages/game/game.ux` 里 `.sp` 的宽高与三个槽位的 `left`）
- 想改章节标题：`tools/gen_story.py` 的 `CHAPTER_TITLES`
- 想加/减 CG 鉴赏分组：`tools/gen_story.py` 的 `GALLERY`

---

## 九、版权与免责

- **这是非官方的个人移植项目**，与 **GalGod** 原开发商、小米公司均无关联。
- **剧本文字与美术资源**（背景、立绘、CG、标题画）版权归原作所有。
  `src/common/story/`、`src/common/img/`、`src/common/home.png`、`src/common/icon.png`
  都是从 PC 版游戏解包并转码而来的衍生文件——收录它们只是为了让仓库**能直接构建出可运行的包**。
  请勿用于商业用途；如版权方有异议，删除相应目录即可（代码本身不依赖具体内容，换个剧本照样能跑）。
- **代码部分**（`src/pages/`、`src/common/reader.js`、`src/app.ux`、`tools/`）可自由参考、修改。
  架构思路来自 [galgaoshou-vela-compile-](https://github.com/mcpotato1123/galgaoshou-vela-compile-)。
- 侧载第三方应用到手表属于非官方途径，**风险自负**。

