# Local Favorites Archive

## 项目简介

Local Favorites Archive 是一个非官方、本地优先的 X Likes 归档工具。它使用你已经登录目标账号的 Google Chrome，从账号自己的“喜欢”时间线中读取当前可访问的推文，并将正文、作者、发布时间、原始链接、图片和视频持久保存到本地。

程序不使用 X 官方收费 API，不将归档上传到第三方服务，也不会保存点赞数、转发数或回复数等互动统计。保存后的内容可以在本地页面中搜索、筛选、排序、分页、打标签和删除。

## 功能概览

- 保存推文 ID、正文、作者显示名称、`@账号名`、作者 ID、发布时间和 X 原始链接。
- 下载并本地展示图片与视频，记录媒体下载进度和失败原因。
- 保留正文中的普通链接，不把原始推文链接拼入正文，也不重复展示已本地化媒体的短链接。
- 以推文 ID 去重，重复同步不会重复保存推文或重复下载已完成媒体。
- 支持按关键词、图片、视频、纯文本、标签和日期范围筛选。
- 支持按发布时间、收藏时间和作者名称正序或逆序排列。
- 支持每页数量选择、上下双分页、页码按钮和指定页跳转。
- 支持本地标签创建、改名、改色、分配、移除和筛选。
- 支持图片大图查看、缩放、旋转和复位，长图首次打开保持居中。
- 支持单条和批量永久删除本地推文及其媒体。
- 支持连续遇到 N 条已有推文时自动停止同步；N 为 `0` 时不启用该限制。
- 总览、我的收藏、同步中心和标签管理使用独立页面区域。

完整功能边界参见 [功能说明](docs/FEATURES.md)。

## 运行环境

当前主要支持：

- Windows 10 或 Windows 11；
- Python 3.11 或更高版本；
- Google Chrome；
- 可访问 X 的网络环境；
- Node.js，可选，仅在开发时用于 JavaScript 语法检查。

目前的真实同步流程依赖 Chrome 扩展。Microsoft Edge 和其他 Chromium 浏览器没有作为主要支持环境验证。程序不会启动带 `--no-sandbox` 的自动化浏览器。

## 安装

在 PowerShell 中进入项目目录：

```powershell
cd D:\MyCode\VibeCodingProjects\LocalFavoritesArchive
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

如果 PowerShell 禁止运行激活脚本，可以不激活环境，直接使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

## 启动与初始化

首次运行先创建空归档：

```powershell
local-favorites init
```

启动本地服务：

```powershell
local-favorites serve
```

然后访问 [http://127.0.0.1:8765](http://127.0.0.1:8765)。服务默认只监听本机地址，不向局域网或公网开放。

如果没有激活虚拟环境，可以运行：

```powershell
.\.venv\Scripts\local-favorites.exe init
.\.venv\Scripts\local-favorites.exe serve
```

指定其他归档目录或端口：

```powershell
local-favorites serve --archive D:\XArchive --port 8766
```

扩展默认连接 `8765`。改变端口后，必须同步调整扩展配置或代码，否则扩展无法连接。

## 加载 Chrome 扩展

1. 在 Google Chrome 地址栏打开 `chrome://extensions`。
2. 打开右上角“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择本项目的 `extension` 目录。
5. 将 Local Favorites Archive 固定到浏览器工具栏，便于查看同步状态。

扩展权限包括当前标签页、Chrome 调试协议、页面脚本、本地扩展存储，以及访问 `x.com`、`twitter.com` 和本机服务。开始同步后 Chrome 会显示当前标签页正在被调试，这是读取 Likes 网络响应所需的正常提示。

更新扩展源码后，需要在 `chrome://extensions` 中点击该扩展的“重新加载”。

## 同步收藏

开始前确认本地服务正在运行，并在同一个 Chrome 中登录需要归档的 X 账号。

1. 打开自己的 Likes 页面，例如 `https://x.com/你的账号名/likes`。
2. 确认页面能正常显示喜欢的推文和媒体。
3. 点击工具栏中的 Local Favorites Archive 扩展。
4. 点击“开始同步”。
5. 保持 Likes 标签页打开。扩展会读取时间线响应并自动向下滚动。
6. 在本地页面“同步中心”查看推文采集进度、媒体下载进度和失败信息。
7. 等待自动完成，或从扩展手动停止同步。

### 连续已有停止条件

同步中心可以设置连续已有内容阈值：

- `50` 表示连续获取到 50 条本地已有推文后停止；
- 遇到一条新推文时，连续计数重新从零开始；
- `0` 表示禁用此条件，会持续采集到当前时间线末尾或手动停止。

无论阈值如何设置，数据库都以推文 ID 去重，已经成功保存的媒体不会重复下载。

### 重试失败媒体

停止服务后并非必须重试；媒体重试命令可以在服务未占用归档写入时执行：

```powershell
local-favorites retry-media
```

使用自定义归档目录时：

```powershell
local-favorites retry-media --archive D:\XArchive
```

## 本地浏览与管理

### 总览

查看推文总数、媒体数量与完整率、标签覆盖、作者和归档时间范围。空归档会显示零值，不生成示例内容。

### 我的收藏

- 在关键词框搜索正文、作者显示名称或 `@账号名`。
- 选择图片、视频或纯文本过滤内容。
- 使用标签、起始日期和截至日期缩小范围。
- 选择排序字段及正序或逆序。
- 在列表上方或下方切换页码，并选择每页显示数量。
- 点击图片打开查看器；使用工具栏缩放、旋转或复位。
- 点击原始链接返回 X 对应推文。

### 标签管理

标签只存在本地，不会写回 X。可以在“标签管理”中创建、重命名、改色或删除标签，也可以直接在推文卡片中添加和移除标签。删除标签不会删除推文。

### 删除本地内容

推文卡片支持单条删除，也可以进入多选状态后批量删除。删除会同时清理正文记录、普通链接、标签关联、原始响应和本地媒体，操作不可恢复。

如果被删除的推文仍然存在于账号 Likes 中，后续同步再次遇到它时会重新保存。

## 数据存储与备份

默认数据目录：

```text
archive/
├── archive.sqlite3   # 推文、作者、链接、标签、设置和同步记录
├── raw/              # 原始响应
└── media/            # 本地图片和视频
```

归档会跨服务重启持久保存。`archive/` 已被 Git 忽略，不应提交到版本库。

备份时先停止本地服务和扩展同步，再完整复制整个 `archive/`。不要只备份 SQLite 数据库，否则图片、视频和原始响应会丢失。恢复时将完整目录放回原位置，或通过 `--archive` 指向备份目录。

彻底清空数据的操作不可恢复。应先停止服务，确认路径后删除整个归档目录，再重新初始化：

```powershell
local-favorites init --archive .\archive
```

更详细的表结构、去重、链接、删除和恢复规则参见 [数据存储规范](docs/DATA-STORAGE.md)。

## 常见问题

### 页面无法打开

确认 `local-favorites serve` 仍在运行，并检查端口是否被占用：

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen
```

### 扩展提示无法连接本地服务

先在浏览器打开 `http://127.0.0.1:8765`。如果页面也无法打开，请重新启动服务；如果服务使用了其他端口，扩展默认仍会连接 `8765`。

### 无法登录或页面要求验证

使用日常登录账号的 Google Chrome 手动完成登录或验证。不要使用 Edge、无痕临时配置或带 `--no-sandbox` 的自动化浏览器。本项目不会绕过账号验证或访问限制。

### 页面有推文，但扩展没有捕获到内容

确认当前标签页确实是目标账号的 Likes 页面，并重新加载扩展后再试。X 的内部响应结构可能发生变化；此时需要更新采集解析器，而不是提高滚动频率或绕过平台限制。

### 推文已保存，但图片或视频缺失

在同步中心查看失败项并执行 `local-favorites retry-media`。来源媒体已经失效、需要额外权限或平台改变地址格式时，重试仍可能失败，但正文会继续保留。

### 修改标签后页码或位置变化

普通标签操作应保持当前页和当前位置。移除当前筛选使用的标签时，该推文不再符合筛选条件，列表会刷新并将页码调整到有效范围。

## 开发与测试

运行完整 Python 测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

检查 JavaScript 语法：

```powershell
node --check extension\background.js
node --check extension\popup.js
node --check src\local_favorites_archive\static\app.js
```

开发约束、测试分层和提交规范参见 [开发规范](docs/DEVELOPMENT.md)。系统组件和数据流参见 [系统架构](docs/ARCHITECTURE.md)，界面约束参见 [界面设计规范](docs/UI-DESIGN.md)。

## 项目结构

```text
LocalFavoritesArchive/
├── extension/                       # Chrome 扩展
├── src/local_favorites_archive/     # Python 应用
│   └── static/                      # 本地管理界面
├── tests/                           # 自动化测试
├── docs/                            # 中文长期文档和历史设计记录
├── archive/                         # 本地归档，不纳入 Git
├── pyproject.toml                   # 项目与依赖配置
├── LICENSE                          # GNU GPL v3 官方许可证
└── README.md
```

长期文档：

- [功能说明](docs/FEATURES.md)
- [系统架构](docs/ARCHITECTURE.md)
- [界面设计规范](docs/UI-DESIGN.md)
- [开发规范](docs/DEVELOPMENT.md)
- [数据存储规范](docs/DATA-STORAGE.md)
- [安全、隐私与限制](docs/SECURITY-AND-LIMITATIONS.md)
- [历史设计与实施记录](docs/superpowers/)

## 使用限制与免责声明

- 本项目不是 X 官方产品，与 X Corp. 没有关联或背书关系。
- 只能归档当前账号有权访问且 Likes 时间线实际返回的内容。
- 被删除、取消喜欢、受限或平台未返回的历史内容无法保证获取。
- 项目不绕过登录验证、访问控制、反自动化或反滥用机制。
- X 页面和内部响应不是稳定公开 API，平台改版可能导致采集部分或完全失效。
- 使用者应自行确认其归档、保存和使用内容的行为符合服务条款、版权要求和当地法律。
- 归档可能包含敏感个人数据。请保护本地磁盘、备份和浏览器登录环境，不要公开原始响应、Cookie 或数据库。

详细边界参见 [安全、隐私与限制](docs/SECURITY-AND-LIMITATIONS.md)。

## 开源许可证

本项目采用 **GNU General Public License v3.0 or later**，SPDX 标识为 `GPL-3.0-or-later`。

你可以在 GPL v3 或后续版本条款下使用、研究、修改和再分发本项目。分发修改版本时必须遵守相应的源代码公开和许可证保留义务。完整且具有约束力的条款以根目录 [LICENSE](LICENSE) 中的 GNU 官方英文文本为准。
