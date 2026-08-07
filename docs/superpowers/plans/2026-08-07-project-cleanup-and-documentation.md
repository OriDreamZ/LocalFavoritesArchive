# 项目清理与文档完善实施计划

> **供智能代理执行：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐项执行并用复选框跟踪进度。

**目标：** 清除项目内已有归档数据和可再生缓存，将程序恢复为空数据可运行状态，并建立完整的中文文档体系和 `GPL-3.0-or-later` 许可证声明。

**架构：** 不修改采集、存储或界面业务逻辑；以现有 CLI 初始化入口重建空归档。README 负责首次使用引导，六份长期文档分别约束功能、架构、界面、开发、数据和安全边界，历史过程文档继续保留。

**技术栈：** Python 3.11+、FastAPI、SQLite、Chrome Manifest V3 扩展、pytest、PowerShell、GNU GPL v3。

---

## 文件结构

- 修改 `pyproject.toml`：声明 GPL 许可证、README 和打包元数据。
- 修改 `README.md`：提供完整的中文项目介绍和使用手册。
- 新建 `LICENSE`：保存未经修改的 GNU GPL v3 官方英文法律文本；这是新增文件中唯一不采用中文正文的文件。
- 新建 `docs/FEATURES.md`：说明功能边界和主要工作流。
- 新建 `docs/ARCHITECTURE.md`：说明扩展、本地服务、存储和界面的协作关系。
- 新建 `docs/UI-DESIGN.md`：约束页面信息架构、交互和视觉规则。
- 新建 `docs/DEVELOPMENT.md`：说明开发环境、测试和变更规范。
- 新建 `docs/DATA-STORAGE.md`：说明数据库、媒体、去重、删除和备份规则。
- 新建 `docs/SECURITY-AND-LIMITATIONS.md`：说明隐私、安全、合规和平台限制。
- 新建 `tests/test_project_documentation.py`：验证许可证元数据、README 和长期文档完整性。
- 删除运行数据 `archive/` 后重新创建空数据库、`archive/raw/` 和 `archive/media/`；这些路径受 `.gitignore` 管理，不提交 Git。
- 删除 `.pytest_cache/`、`src/local_favorites_archive/__pycache__/`、`tests/__pycache__/`；保留 `.venv/` 内所有内容。

### 任务 1：记录基线并安全停止本地服务

**文件：**

- 检查：`archive/`
- 检查：`src/local_favorites_archive/cli.py`

- [ ] **步骤 1：确认工作区只包含已批准的设计与计划变更**

运行：

```powershell
git status --short --branch
git log -3 --oneline
```

预期：当前分支为 `main`；设计提交 `3bcd058` 存在；除本实施计划外没有意外修改。

- [ ] **步骤 2：记录归档绝对路径、文件数量和大小**

运行：

```powershell
$projectRoot = (Resolve-Path '.').Path
$archiveRoot = (Resolve-Path '.\archive').Path
if ((Split-Path -Parent $archiveRoot) -ne $projectRoot -or (Split-Path -Leaf $archiveRoot) -ne 'archive') { throw '归档目录不在项目根目录内' }
$files = Get-ChildItem -LiteralPath $archiveRoot -Recurse -File
[pscustomobject]@{ ProjectRoot = $projectRoot; ArchiveRoot = $archiveRoot; FileCount = $files.Count; Bytes = ($files | Measure-Object Length -Sum).Sum }
```

预期：`ArchiveRoot` 精确等于 `D:\MyCode\VibeCodingProjects\LocalFavoritesArchive\archive`，并显示清理前统计。

- [ ] **步骤 3：定位 8765 端口进程并确认属于本项目**

运行：

```powershell
$listeners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
$listeners | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" | Select-Object ProcessId,Name,CommandLine }
```

预期：没有监听进程，或命令行明确包含本项目路径及 `local-favorites`/`uvicorn`。若进程归属不明确，停止实施并报告，不结束该进程。

- [ ] **步骤 4：停止已确认属于本项目的服务**

重新执行归属检查，并只停止命令行同时包含项目根目录和本项目启动入口的进程：

```powershell
$projectRoot = (Resolve-Path '.').Path
$listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
$processes = @($listeners | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" })
$projectProcesses = @($processes | Where-Object {
  $_.CommandLine -like "*$projectRoot*" -and
  ($_.CommandLine -match 'local-favorites|uvicorn')
})
if ($processes.Count -ne $projectProcesses.Count) { throw '存在无法确认归属的 8765 监听进程，拒绝停止' }
$projectProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId }
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
```

预期：项目服务进程被停止，端口 8765 不再存在监听；如果没有监听进程，`$projectProcesses` 为空且不会停止任何其他程序。

- [ ] **步骤 5：审计根目录和已跟踪文件**

运行：

```powershell
Get-ChildItem -Force | Select-Object Name,Mode
git ls-files
```

预期：根目录只包含 Git 元数据、虚拟环境、归档、源码、测试、扩展、文档和项目配置；已跟踪文件均属于源码、测试、扩展、项目配置或保留的文档。`.venv/` 与 `archive/` 不在 Git 跟踪列表中，不删除现有历史设计和实施计划。

### 任务 2：用测试锁定许可证和项目元数据

**文件：**

- 新建：`tests/test_project_documentation.py`
- 修改：`pyproject.toml`
- 新建：`LICENSE`

- [ ] **步骤 1：新增会失败的许可证元数据测试**

用 `apply_patch` 新建 `tests/test_project_documentation.py`：

```python
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_project_declares_gpl_3_or_later() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["readme"] == "README.md"
    assert project["license"] == "GPL-3.0-or-later"
    assert "GNU General Public License v3 or later (GPLv3+)" in project["classifiers"]


def test_license_contains_complete_gpl_v3_markers() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert license_text.startswith("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007")
    assert "TERMS AND CONDITIONS" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text
    assert "How to Apply These Terms to Your New Programs" in license_text
```

- [ ] **步骤 2：运行测试并确认先失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_documentation.py -v
```

预期：因 `LICENSE` 不存在或 `project.license` 尚未声明而失败。

- [ ] **步骤 3：更新项目元数据**

用 `apply_patch` 将 `pyproject.toml` 的构建要求和 `[project]` 元数据更新为：

```toml
[build-system]
requires = ["setuptools>=77.0.3"]
build-backend = "setuptools.build_meta"

[project]
name = "local-favorites-archive"
version = "0.1.0"
description = "将当前账号可访问的 X 喜欢内容归档到本地并进行筛选管理"
readme = "README.md"
license = "GPL-3.0-or-later"
requires-python = ">=3.11"
classifiers = [
  "Development Status :: 3 - Alpha",
  "Environment :: Web Environment",
  "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
  "Operating System :: Microsoft :: Windows",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
]
```

保留现有 `dependencies`、测试依赖、pytest 配置和命令入口。

- [ ] **步骤 4：添加完整 GPL v3 官方许可证**

用 `apply_patch` 新建 `LICENSE`，内容逐字采用 GNU 发布的 `https://www.gnu.org/licenses/gpl-3.0.txt`，从 `GNU GENERAL PUBLIC LICENSE` 到 `How to Apply These Terms to Your New Programs` 全部保留，不添加非官方译文或额外条款。

- [ ] **步骤 5：运行许可证测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_documentation.py -v
```

预期：2 项测试通过。

- [ ] **步骤 6：提交许可证和元数据**

```powershell
git add pyproject.toml LICENSE tests/test_project_documentation.py
git commit -m "docs: license project under GPL-3.0-or-later"
```

### 任务 3：建立中文长期维护文档

**文件：**

- 修改：`tests/test_project_documentation.py`
- 新建：`docs/FEATURES.md`
- 新建：`docs/ARCHITECTURE.md`
- 新建：`docs/UI-DESIGN.md`
- 新建：`docs/DEVELOPMENT.md`
- 新建：`docs/DATA-STORAGE.md`
- 新建：`docs/SECURITY-AND-LIMITATIONS.md`

- [ ] **步骤 1：新增会失败的长期文档测试**

在 `tests/test_project_documentation.py` 追加：

```python
EXPECTED_DOCUMENTS = {
    "FEATURES.md": ("# 功能说明", "## 非目标"),
    "ARCHITECTURE.md": ("# 系统架构", "## 数据流"),
    "UI-DESIGN.md": ("# 界面设计规范", "## 可访问性"),
    "DEVELOPMENT.md": ("# 开发规范", "## 测试要求"),
    "DATA-STORAGE.md": ("# 数据存储规范", "## 备份与恢复"),
    "SECURITY-AND-LIMITATIONS.md": ("# 安全、隐私与限制", "## 已知限制"),
}


def test_long_term_documents_are_present_and_chinese() -> None:
    for filename, required_headings in EXPECTED_DOCUMENTS.items():
        content = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        assert all(heading in content for heading in required_headings)
        assert any("\u4e00" <= character <= "\u9fff" for character in content)
```

- [ ] **步骤 2：运行测试并确认文档缺失**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_documentation.py::test_long_term_documents_are_present_and_chinese -v
```

预期：因 `docs/FEATURES.md` 尚不存在而失败。

- [ ] **步骤 3：编写功能与架构文档**

使用 `apply_patch` 新建：

- `docs/FEATURES.md`：包含“项目范围、采集与同步、本地归档、浏览与排序、媒体查看、标签管理、删除与去重、功能边界、非目标”。明确不保存互动计数、不使用官方收费 API、仅处理当前账号可访问的 Likes 内容。
- `docs/ARCHITECTURE.md`：包含“组件、数据流、扩展职责、本地服务职责、持久化层、媒体下载、接口边界、错误处理、启动与关闭”。用 Mermaid 流程图表达 `X Likes 页面 -> Chrome 扩展 -> FastAPI -> SQLite/文件 -> 本地界面`，图中文字使用中文。

- [ ] **步骤 4：编写界面与开发规范**

使用 `apply_patch` 新建：

- `docs/UI-DESIGN.md`：包含“设计目标、信息架构、总览、我的收藏、同步中心、标签管理、筛选与分页、图片查看器、状态反馈、排版与数字字体、响应式、可访问性、界面变更检查表”。明确上下两套分页保持同步、标签操作保持页码和当前位置、日期统一为年月日、长图初始居中且支持缩放旋转。
- `docs/DEVELOPMENT.md`：包含“环境要求、安装、运行、目录职责、编码规范、测试要求、文档要求、提交规范、功能变更检查表、发布前检查”。明确 Python 文件遵循现有类型和命名方式、前端不引入无必要框架、所有新增长期文档使用中文。

- [ ] **步骤 5：编写数据与安全限制文档**

使用 `apply_patch` 新建：

- `docs/DATA-STORAGE.md`：包含“默认目录、数据库表、原始响应、媒体文件、推文主键、去重规则、连续已有停止阈值、链接保存规则、删除语义、持久化、备份与恢复、彻底清空”。明确推文 ID 为主键、媒体链接在本地展示正文中移除但正文普通链接保留、永久删除不可恢复。
- `docs/SECURITY-AND-LIMITATIONS.md`：包含“使用边界、本地隐私、浏览器权限、访问控制、平台兼容风险、网络与媒体风险、数据删除风险、已知限制、问题报告注意事项”。明确不绕过登录验证、访问控制和反滥用机制，不承诺完整获取平台未返回的历史内容。

- [ ] **步骤 6：验证文档并提交**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_documentation.py -v
git diff --check
```

预期：3 项测试通过；`git diff --check` 无输出。

提交：

```powershell
git add docs/FEATURES.md docs/ARCHITECTURE.md docs/UI-DESIGN.md docs/DEVELOPMENT.md docs/DATA-STORAGE.md docs/SECURITY-AND-LIMITATIONS.md tests/test_project_documentation.py
git commit -m "docs: add Chinese project documentation"
```

### 任务 4：重写中文 README

**文件：**

- 修改：`tests/test_project_documentation.py`
- 修改：`README.md`

- [ ] **步骤 1：新增会失败的 README 完整性测试**

在 `tests/test_project_documentation.py` 追加：

```python
def test_readme_covers_setup_usage_storage_and_license() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required_sections = (
        "## 项目简介",
        "## 功能概览",
        "## 运行环境",
        "## 安装",
        "## 启动与初始化",
        "## 加载 Chrome 扩展",
        "## 同步收藏",
        "## 本地浏览与管理",
        "## 数据存储与备份",
        "## 常见问题",
        "## 开发与测试",
        "## 项目结构",
        "## 使用限制与免责声明",
        "## 开源许可证",
    )
    assert all(section in readme for section in required_sections)
    assert "GPL-3.0-or-later" in readme
    assert "http://127.0.0.1:8765" in readme
```

- [ ] **步骤 2：运行测试并确认旧 README 不完整**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_documentation.py::test_readme_covers_setup_usage_storage_and_license -v
```

预期：因旧 README 缺少要求的章节而失败。

- [ ] **步骤 3：完整重写 README**

使用 `apply_patch` 重写 `README.md`，按测试中的章节顺序提供中文说明，并确保：

- 项目名称和首段直接说明它是非官方、仅本地运行的 X Likes 归档工具。
- 安装命令使用 PowerShell：创建 `.venv`、激活环境、执行 `python -m pip install -e ".[test]"`。
- 说明 `local-favorites init`、`local-favorites serve`、`local-favorites retry-media`、`--archive` 和 `--port`。
- 说明使用已登录目标账号的 Google Chrome 手动加载 `extension/`，不使用 Edge 或 `--no-sandbox` 自动化浏览器。
- 描述开始同步、同步/媒体进度、连续 N 条已有内容停止条件，以及 N=0 时禁用限制。
- 描述总览、收藏筛选排序、文本/图片/视频过滤、分页、标签、图片缩放旋转、单条和批量删除。
- 说明默认 `archive/` 内容、备份需停止服务、恢复时保持目录结构，以及清空数据的不可恢复性。
- 提供端口占用、扩展无法连接、未捕获响应、媒体下载失败和平台页面变化的排查入口。
- 链接六份中文长期文档和历史设计目录。
- 明确 Python 3.11+、Windows 与 Google Chrome 为当前主要支持环境。
- 明确仅归档用户有权访问的内容，不绕过验证或访问限制，X 改版可能导致采集失效。
- 许可证章节标明 `GPL-3.0-or-later` 并链接根目录 `LICENSE`。

- [ ] **步骤 4：验证 README 并提交**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_project_documentation.py -v
git diff --check
```

预期：4 项测试通过；无空白错误。

提交：

```powershell
git add README.md tests/test_project_documentation.py
git commit -m "docs: rewrite Chinese README"
```

### 任务 5：清除全部归档并重建空数据状态

**文件：**

- 删除并重建：`archive/`

- [ ] **步骤 1：再次验证删除目标和服务状态**

运行：

```powershell
$projectRoot = (Resolve-Path '.').Path
$archiveRoot = (Resolve-Path '.\archive').Path
if ((Split-Path -Parent $archiveRoot) -ne $projectRoot -or (Split-Path -Leaf $archiveRoot) -ne 'archive') { throw '拒绝删除：目标不是项目内 archive 目录' }
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { throw '拒绝删除：本地服务仍在运行' }
Get-ChildItem -LiteralPath $archiveRoot -Force | Select-Object FullName,Length
```

预期：路径校验通过、8765 无监听，并列出待删除内容。

- [ ] **步骤 2：删除精确归档目录**

运行：

```powershell
Remove-Item -LiteralPath 'D:\MyCode\VibeCodingProjects\LocalFavoritesArchive\archive' -Recurse -Force
Test-Path -LiteralPath 'D:\MyCode\VibeCodingProjects\LocalFavoritesArchive\archive'
```

预期：`Test-Path` 输出 `False`。此操作会永久删除现有推文和约 1.07 GiB 媒体，不可恢复。

- [ ] **步骤 3：通过正式 CLI 重新初始化空归档**

运行：

```powershell
.\.venv\Scripts\local-favorites.exe init --archive .\archive
Get-ChildItem -LiteralPath .\archive -Recurse -Force | Select-Object FullName,Length
```

预期：显示“归档目录已初始化”；生成 `archive.sqlite3`、空 `raw/` 和空 `media/`。

- [ ] **步骤 4：验证所有业务表为空**

运行：

```powershell
@'
import sqlite3
from pathlib import Path

database = Path("archive/archive.sqlite3")
tables = ("posts", "media", "post_links", "sync_runs", "tags", "post_tags", "posts_fts")
with sqlite3.connect(database) as connection:
    counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
print(counts)
assert all(count == 0 for count in counts.values()), counts
assert connection is not None
assert not any(Path("archive/raw").iterdir())
assert not any(Path("archive/media").iterdir())
'@ | .\.venv\Scripts\python.exe -
```

预期：所有列出的表均为 `0`，两个媒体目录均为空。`archive_settings` 保留初始化默认值，不视为用户归档数据。

### 任务 6：清理可再生缓存并完成全量验证

**文件：**

- 删除：`.pytest_cache/`
- 删除：`src/local_favorites_archive/__pycache__/`
- 删除：`tests/__pycache__/`
- 保留：`.venv/`

- [ ] **步骤 1：删除项目范围内的可再生缓存**

运行：

```powershell
$targets = @(
  'D:\MyCode\VibeCodingProjects\LocalFavoritesArchive\.pytest_cache',
  'D:\MyCode\VibeCodingProjects\LocalFavoritesArchive\src\local_favorites_archive\__pycache__',
  'D:\MyCode\VibeCodingProjects\LocalFavoritesArchive\tests\__pycache__'
)
$projectRoot = (Resolve-Path '.').Path
foreach ($target in $targets) {
  $parent = Split-Path -Parent $target
  if (-not $target.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar)) { throw "缓存目标越界：$target" }
  if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
$targets | ForEach-Object { [pscustomobject]@{ Path = $_; Exists = Test-Path -LiteralPath $_ } }
```

预期：三个项目缓存路径的 `Exists` 均为 `False`；不遍历或删除 `.venv/`。

- [ ] **步骤 2：运行完整 Python 测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

预期：全部测试通过，无失败或错误。

- [ ] **步骤 3：检查扩展 JavaScript 语法**

运行：

```powershell
node --check extension\background.js
node --check extension\popup.js
node --check src\local_favorites_archive\static\app.js
```

预期：三个命令均退出码 0 且无语法错误。

- [ ] **步骤 4：启动服务并验证空状态接口**

运行：

```powershell
$service = Start-Process -FilePath '.\.venv\Scripts\local-favorites.exe' -ArgumentList @('serve','--archive','.\archive','--port','8765') -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
$status = Invoke-RestMethod http://127.0.0.1:8765/api/status
$status | ConvertTo-Json -Depth 5
```

预期：状态中的归档路径指向项目 `archive`，推文总数和媒体总数均为 `0`。

- [ ] **步骤 5：使用浏览器验证空状态页面**

打开 `http://127.0.0.1:8765`，确认：

- 总览统计均为零且没有残留作者、标签或媒体；
- “我的收藏”显示明确的空状态，不出现破损卡片；
- 同步中心显示项目内归档路径；
- 总览、我的收藏、同步中心和标签管理侧边栏均可切换；
- 浏览器控制台无页面初始化错误。

- [ ] **步骤 6：停止验证服务并检查最终状态**

运行：

```powershell
Stop-Process -Id $service.Id
git diff --check
git status --short --branch
```

预期：服务停止；`git diff --check` 无输出；工作区没有未提交的文档或源码变更。被忽略的 `archive/` 包含空初始化数据库和空媒体目录。

- [ ] **步骤 7：提交实施计划状态（如执行过程中更新了复选框）**

仅当实施过程中更新了本计划复选框时运行：

```powershell
git add docs/superpowers/plans/2026-08-07-project-cleanup-and-documentation.md
git commit -m "docs: record project cleanup execution"
```
