# Matplotlib Prefab 服务器交接文档

本文供接手服务器上的维护者或 coding agent 使用，覆盖当前交付状态、启动、完整验证及后续工作。项目的三个阶段已实现：绘图 skill、会议论文上下文评估、浏览器图表调参与版式校准工具。接手时应复用现有实现，无需重新初始化或重做迁移。

## 交接基线与远端状态

- 核对日期：2026-10-05 UTC。
- 仓库：`https://github.com/cbhua/matplotlib-prefab.git`，分支 `main`。
- 本次核对时，本地 HEAD 与 GitHub 远端 main 均为 `ba90fda1be2ba37d13ff1c00f0fc9a573b28de15`，已有代码已 push。
- 网页功能提交：`abb0982`；最新基线提交 `ba90fda` 增加临时文件忽略规则。
- 本文在上述基线之后新增，需要随下一次提交推送，或单独传给接手人。
- `.tmp/`、`.venv/`、`.venv-render-parity/` 和 `web/public/generated/pyodide/` 被 Git 忽略，clone 不会带过去。

原始计划在 `.tmp/plans/01.single-column-figure-skill.md`、`02.conference-context-evaluation.md`、`03.browser-conference-style-lab.md`，原始交接报告在 `.tmp/reports/03.browser-conference-style-lab.handoff.md`。它们只存在于原服务器；本文包含接手所需信息。如果需要原始过程记录，请另外传输这些文件。

## 已完成的功能与验收

最后一份计划 03 的 A–G 阶段已实施：Pyodide 原型、六种论文页基准、页面校准、共享参数与 UI、配置导出、全矩阵验收、文档交接。

| 能力 | 当前交付 |
| --- | --- |
| 绘图 skill | 单面板 line/bar；输出 PDF、PNG、输入快照、resolved profile、检查报告 |
| 会议上下文 | ICLR 2026、NeurIPS 2026、ICML 2026；真实模板、正文 fixture 与 PDF 测量 |
| 浏览器工具 | 三会议切换、窄幅/宽幅、示例与 JSON spec 导入、字号/字重/线宽等控件、重置 |
| 实际渲染 | Web Worker 内通过 Pyodide 调用共享 Python 绘图核心，返回 SVG |
| 导出 | 复制给 Agent、纯 profile、配置下载、剪贴板失败回退；当前配置未绘制成功时禁止导出 |
| 一致性 | 10 组浏览器/本地 SVG 比较、3 组导出回环全部通过 |
| 页面校准 | 六种会议/宽度布局；12 组默认页面加 3 组调参页面对照全部通过 |

纸张正文从编译后的 LaTeX PDF 提取布局，主要文字使用 SVG `<text>` 和已打包的实际字体；数学特殊字形使用 PDF 内嵌字体提取的矢量路径。该选择偏离原计划的 HTML span 方案，原因是 SVG 可以直接指定文字基线。没有采用整页截图模拟正文。

| 会议 | 窄幅 | 宽幅 |
| --- | --- | --- |
| ICLR 2026 | 半正文宽 69.85 mm | 全正文宽 139.70 mm |
| NeurIPS 2026 | 半正文宽 69.85 mm | 全正文宽 139.70 mm |
| ICML 2026 | 一栏 82.55 mm | 真实 `figure*` 跨两栏 171.45 mm |

这些尺寸来自模板测量资产。切换宽度时不会自动放大字号；图高/宽高比固定，以保持正文图槽与校准一致。

## 新服务器启动

以下从干净 clone 开始。快速预览只需要 Python、下载 runtime 所需的网络和 HTTP 服务；已提交的字体、论文页和 Python 资产可以直接使用，不需要重新安装 LaTeX 或编译页面。

```sh
git clone https://github.com/cbhua/matplotlib-prefab.git
cd matplotlib-prefab
git rev-parse HEAD
python3 scripts/fetch_pyodide.py
python3 scripts/fetch_pyodide.py --verify
python3 web/serve.py
```

默认服务地址为 `http://127.0.0.1:8765/index.html`。从自己的电脑访问服务器预览，可在自己电脑的终端运行下面的命令，替换 SSH 目标后打开相同地址：

```sh
ssh -L 8765:127.0.0.1:8765 USER@SERVER
```

`file://` 不可用，Worker/WASM 需要通过 HTTP 加载。runtime 按 `web/pyodide.lock.json` 下载并校验 SHA256，约 24.19 MiB；不要使用 `--record`，该选项用于升级锁定版本。

浏览器最终使用的是服务器提供的 runtime 与资源，普通用户无需安装 Python 或 LaTeX。预览服务只用于本地查看；网站正式发布尚未执行。后续静态托管应以完整 `web/` 为站点根目录，包括另行下载的 `public/generated/pyodide/`，保留相对路径，并正确提供 `.wasm`、`.mjs` 和字体 MIME 类型。浏览器计算不需要后端绘图服务。

## 开发与完整验证环境

原服务器主环境使用 Python 3.12。新服务器建议使用 Python 3.12 创建主环境；项目声明最低 Python 3.9，但这不代表所有新版本依赖在该版本都可安装。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install matplotlib numpy pytest pypdf playwright pillow fonttools brotli uv
.venv/bin/python -m playwright install chromium firefox
```

浏览器缺少系统共享库时，由有权限的管理员安装 Playwright 所需依赖，例如使用 `.venv/bin/python -m playwright install-deps chromium firefox`。WebKit 的验证可在安装对应浏览器和系统依赖后另行开展。

完整基准生成还需要 LaTeX、Poppler 和 URW 字体。Debian/Ubuntu 的参考安装命令如下，需管理员权限：

```sh
sudo apt install texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra latexmk poppler-utils fonts-urw-base35
.venv/bin/python tests/render_conference_context.py --check-dependencies
```

浏览器/本地等价比较使用独立环境 `.venv-render-parity`，与主环境分开。`scripts/parity.py` 从 runtime lock 读取 Matplotlib/NumPy 版本，并通过 PATH 上的 `uv` 创建 Python 3.12 环境：

```sh
export PATH="$PWD/.venv/bin:$PATH"
python scripts/parity.py --setup
python scripts/parity.py --status
```

当前锁定的 Pyodide 分发版本为 0.28.3，浏览器报告 Python 3.13.2、Matplotlib 3.8.4、NumPy 2.2.5。本地 parity 使用 Python 3.12；这个解释器差异已记录在一致性报告中。SVG 等价结论依赖相同数据、profile、代码、字体及锁定绘图库版本，不能扩展为任意环境或不同数据的视觉一致。

## 接手验证顺序

先启动浏览器预览并检查：三个会议及两种宽度可切换，line/bar 可绘制，修改一个轴字号后预览更新，复制/下载可用，无效 JSON 有明确错误。然后执行：

```sh
.venv/bin/python -m pytest -ra
```

2026-10-05 在原服务器重新验证得到合计 **380 passed、1 skipped**：完整套件在沙箱中先得到 357 passed，23 项浏览器测试因无法创建本地 socket 在 setup 阶段报错；允许启动 loopback HTTP 服务后单独重跑这 23 项，全部通过。唯一 skip 是工具链已安装时不适用的缺依赖场景。新服务器请记录自己的实际结果，不能直接沿用此数字。

源码/模板/默认 profile 修改后，用下面的命令重建对应产物和证据；完整网页流程需要前述工具链、浏览器及 runtime 下载能力：

```sh
.venv/bin/python scripts/build_and_verify_web.py --list
.venv/bin/python scripts/build_and_verify_web.py
.venv/bin/python -m pytest -ra
```

若修改默认 profile，还需更新已提交的绘图与会议上下文 proof sheet：

```sh
.venv/bin/python tests/render_gallery.py
.venv/bin/python tests/render_conference_context.py --all
```

`build_and_verify_web.py --fast` 会跳过所有 LaTeX 阶段，不能算作完整页面校准验收。测试中的报告指纹漂移应通过重新生成修复；不要修改测试或手工编辑报告来隐藏失效。

## 代码入口与证据位置

| 路径 | 用途 |
| --- | --- |
| `skills/scientific-figures/SKILL.md` | Agent 绘图与交接配置使用流程 |
| `skills/scientific-figures/scripts/figure_core.py` | CLI、上下文 evaluator、浏览器共用的绘图核心 |
| `skills/scientific-figures/scripts/inspect_figure.py` | 绘图检查与 live checks |
| `skills/scientific-figures/references/profiles/single-column.json` | 默认样式真源，仍为 provisional |
| `web/src/app.js`、`controls.js`、`render-worker.js` | UI、参数映射、渲染队列及过期结果处理 |
| `web/src/export-config.js` | Agent 文本与机器可读导出契约 |
| `web/src/paper-page.js`、`paper-page.css` | 校准后的固定论文页 |
| `web/public/generated/` | 构建生成资产，应修改对应源码后重建 |
| `tests/web/calibration/` | 原型、页面校准、等价性、导出回环、端到端、浏览器范围报告与对照图 |
| `tests/web/test_verification.py` | 检查证据通过与源码指纹一致 |
| `tests/README.md`、`tests/web/README.md`、`web/README.md` | 测试、视觉观察、网页运行与维护说明 |

## 已知限制与待处理事项

1. **浏览器范围**：已保存的报告验证了 Chromium 和 Firefox。WebKit 在原环境无法启动，尚未验证；不能声称 Safari 已兼容。
2. **性能以 JSON 为准**：当前 `render-equivalence.json` 的 Chromium 40 次交互 p95 为 **300.8 ms**，达到 500 ms 目标。`browsers.json` 的 Firefox 12 次样本 p95 为 **1417.1 ms**；该小样本不能作为完整性能认证。README 的 217 ms 与原交接的 Firefox 630 ms 已过时，后续应同步文档。
3. **人工审阅**：浏览器导出仍将 `visual_review` 留为未完成；自动渲染和几何通过不等于人工视觉认可。`tests/README.md` 另有 2026-09-08 的会议页视觉观察：窄幅 `bar-signed` 类别标签拥挤，字体相对正文显大。默认样式仍待用户决定，不应擅自 finalize。
4. **范围限制**：只有单面板 line/bar；不支持任意图片内部样式编辑、任意论文编辑、自由图高/宽高比。网页验证的是固定 fixture，不能保证用户整篇论文的 float、分页与自定义宏编译成功。
5. **发布状态**：未部署，也没有离线缓存；字体许可文件随已生成资产保留，相关来源见 `web/README.md`。
6. **旧记录状态**：原计划仍写“待执行”，原 handoff 仍写“未提交”，属于历史文档未更新；当前代码已 push，本文的远端核对结果及实际 JSON 证据优先。

## 给接手 Agent 的执行要求

从仓库检查和上述启动/测试开始，保留已有共享实现、数据顺序、检查逻辑与用户样式选择。不要另写 JavaScript 图表模板替代 Matplotlib，不要手工维护生成目录中的源码副本，不要放宽校准阈值来使测试通过。

下一步可先同步过时文档、开展人工视觉审阅并补 WebKit 验证，再根据用户的新要求调整样式或安排发布。本次交接只准备文档，未授权接手 Agent 自动部署、推送、安装全局配置或执行破坏性 Git 操作；这些操作按后续用户授权执行。
