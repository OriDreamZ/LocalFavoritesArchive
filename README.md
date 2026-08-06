# Local Favorites Archive

把你自己的 X 账号中可访问的“喜欢”推文保存到本地，包括完整可见文本、作者、发布时间、原始链接、图片和视频。互动数量不会保存。

## 安装与启动

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
local-favorites serve
```

打开 `http://127.0.0.1:8765` 查看本地归档。同步使用你日常已经登录对应 X 账号的 Chrome，不会启动带有 `--no-sandbox` 的自动化浏览器：

1. 在 Chrome 打开 `chrome://extensions`，启用“开发者模式”。
2. 点击“加载已解压的扩展程序”，选择本项目的 `extension` 目录。
3. 在同一个 Chrome 中打开自己的 `https://x.com/<用户名>/likes` 页面。
4. 点击工具栏中的 Local Favorites Archive 扩展，再点击“开始同步”。
5. Chrome 会显示当前标签页正在被调试，这是扩展读取 Likes 网络响应所必需的提示；扩展只接受当前 X Likes 标签页。
6. 扩展滚动到当前可访问内容末尾后会自动停止，并通知本地服务下载图片和视频。

归档默认保存到 `archive/`。通过 `--archive D:\path\to\archive` 可以指定其他位置。

## 重要限制

- 该工具使用浏览器自动化，不使用 X 官方付费 API。X 页面或内部响应结构改版后，采集适配器可能需要更新。
- 只能归档账号当时可访问且 Likes 时间线实际返回的内容。被删除、取消喜欢、受限或被平台截断的历史内容无法保证获取。
- 遇到登录验证、异常活动提示或访问限制时，程序会暂停，不会绕过验证机制。
- 请仅用于归档你有权访问的内容，并自行确认适用的服务条款和当地法律。

## 命令

```powershell
local-favorites init
local-favorites retry-media
local-favorites serve --port 8765
```
