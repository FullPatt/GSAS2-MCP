# GSAS-II — XRDFPSR Fork

[![Documentation Status][rtd-badge]][rtd-link]
[![Actions Status][actions-badge]][actions-link]
[![License](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)

<!-- prettier-ignore-start -->
[actions-badge]:            https://github.com/AdvancedPhotonSource/GSAS-II/workflows/CI/badge.svg
[actions-link]:             https://github.com/AdvancedPhotonSource/GSAS-II/actions
[rtd-badge]:                https://readthedocs.org/projects/GSAS-II/badge/?version=latest
[rtd-link]:                 https://GSAS-II.readthedocs.io/en/latest/?badge=latest
<!-- prettier-ignore-end -->

本 fork 在 [AdvancedPhotonSource/GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) 上游基础上增加了 MCP（Model Context Protocol）服务器集成、AI 智能体接口，以及预编译的 Python 3.11 Fortran 二进制扩展。

This fork extends the upstream [AdvancedPhotonSource/GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) with MCP (Model Context Protocol) server integration, AI agent interfaces, and pre-compiled Python 3.11 Fortran binary extensions.

---

## 项目目的 / Purpose

**上游 GSAS-II** 是一款功能强大的 X 射线/中子衍射数据分析软件，支持粉末衍射 Rietveld 精修、单晶衍射、PDF 分析、SAXS 等多种技术。

**本 fork 的目标**：

- 🧩 **MCP 协议支持**：通过标准的 MCP 协议将 GSAS-II 的精修能力暴露给 AI 智能体（Claude, Copilot, Cursor 等）
- 🤖 **AI 增强工作流**：支持自动参数推荐、智能诊断、增量精修策略
- ⚙️ **Headless 运行**：无需 wxPython GUI，纯 Python 命令行即可操作
- 🏗️ **预编译二进制**：提供 Python 3.11 的 Fortran `.so` 扩展，开箱即用
- 🔧 **编译器缺失环境兼容**：自动 fallback 机制，即使没有 Fortran 编译器也能运行核心功能

### 相关 MCP 项目

| 项目 | 说明 |
|------|------|
| [gsas2-mcp-server](https://github.com/XRDFPSR/gsas2-mcp-server) | GSAS-II MCP 服务器（独立仓库，依赖本 fork） |
| [fullprof-mcp](https://github.com/XRDFPSR/fullprof-app) | FullProf MCP 服务器 |
| [Profex-MCP](https://github.com/XRDFPSR/Profex-MCP) | Profex/BGMN MCP 服务器 |
| [maud-mcp](https://github.com/XRDFPSR/maud) | MAUD MCP 服务器 |

---

## 与本 fork 的变更 / Changes vs Upstream

| 变更 | 说明 |
|------|------|
| 🔧 `GSASIIobj.py` P1SGData fallback | 修复无 `pyspg` 二进制时 `SetNewPhase()` 的 `NameError` |
| 📦 Python 3.11 `.so` 二进制 | 预编译 pyspg/pypowder/pytexture/pydiffax 等 8 个扩展模块 |
| 🧪 完整 MCP 兼容 | 全部 41 个 gsas2-mcp-server 测试通过 |

---

## 代码结构 / Code Structure

```
GSAS-II/
├── GSASII/                          # 核心 Python 包
│   ├── GSASII.py                    # GUI 入口（wxPython）
│   ├── GSASIIobj.py                 # 🔥 P1SGData fallback 修复
│   ├── GSASIIscriptable.py          # 脚本化 API（MCP 服务器依赖）
│   ├── GSASIIpath.py                # 路径/二进制管理
│   ├── GSASIIstrIO.py / Math.py     # 精修 I/O 与计算引擎
│   ├── GSASIIlattice.py             # 晶格参数计算
│   ├── GSASIIspc.py                 # 空间群运算
│   ├── imports/                     # 数据导入器
│   │   ├── G2phase_CIF.py           # CIF 物相导入器
│   │   ├── G2img_*.py               # 图像导入器
│   │   └── ...                      # 30+ 导入格式
│   ├── *.cpython-311-*.so           # ✅ 预编译 Fortran 扩展
│   └── ...                          # 100+ 模块
├── sources/                         # Fortran/C 源码
│   ├── pyspg.for                    # 空间群计算
│   ├── pypowder.for                 # 粉末衍射花样计算
│   ├── pytexture.for                # 织构计算
│   ├── pydiffax.for                 # DIFFaX 衍射计算
│   ├── pack_f.for / unpack_cbf.for  # 图像解包
│   ├── histogram2d.for              # 2D 直方图
│   ├── fmask.c                      # 图像掩膜
│   ├── spsubs/                      # 空间群辅助库
│   ├── powsubs/                     # 粉末计算辅助库
│   ├── texturesubs/                 # 织构计算辅助库
│   ├── NISTlatsubs/                 # NIST 晶格辅助库
│   └── meson.build                  # Meson 构建配置
└── tests/                           # GSAS-II 测试数据
    └── testinp/                     # 测试输入文件 (PbSO4)
```

---

## 编译方法 / Compilation

### 前置条件 / Prerequisites

- **Python 3.10+**（本 fork 提供 Python 3.11 二进制）
- **Fortran 编译器**（用于编译扩展模块，可选）
  - gfortran 12+ （推荐 conda-forge 版本）
  - 或直接从 [Releases](https://github.com/XRDFPSR/GSAS-II/releases) 下载预编译 `.so`

### 编译全部 Fortran 扩展 / Compile All Extensions

```bash
# 1. 安装 gfortran（推荐 conda-forge，无需 root）
micromamba create -y -p ./gfortran-env -c conda-forge gfortran_linux-64
export PATH="./gfortran-env/bin:$PATH"
export LD_LIBRARY_PATH="./gfortran-env/lib"

# 2. 编译 8 个扩展模块
cd sources

gfortran -fPIC -O2 -c pyspg.for -o pyspg.o
gfortran -fPIC -O2 -c spsubs/*.for          # 空间群辅助
gfortran -fPIC -O2 -c NISTlatsubs/*.f       # NIST 晶格辅助
gfortran -fPIC -O2 -c INCLDS/COPYRIGT.FOR
gcc -fPIC -O2 -c pyspgmodule.c -o pyspg_mod.o
gfortran -shared -o pyspg.cpython-311-x86_64-linux-gnu.so *.o -lm
cp *.so ../GSASII/

# 其他模块类似（见 build 文档）
```

### 一键构建脚本 / One-Click Build

```bash
# 完整构建脚本位于 sources/meson.build
# 或使用 meson（需安装 Python meson 包）：
pip install meson ninja
cd sources && meson setup build && meson compile -C build
```

### 验证安装 / Verify Installation

```python
import sys
sys.path.insert(0, '.')
from GSASII import GSASIIpath
GSASIIpath.SetBinaryPath()
from GSASII import pyspg
print(pyspg.__file__)  # 应显示 .so 路径
```

---

## MCP 服务器集成 / MCP Server Integration

本 fork 的目标是为 [gsas2-mcp-server](https://github.com/XRDFPSR/gsas2-mcp-server) 提供依赖。该 MCP 服务器通过标准协议将 GSAS-II 的精修能力暴露给 AI 智能体。

### MCP 工具清单

服务器提供 15+ 个 MCP 工具：

| 类别 | 工具 | 功能 |
|------|------|------|
| **项目管理** | `create_project` | 创建新 .gpx 项目 |
| | `load_project` | 加载已有项目 |
| | `project_summary` | 获取项目摘要 |
| **数据导入** | `add_powder_histogram` | 添加粉末衍射数据 |
| | `add_phase` | 从 CIF 添加物相 |
| | `add_image` | 添加 2D 探测器图像 |
| **精修控制** | `set_refinement` | 设置精修参数 |
| | `refine` | 执行精修 |
| | `get_results` | 获取精修结果 |
| **智能诊断** | `auto_diagnose` | 自动诊断 + 修复建议 |
| | `suggest_best_strategy` | 推荐最佳精修策略 |
| | `generate_report` | 生成精修报告 |
| **可视化** | `generate_plot` | 生成拟合图 |
| **参数控制** | `hold_variable` | 固定参数 |
| | `free_variable` | 释放参数 |

### 快速启动

```bash
# 安装 MCP 服务器
git clone https://github.com/XRDFPSR/gsas2-mcp-server.git
cd gsas2-mcp-server
pip install -r requirements.txt

# 确保 GSAS-II 在 Python 路径中
export PYTHONPATH=/path/to/GSAS-II:$PYTHONPATH

# 启动 stdio MCP 服务器（用于 Claude Desktop 等）
python -m gsas2_mcp_server

# 启动 SSE HTTP 服务器
python -m gsas2_mcp_server --transport sse --port 8910
```

### MCP 宿主配置 (Claude Desktop / VS Code)

```json
{
  "mcpServers": {
    "gsas2-mcp": {
      "command": "python3",
      "args": ["-m", "gsas2_mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/GSAS-II"
      }
    }
  }
}
```

---

## 兼容性说明 / Compatibility Notes

### 支持的 Python 版本

| 版本 | 二进制支持 | 说明 |
|------|-----------|------|
| Python 3.11 | ✅ 预编译 | 本 fork 提供完整 8 个 `.so` |
| Python 3.12 | ⚠️ 需编译 | 无预编译二进制 |
| Python 3.13 | 🔄 上游 meson | 上游提供的 cp313 二进制 |

### headless / 无 Fortran 编译环境

本 fork 在 `GSASIIobj.py` 中提供了 P1SGData fallback 回退机制，使得：

- 即使没有 Fortran 编译器
- 即使 `pyspg` 等二进制缺失
- 也能正常创建项目、添加物相、进行脚本化操作

空间群运算和粉末衍射花样计算等功能需要编译的二进制支撑。

---

## 快速验证 / Quick Test

```bash
# 验证 GSAS-II 核心功能
python3 -c "
import sys, os
sys.path.insert(0, '.')
os.environ['GSASII_HEADLESS'] = 'true'
from GSASII import GSASIIscriptable as G2sc
gpx = G2sc.G2Project(newgpx='/tmp/test.gpx')
print(f'✅ Project created')
hist = gpx.add_powder_histogram('tests/testinp/PBSO4.XRA',
    iparams='tests/testinp/INST_XRY.PRM')
print(f'✅ Data loaded: {hist.name}')
phase = gpx.add_phase('tests/testinp/PbSO4-Wyckoff.cif')
print(f'✅ Phase added: {phase.name}')
"
```

---

## 许可证 / License

**BSD 3-Clause License**（与上游 GSAS-II 一致）

---

## 致谢 / Acknowledgements

- **Advanced Photon Source, Argonne National Lab** — GSAS-II 开发团队
- **Juan Rodríguez-Carvajal** — FullProf
- **Nico B.** — Profex
- **Luca Lutterotti** — MAUD

<!-- SPHINX-START -->

<!-- prettier-ignore-start -->

[comment]: # (以下为 upstream README 保留内容)

## URLs
* The
  [home page for GSAS-II](https://advancedphotonsource.github.io/GSAS-II-tutorials) has
  [installation instructions](https://advancedphotonsource.github.io/GSAS-II-tutorials/install.html) and a link
  to [the downloads location](https://github.com/AdvancedPhotonSource/GSAS-II-buildtools/releases/latest).

* [This repo](https://github.com/AdvancedPhotonSource/GSAS-II) is the main repository for the GSAS-II source code (replacing the
  [old subversion site](https://subversion.xray.aps.anl.gov/pyGSAS)
  and the [trac web site](https://subversion.xray.aps.anl.gov/trac/pyGSAS/browser)), but there are two additional repo's associated with GSAS-II
  * [GSAS-II installation tools](https://github.com/AdvancedPhotonSource/GSAS-II-buildtools) that includes [downloads](https://github.com/AdvancedPhotonSource/GSAS-II-buildtools/releases/latest) as well as [automated build/test scripts](https://github.com/AdvancedPhotonSource/GSAS-II/actions)
  and
  * [GSAS-II web content](https://github.com/AdvancedPhotonSource/GSAS-II-tutorials) that includes [tutorials](https://advancedphotonsource.github.io/GSAS-II-tutorials/tutorials.html).

* Code documentation: https://gsas-ii.readthedocs.io and scripting documentation: https://gsas-ii-scripting.readthedocs.io (subset of full documentation)

* Tutorial videos: [GSAS-II YouTube playlist](https://www.youtube.com/playlist?list=PLY1mvsJYSk7GBSsS4LqaU3inJHP0AzqqE)

* Releases (installers) for the lastest stable version and binary builds can be downloaded
  [here](https://github.com/AdvancedPhotonSource/GSAS-II-buildtools/releases/latest).

* The GSAS-II community uses [GitHub Discussions](https://github.com/AdvancedPhotonSource/GSAS-II/discussions).
  The [previous mailing list](http://lists.csn.ornl.gov/mailman/listinfo/gsas-list/) is now read-only.

## Installation
Installation is simple (see the Installation documentation at the [GSAS-II home page](https://advancedphotonsource.github.io/GSAS-II-tutorials/install.html))
for more details:

* first install Python if needed (see [Python](https://www.python.org/) or use
  the [Anaconda distribution](https://www.anaconda.com/download/)).
* Download installer, save into a folder that can be written and run it:
  * Windows: [GSAS-II-win64.exe](https://github.com/AdvancedPhotonSource/GSAS-II-buildtools/releases/latest)
  * Mac: [GSAS-II-mac.dmg](https://github.com/AdvancedPhotonSource/GSAS-II-buildtools/releases/latest)
  * Linux: [GSAS-II-linux.py](https://github.com/AdvancedPhotonSource/GSAS-II-buildtools/releases/latest)

## Quick Start
After installation, the GSAS-II GUI is started with the `GSAS-II` icon
(or the `gsas2` command)
created in the folder where the installer is downloaded. Get started with data
analysis with the [tutorials](https://advancedphotonsource.github.io/GSAS-II-tutorials/tutorials.html).

If you wish to use the scriptable (non-GUI) interface, see the
[scripting documentation](https://gsas-ii-scripting.readthedocs.io).
