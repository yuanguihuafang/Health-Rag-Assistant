# 模板初始化脚本（新单纯净项目）

脚本路径：
- `scripts/init_clean_project.ps1`

用途：
- 从当前工程一键生成“新单独立项目目录”
- 自动排除 `node_modules / venv / .venv / .git`
- 默认对旧本地业务 App 做“物理剔除”（`amazon_store_assistant / health_rag_assistant / java_refactor_assistant`）
- 自动清理关键配置中的注释化遗留代码（不再采用“注释停用”）
- 支持可选关闭前端残留功能：`user-profile / theme-runtime / admin-user-dropdown`
- 自动替换系统品牌文案（登录页、用户端标题、浏览器标签后缀）
- 可选初始化 Git 仓库

## 1. 最常用命令（纯净新项目）

```powershell
& D:\hertz_studio_django\scripts\init_clean_project.ps1 `
  -ProjectNameCn "基于DeepSeek的红色文化数字化传承系统" `
  -ProjectSlug "deepseek_red_culture" `
  -OutputRoot "D:\hertz_project_inits"
```

## 2. 保留某个本地 App（可选）

例如保留亚马逊模块：

```powershell
& D:\hertz_studio_django\scripts\init_clean_project.ps1 `
  -ProjectNameCn "亚马逊系统二开项目" `
  -ProjectSlug "amazon_rework" `
  -OutputRoot "D:\hertz_project_inits" `
  -EnableLocalApps @("amazon_store_assistant")
```

可选值：
- `amazon_store_assistant`
- `health_rag_assistant`
- `java_refactor_assistant`

## 3. 初始化 Git（可选）

```powershell
& D:\hertz_studio_django\scripts\init_clean_project.ps1 `
  -ProjectNameCn "基于DeepSeek的红色文化数字化传承系统" `
  -ProjectSlug "deepseek_red_culture" `
  -OutputRoot "D:\hertz_project_inits" `
  -InitGit `
  -GitRemote "https://github.com/your-org/your-repo.git"
```

## 3.1 关闭可选残留功能（可选）

例如关闭个人信息页、主题运行时、管理端右上角用户下拉：

```powershell
& D:\hertz_studio_django\scripts\init_clean_project.ps1 `
  -ProjectNameCn "你的项目名" `
  -ProjectSlug "your_project_slug" `
  -OutputRoot "D:\hertz_project_inits" `
  -DisableOptionalFeatures @("user-profile","theme-runtime","admin-user-dropdown")
```

## 4. 使用 PAT 自动创建 GitHub 仓库并推送（推荐）

```powershell
& D:\hertz_studio_django\scripts\init_clean_project.ps1 `
  -ProjectNameCn "基于DeepSeek的红色文化数字化传承系统" `
  -ProjectSlug "deepseek_red_culture" `
  -OutputRoot "D:\hertz_project_inits" `
  -InitGit `
  -GitUserName "Xandor" `
  -GitUserEmail "1253901211@qq.com" `
  -CreateGitHubRepo `
  -GitHubOwner "XXXws" `
  -GitHubVisibility "private" `
  -GitDefaultBranch "main" `
  -GitHubPAT "你的PAT"
```

说明：
- 未指定 `-GitHubRepoName` 时，默认使用 `ProjectNameCn` 作为仓库名（支持中文）。
- 推送时使用 PAT 临时认证，脚本会把 `origin` 设置为不含 token 的干净地址。
- 若仓库已存在，会自动复用该仓库并继续推送。

## 5. 参数说明

- `-ProjectNameCn`：项目中文名称（必填）
- `-ProjectSlug`：目录标识（必填，建议英文小写）
- `-OutputRoot`：输出根目录，默认 `D:\hertz_projects`
- `-MachineCode`：预留参数（默认 `DFF8C67EE163D083`）
- `-LoginBadge`：登录页左侧徽标文案
- `-LoginWelcomeTitle`：登录页欢迎标题
- `-LoginDescription`：登录页说明文案
- `-BrowserHomeTitle`：用户首页路由标题（默认 `用户首页`）
- `-EnableLocalApps`：需要保留启用的本地 App 列表
- `-DisableOptionalFeatures`：可选关闭的前端残留功能，支持：
  - `user-profile`：用户个人信息页（`/user/profile`）及对应页面文件
  - `theme-runtime`：`main.ts` 中主题运行时加载逻辑
  - `admin-user-dropdown`：管理端右上角用户下拉入口
- `-InitGit`：是否初始化 Git 仓库
- `-GitRemote`：远程仓库地址（与 `-InitGit` 配合）
- `-GitUserName`：Git 提交用户名（建议填写）
- `-GitUserEmail`：Git 提交邮箱（建议填写）
- `-CreateGitHubRepo`：是否通过 GitHub API 自动建仓并推送
- `-GitHubOwner`：GitHub 用户名或组织名
- `-GitHubPAT`：PAT（需具备仓库管理与内容写入权限）
- `-GitHubVisibility`：`private/public`
- `-GitHubRepoName`：仓库名（可选，不填默认用 `ProjectNameCn`）
- `-GitDefaultBranch`：默认分支，默认 `main`

## 6. 结果检查建议

生成后建议检查：
1. 后端目录中不应再出现 `amazon_store_assistant / health_rag_assistant / java_refactor_assistant`
2. `hertz_server_django/settings.py` 与 `hertz_server_django/urls.py` 不应有三套本地 app 残留
3. `hertz_server_django_ui/src` 中不应有 `amazon-store / health-rag / java-refactor` 关键词残留
4. `hertz_server_django_ui/src/router/index.ts` 浏览器标题后缀是否正确
5. `hertz_server_django_ui/src/views/Login.vue` 左侧文案是否正确
6. `hertz_server_django_ui/src/config/hertz_modules.ts` 的 `LOCAL_STORAGE_KEY` 是否已带项目 slug
