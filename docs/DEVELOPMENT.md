# 开发规范

## 环境要求

- Windows 10 或 Windows 11。
- Python 3.11 或更高版本。
- Google Chrome，用于扩展加载和真实同步测试。
- Node.js，仅用于对扩展和页面 JavaScript 执行语法检查。
- Git，用于版本管理。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

项目没有前端打包步骤。`src/local_favorites_archive/static/` 中的文件由 FastAPI 直接提供。

## 本地运行

```powershell
local-favorites init
local-favorites serve
```

默认访问地址为 `http://127.0.0.1:8765`，默认归档目录为项目下的 `archive/`。开发时如需隔离测试数据，应显式使用临时目录：

```powershell
local-favorites serve --archive .\archive-dev --port 8766
```

## 目录职责

- `src/local_favorites_archive/`：Python 应用、数据解析、存储、下载和 Web 服务。
- `src/local_favorites_archive/static/`：本地管理界面。
- `extension/`：Chrome Manifest V3 扩展。
- `tests/`：Python、接口、前端契约和扩展静态测试。
- `docs/`：长期维护文档与历史设计记录。
- `archive/`：被 Git 忽略的本地用户数据。

## 编码规范

- Python 代码遵循现有模块职责，使用明确类型、标准库路径对象和参数化 SQL。
- 解析外部响应时允许字段缺失，禁止无依据地猜测作者、正文或媒体。
- 文件操作必须从归档根目录解析并验证归属，不能信任数据库或请求传入的任意路径。
- 前端继续使用原生 HTML、CSS 和 JavaScript；除非功能复杂度明确需要，不引入构建系统或大型框架。
- 界面文案使用简洁中文，X、Chrome、SQLite 等产品或技术名称保留通用写法。
- 新增长期文档使用 UTF-8 中文；许可证法律正文保持 GNU 官方英文原文。
- 代码注释只解释不直观的约束和决策，不复述代码表面行为。

## 测试要求

涉及媒体重试时必须覆盖重试接口、下载锁互斥、`failed` 目标过滤、批量不受 200 条列表限制、单条 404 和前端按钮状态。重试接口应在异步路由中调用后台任务，并在测试中等待 `retrying` 变为完成或错误。

运行完整测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

检查 JavaScript 语法：

```powershell
node --check extension\background.js
node --check extension\popup.js
node --check src\local_favorites_archive\static\app.js
```

变更采集解析时，必须使用去标识化的最小响应样本覆盖成功和字段缺失情况。变更存储层时，测试必须使用 pytest 临时目录，不能读取或修改真实 `archive/`。变更界面时，应增加 HTML/JavaScript 契约测试，并在本地浏览器检查桌面和窄屏布局。

## 测试分层

多标签必须测试交集、并集、重复 ID、旧参数及列表/计数一致性；扩展必须测试刷新后网络响应采集、自动滚动、速度设置持久化和页面加载等待。局域网必须测试默认关闭、`--lan` 地址、完整管理权限和缺少客户端标记时的修改请求拒绝。

- `test_collector.py`：X 响应解析、正文链接和媒体提取。
- `test_storage.py`：数据库、查询、统计、去重、标签和删除。
- `test_web.py`：API、同步状态和前端行为契约。
- `test_extension.py`：扩展清单、权限和采集脚本契约。
- `test_config.py`：路径和配置默认值。
- `test_project_documentation.py`：许可证、项目元数据和长期文档完整性。

## 文档要求

- 新功能同时更新 `README.md` 的用户操作说明和对应长期文档。
- 数据格式或表结构变化更新 `DATA-STORAGE.md` 与 `ARCHITECTURE.md`。
- 页面结构或交互约束变化更新 `UI-DESIGN.md`。
- 权限、访问边界或已知风险变化更新 `SECURITY-AND-LIMITATIONS.md`。
- 历史设计和实施计划保存在 `docs/superpowers/`，不作为最终用户的必读入口。

## 提交规范

- 每个提交只包含一个可说明、可验证的主题。
- 使用 `feat:`、`fix:`、`test:`、`docs:`、`refactor:` 或 `chore:` 等简短前缀。
- 提交前运行相关测试和 `git diff --check`。
- 不提交 `archive/`、`.venv/`、缓存、浏览器资料、真实 X 响应或用户媒体。
- 不通过提交顺带格式化或改写与当前任务无关的文件。

## 功能变更检查表

1. 先写能复现需求或缺陷的失败测试。
2. 以最小改动实现行为，并保持现有接口兼容。
3. 运行目标测试和完整测试。
4. 对界面变更执行浏览器交互与响应式检查。
5. 更新用户文档和对应规范。
6. 检查 Git 差异中没有归档数据、凭据或无关文件。

## 发布前检查

- 所有 Python 测试通过。
- 三个 JavaScript 文件通过语法检查。
- 空归档可以初始化、启动和显示。
- Chrome 扩展可以连接默认端口，且权限没有无说明扩张。
- README 命令、端口、路径和功能与代码一致。
- `LICENSE` 与 `pyproject.toml` 均声明 `GPL-3.0-or-later`。
## 采集安全回归要求

扩展测试必须确认同步前刷新 Likes 页面，源码中不得重新引入 DOM 入库接口、DOM 推文批次或不刷新续采逻辑。下载器测试必须覆盖视频收到图片 MIME、图片收到视频 MIME、缩略图地址和空响应等情况，并确认失败记录包含可定位的推文信息。
