# GSAS2-MCP 🧪🤖

**AI-Agent-Friendly MCP Server for GSAS-II — Rietveld Refinement & Crystallographic Analysis**

[![License](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)]()
[![MCP Protocol](https://img.shields.io/badge/MCP-1.0+-green.svg)](https://modelcontextprotocol.io)

GSAS2-MCP 将功能强大的晶体学精修软件 [GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) 封装为标准的 **MCP (Model Context Protocol)** 服务器，使 AI 智能体（Claude、Copilot、Cursor 等）和自动化工作流可以直接调用 Rietveld 精修、物相分析、数据导入等全部功能。

GSAS2-MCP wraps the powerful crystallographic refinement engine [GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) as a standard **MCP (Model Context Protocol)** server, enabling AI agents (Claude, Copilot, Cursor, etc.) and automated workflows to directly invoke Rietveld refinement, phase analysis, data import, and more.

---

## 项目目的 / Purpose

本仓库是 **GSAS-II 的 fork + MCP 包装**，在保持与上游 [AdvancedPhotonSource/GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) 完全同步的基础上增加了：

This repository is a **GSAS-II fork + MCP wrapper** that adds the following on top of keeping fully synced with upstream:

| 特性 | 说明 |
|------|------|
| 🧩 **MCP 协议服务** | 通过 stdio/SSE 将 15+ GSAS-II 操作暴露为 MCP 工具 |
| 🤖 **AI 智能体接口** | AI 可直接创建项目、导入数据、设置参数、执行精修、诊断结果 |
| ⚙️ **Headless 运行** | 无需 wxPython GUI，纯 Python CLI 操作 |
| 🏗️ **预编译扩展** | Python 3.11 的 8 个 Fortran `.so` 扩展，开箱即用 |
| 🔧 **编译器缺失 fallback** | GSASIIobj.py P1SGData 回退，无 Fortran 编译器也可用 |
| 🧪 **完整测试覆盖** | 41 个 MCP 集成测试全部通过 |

**本仓库是 [gsas2-mcp-server](https://github.com/XRDFPSR/gsas2-mcp-server) 的运行时依赖。** 两者配合使用：

```
AI Agent (Claude/Copilot)
        │ MCP stdio/SSE
        ▼
┌───────────────────┐     import      ┌──────────────────┐
│ gsas2-mcp-server  │ ──────────────→ │   GSAS2-MCP      │
│ (MCP 协议层)       │                 │  (GSAS-II 引擎)   │
└───────────────────┘                 └──────────────────┘
```

---

## 代码结构 / Code Structure

```
GSAS2-MCP/
├── GSASII/                              # 🎯 核心 Python 包 (GSAS-II 引擎)
│   ├── GSASII.py                        # GUI 入口
│   ├── GSASIIobj.py                     # 🔥 P1SGData fallback 修复
│   ├── GSASIIscriptable.py              # 脚本 API (MCP 服务器依赖)
│   ├── GSASIIpath.py                    # 路径/二进制管理
│   ├── GSASIIstrIO.py                   # 精修 I/O
│   ├── GSASIIstrMath.py                 # 精修计算引擎
│   ├── GSASIIlattice.py                 # 晶格参数计算
│   ├── GSASIIspc.py                     # 空间群运算
│   ├── GSASIImapvars.py                 # 约束/限制管理
│   ├── imports/                         # 数据导入器 (30+ 格式)
│   │   ├── G2phase_CIF.py               # CIF 物相导入
│   │   ├── G2img_*.py                   # 图像导入
│   │   └── ...                          # 30+ 导入器
│   ├── exports/                         # 数据导出器
│   ├── *.cpython-311-x86_64-linux-gnu.so # ✅ 预编译 Fortran 扩展
│   └── ...                              # 100+ 模块
├── sources/                             # 🔧 Fortran/C 源码
│   ├── pyspg.for                        # 空间群计算模块
│   ├── pypowder.for                     # 粉末衍射计算
│   ├── pytexture.for                    # 织构计算
│   ├── pydiffax.for                     # DIFFaX 衍射
│   ├── pack_f.for / unpack_cbf.for      # 图像解包
│   ├── histogram2d.for                  # 2D 直方图
│   ├── fmask.c                          # 图像掩膜
│   ├── spsubs/                          # 空间群辅助 (sgroupnp 等)
│   ├── powsubs/                         # 粉末计算辅助
│   ├── texturesubs/                     # 织构计算辅助
│   ├── NISTlatsubs/                     # NIST 晶格辅助
│   └── meson.build                      # Meson 构建配置
├── tests/                               # 测试数据
│   └── testinp/                         # PbSO4 测试数据
└── build/                               # 构建输出 (cp313)
```

### 模块依赖关系 / Module Dependencies

```
GSASIIscriptable (MCP 入口)
    │
    ├── GSASIIobj        — 数据结构 (Phase, Histogram, G2VarObj)
    ├── GSASIIstrIO      — 精修 I/O (读取/写入项目文件)
    ├── GSASIIstrMath    — 精修数学引擎
    ├── GSASIIlattice    — 晶格参数
    ├── GSASIIspc        — 空间群运算 (依赖 pyspg.so)
    ├── GSASIImapvars    — 约束引擎
    └── imports/         — 数据导入器
        └── G2phase_CIF  — CIF 导入
```

---

## 编译方法 / Compilation

### 前置条件 / Prerequisites

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Python 3.10+ | 运行时 | `apt install python3.11` 或 conda |
| numpy | 数值计算 | `pip install numpy` |
| scipy | 科学计算 | `pip install scipy` |
| matplotlib | 绘图 | `pip install matplotlib` |
| wxPython | GUI (可选) | `pip install wxpython` |
| **gfortran** | 编译扩展 (可选) | conda-forge 或系统包管理器 |
| **meson** / ninja | 编译系统 (可选) | `pip install meson ninja` |

### 编译全部 Fortran 扩展 / Compile All Extensions

**方法一：使用 meson（推荐）**

```bash
# 安装依赖
pip install meson ninja numpy

# 编译
cd sources
meson setup build
meson compile -C build
cp build/sources/*.so ../GSASII/
```

**方法二：手动编译（无 meson 环境）**

```bash
# 设置 gfortran（推荐 conda-forge 版本，无需 root）
micromamba create -y -p ./gfortran-env -c conda-forge gfortran_linux-64
export PATH="./gfortran-env/bin:$PATH"
export LD_LIBRARY_PATH="./gfortran-env/lib"

cd sources

# 编译辅助库
gfortran -fPIC -O2 -c spsubs/*.for               # 空间群
gfortran -fPIC -O2 -c NISTlatsubs/*.f             # NIST 晶格
gfortran -fPIC -O2 -c powsubs/*.for powsubs/*.f90 # 粉末计算
gfortran -fPIC -O2 -c texturesubs/*.for           # 织构计算
gfortran -fPIC -O2 -c INCLDS/COPYRIGT.FOR         # 版权声明
gfortran -fPIC -O2 -c DIFFaXsubs/DIFFaXsubs.for   # DIFFaX

# 编译主模块
for mod in pyspg pypowder pytexture pydiffax pack_f unpack_cbf histogram2d; do
    gfortran -fPIC -O2 -c ${mod}.for -o ${mod}.o
    gcc -fPIC -O2 -c ${mod}module.c -o ${mod}_mod.o
    [ -f "${mod}-f2pywrappers.f" ] && \
        gfortran -fPIC -O2 -c ${mod}-f2pywrappers.f -o ${mod}_wrap.o
done
gcc -fPIC -O2 -c fortranobject.c -o fortranobject.o
gcc -fPIC -O2 -c fmask.c -o fmask.o

# 链接
gfortran -shared -o pyspg.cpython-311-x86_64-linux-gnu.so *.o -lm
cp *.cpython-311-x86_64-linux-gnu.so ../GSASII/

# fmask (纯 C)
gcc -shared -o fmask.cpython-311-x86_64-linux-gnu.so fmask.o -lm
cp fmask.cpython-311-x86_64-linux-gnu.so ../GSASII/
```

### 验证安装 / Verify Installation

```bash
python3 -c "
import sys, os
sys.path.insert(0, '.')
os.environ['GSASII_HEADLESS'] = 'true'
from GSASII import GSASIIpath
GSASIIpath.SetBinaryPath()
from GSASII import pyspg, pypowder, pytexture
print(f'✅ pyspg loaded: {len(dir(pyspg))} functions')
print(f'✅ pypowder loaded')
print(f'✅ pytexture loaded')
"
```

---

## MCP 服务器集成 / MCP Server Integration

### 关联项目 / Related Project

MCP 服务器代码位于独立仓库 [gsas2-mcp-server](https://github.com/XRDFPSR/gsas2-mcp-server)，依赖本仓库的 GSAS-II Python 包。

### 安装 MCP 服务器

```bash
git clone https://github.com/XRDFPSR/gsas2-mcp-server.git
cd gsas2-mcp-server
pip install -r requirements.txt

# 确保 GSAS2-MCP 在 Python 路径
export PYTHONPATH=/path/to/GSAS2-MCP:$PYTHONPATH
```

### 启动服务器

```bash
# stdio 模式 (默认，用于 Claude Desktop / Cursor)
python -m gsas2_mcp_server

# SSE HTTP 模式
python -m gsas2_mcp_server --transport sse --port 8910
```

### MCP 工具清单 (15 个)

| 类别 | 工具 | 功能 |
|------|------|------|
| **项目管理** | `create_project` | 创建新的 .gpx 项目 |
| | `load_project` | 加载已有 .gpx 项目 |
| | `project_summary` | 获取项目结构化摘要 |
| | `save_project` | 保存项目 |
| **数据导入** | `add_powder_histogram` | 添加粉末衍射数据 |
| | `add_phase` | 从 CIF 添加物相 |
| | `add_image` | 添加 2D 探测器图像 |
| | `load_data` | 加载衍射数据 (摘要) |
| **精修控制** | `set_refinement` | 设置精修参数 (支持缩写名自动映射) |
| | `refine` | 执行 Rietveld 精修 |
| | `get_results` | 解析精修结果 (Rwp, GOF, 晶胞参数) |
| | `hold_variable` | 固定参数 |
| | `free_variable` | 释放参数 |
| **智能诊断** | `auto_diagnose` | 自动诊断 + 修复建议 |
| | `suggest_best_strategy` | 推荐增量精修策略 |
| | `generate_report` | 生成精修报告 (Markdown/HTML/JSON) |
| **可视化** | `generate_plot` | 生成精修拟合图 (PNG/SVG) |

### Claude Desktop 配置

```json
{
  "mcpServers": {
    "gsas2-mcp": {
      "command": "python3",
      "args": ["-m", "gsas2_mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/GSAS2-MCP"
      }
    }
  }
}
```

### 快速功能测试

```python
import sys, os
sys.path.insert(0, "/path/to/GSAS2-MCP")
os.environ["GSASII_HEADLESS"] = "true"
os.environ["MPLBACKEND"] = "Agg"

from GSASII import GSASIIscriptable as G2sc

# 创建项目
gpx = G2sc.G2Project(newgpx="/tmp/test.gpx")

# 导入粉末衍射数据
hist = gpx.add_powder_histogram(
    "tests/testinp/PBSO4.XRA",
    iparams="tests/testinp/INST_XRY.PRM"
)

# 添加物相 (CIF)
phase = gpx.add_phase("tests/testinp/PbSO4-Wyckoff.cif", histograms=[hist.name])

# 设置精修参数
gpx.set_refinement({"set": {"Background": True, "Scale": True}})

# 执行精修
results = gpx.refine()
print(f"Rwp = {results.get('Rwp', 'N/A')}")
```

---

## 二进制支持 / Binary Support

| 模块 | 描述 | Python 3.11 | Python 3.13 |
|------|------|-------------|-------------|
| `pyspg` | 空间群运算 | ✅ 预编译 | ✅ 上游 meson |
| `pypowder` | 粉末衍射计算 | ✅ 预编译 | ✅ 上游 meson |
| `pytexture` | 织构计算 | ✅ 预编译 | ✅ 上游 meson |
| `pydiffax` | DIFFaX 衍射 | ✅ 预编译 | ✅ 上游 meson |
| `pack_f` | 图像打包 | ✅ 预编译 | ✅ 上游 meson |
| `unpack_cbf` | CBF 解包 | ✅ 预编译 | ✅ 上游 meson |
| `histogram2d` | 2D 直方图 | ✅ 预编译 | ✅ 上游 meson |
| `fmask` | 图像掩膜 | ✅ 预编译 | ✅ 上游 meson |

编译环境：conda-forge gfortran 15.2.0, Debian 12 (bookworm)

---

## 本 Fork 的变更 / Changes vs Upstream

| 变更 | 文件 | 说明 |
|------|------|------|
| P1SGData fallback | `GSASII/GSASIIobj.py` | 无 `pyspg` 时提供最小 P1 SGData 字典 |
| Python 3.11 二进制 | `GSASII/*.cpython-311-*.so` | 8 个扩展模块预编译 |
| 重命名为 GSAS2-MCP | — | GSAS-II → GSAS2-MCP |
| README 更新 | `README.md` | 本文件 |

---

## 测试 / Testing

### GSAS2-MCP 核心测试

```bash
cd /path/to/GSAS2-MCP
python3 -c "
import sys, os
sys.path.insert(0, '.')
os.environ['GSASII_HEADLESS'] = 'true'
os.environ['MPLBACKEND'] = 'Agg'
from GSASII import GSASIIscriptable as G2sc

gpx = G2sc.G2Project(newgpx='/tmp/test.gpx')
hist = gpx.add_powder_histogram('tests/testinp/PBSO4.XRA',
    iparams='tests/testinp/INST_XRY.PRM')
phase = gpx.add_phase('tests/testinp/PbSO4-Wyckoff.cif',
    histograms=[hist.name])
print(f'✅ Project created with {phase.name}')
"
```

### MCP 服务器集成测试 (41 个)

```bash
cd /path/to/gsas2-mcp-server
pip install -r requirements.txt
export PYTHONPATH=/path/to/GSAS2-MCP:$PYTHONPATH
python -m pytest tests/ -v
```

输出示例：
```
41 passed in 27.40s  ✅
```

---

## 相关项目 / Related Projects

| 项目 | 说明 | 仓库 |
|------|------|------|
| **gsas2-mcp-server** | GSAS2-MCP 的 MCP 协议封装 | [XRDFPSR/gsas2-mcp-server](https://github.com/XRDFPSR/gsas2-mcp-server) |
| **FullProf-MCP** | FullProf Rietveld 精修 MCP 服务器 | [XRDFPSR/fullprof-app](https://github.com/XRDFPSR/fullprof-app) |
| **Profex-MCP** | Profex/BGMN XRD 分析 MCP 服务器 | [XRDFPSR/Profex-MCP](https://github.com/XRDFPSR/Profex-MCP) |
| **maud-mcp** | MAUD Rietveld 精修 MCP 服务器 | [XRDFPSR/maud](https://github.com/XRDFPSR/maud) |

---

## 许可证 / License

**BSD 3-Clause License**（与上游 GSAS-II 一致）

本仓库是 [AdvancedPhotonSource/GSAS-II](https://github.com/AdvancedPhotonSource/GSAS-II) 的 fork，所有上游贡献者的版权均保留。

---

## 致谢 / Acknowledgements

- **Advanced Photon Source, Argonne National Lab** — GSAS-II 开发团队
- **Bob B. Von Dreele** — GSAS-II 联合创始人
- **Brian H. Toby** — GSAS-II 联合创始人
- **Juan Rodríguez-Carvajal** — FullProf 作者
- **Nico B.** — Profex 作者
- **Luca Lutterotti** — MAUD 作者

---

*GSAS-II 文档: https://gsas-ii.readthedocs.io*
*GSAS-II 教程: https://advancedphotonsource.github.io/GSAS-II-tutorials*
