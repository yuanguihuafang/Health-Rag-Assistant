param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectNameCn,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-zA-Z][a-zA-Z0-9_-]{2,64}$")]
    [string]$ProjectSlug,

    [string]$OutputRoot = "D:\\hertz_projects",
    [string]$MachineCode = "DFF8C67EE163D083",
    [string]$LoginBadge = "PYTHON STUDIO",
    [string]$LoginWelcomeTitle = "欢迎使用",
    [string]$LoginDescription = "为业务功能开发与数据管理提供统一入口",
    [string]$BrowserHomeTitle = "用户首页",
    [string[]]$EnableLocalApps = @(),
    [ValidateSet("user-profile", "theme-runtime", "admin-user-dropdown")]
    [string[]]$DisableOptionalFeatures = @(),
    [switch]$InitGit,
    [string]$GitRemote = "",
    [string]$GitUserName = "",
    [string]$GitUserEmail = "",
    [ValidateSet("private", "public")]
    [string]$GitHubVisibility = "private",
    [string]$GitHubOwner = "",
    [string]$GitHubPAT = "",
    [string]$GitHubRepoName = "",
    [string]$GitDefaultBranch = "main",
    [switch]$CreateGitHubRepo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[init] $Message" -ForegroundColor Cyan
}

function Remove-RegexMatchesFromFile {
    param(
        [string]$FilePath,
        [string[]]$Patterns
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return
    }
    $content = Get-Content -LiteralPath $FilePath -Raw -Encoding UTF8
    $updated = $content
    foreach ($pattern in $Patterns) {
        if (-not $pattern) {
            continue
        }
        $updated = [regex]::Replace($updated, $pattern, "")
    }
    if ($updated -ne $content) {
        Set-Content -LiteralPath $FilePath -Value $updated -Encoding UTF8
    }
}

function Uncomment-MatchingLine {
    param(
        [string]$FilePath,
        [string]$ContainsText,
        [string]$CommentPrefix = "#"
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return
    }
    $lines = Get-Content -LiteralPath $FilePath -Encoding UTF8
    $changed = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        if (-not $line.Contains($ContainsText)) {
            continue
        }
        $pattern = "^\s*" + [regex]::Escape($CommentPrefix) + "\s*"
        if ($line -match $pattern) {
            $lines[$i] = $line -replace $pattern, "    "
            $changed = $true
        }
    }
    if ($changed) {
        Set-Content -LiteralPath $FilePath -Value $lines -Encoding UTF8
    }
}

function Remove-LinesContainingAny {
    param(
        [string]$FilePath,
        [string[]]$Needles
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return
    }
    $lines = Get-Content -LiteralPath $FilePath -Encoding UTF8
    $filtered = [System.Collections.Generic.List[string]]::new()
    $changed = $false
    foreach ($line in $lines) {
        $matched = $false
        foreach ($needle in $Needles) {
            if ($needle -and $line.Contains($needle)) {
                $matched = $true
                break
            }
        }
        if ($matched) {
            $changed = $true
            continue
        }
        [void]$filtered.Add($line)
    }
    if ($changed) {
        Set-Content -LiteralPath $FilePath -Value $filtered -Encoding UTF8
    }
}

function Remove-CommentOnlyLines {
    param(
        [string]$FilePath,
        [string[]]$CommentPrefixes
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return
    }
    $lines = Get-Content -LiteralPath $FilePath -Encoding UTF8
    $filtered = [System.Collections.Generic.List[string]]::new()
    $changed = $false
    foreach ($line in $lines) {
        $trimmed = $line.TrimStart()
        $isCommentLine = $false
        foreach ($prefix in $CommentPrefixes) {
            if ($prefix -and $trimmed.StartsWith($prefix)) {
                $isCommentLine = $true
                break
            }
        }
        if ($isCommentLine) {
            $changed = $true
            continue
        }
        [void]$filtered.Add($line)
    }
    if ($changed) {
        Set-Content -LiteralPath $FilePath -Value $filtered -Encoding UTF8
    }
}

function Remove-ObjectBlocksByMarkers {
    param(
        [string]$FilePath,
        [string[]]$Markers
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return
    }
    $lines = Get-Content -LiteralPath $FilePath -Encoding UTF8
    $changed = $false

    foreach ($marker in $Markers) {
        if (-not $marker) {
            continue
        }
        while ($true) {
            $markerIdx = -1
            for ($i = 0; $i -lt $lines.Count; $i++) {
                if ($lines[$i].Contains($marker)) {
                    $markerIdx = $i
                    break
                }
            }
            if ($markerIdx -lt 0) {
                break
            }

            $start = $markerIdx
            while ($start -gt 0) {
                $trimmed = $lines[$start].Trim()
                if ($trimmed -match '^(//\s*)?\{$') {
                    break
                }
                $start--
            }
            if ($lines[$start].Trim() -notmatch '^(//\s*)?\{$') {
                $start = $markerIdx
            }

            $end = $markerIdx
            while ($end -lt ($lines.Count - 1)) {
                $trimmed = $lines[$end].Trim()
                if ($trimmed -match '^(//\s*)?\},?\s*$') {
                    break
                }
                $end++
            }

            $head = @()
            $tail = @()
            if ($start -gt 0) {
                $head = $lines[0..($start - 1)]
            }
            if (($end + 1) -lt $lines.Count) {
                $tail = $lines[($end + 1)..($lines.Count - 1)]
            }
            $lines = @($head + $tail)
            $changed = $true
        }
    }

    if ($changed) {
        Set-Content -LiteralPath $FilePath -Value $lines -Encoding UTF8
    }
}

function Remove-PathIfExists {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Remove-LiteralFragmentsFromFile {
    param(
        [string]$FilePath,
        [string[]]$Fragments
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return
    }
    $content = Get-Content -LiteralPath $FilePath -Raw -Encoding UTF8
    $updated = $content
    foreach ($fragment in $Fragments) {
        if (-not $fragment) {
            continue
        }
        $updated = $updated.Replace(",$fragment", "")
        $updated = $updated.Replace("$fragment,", "")
        $updated = $updated.Replace($fragment, "")
    }
    if ($updated -ne $content) {
        Set-Content -LiteralPath $FilePath -Value $updated -Encoding UTF8
    }
}

function Write-CleanUserIndexTemplate {
    param([string]$FilePath)
    $content = @'
<template>
  <div class="user-home-page">
    <header class="brand-header">
      <span class="logo-text">Hertz Studio Template</span>
    </header>
    <main class="home-content">
      <h1>用户首页</h1>
      <p>当前为纯净模板环境，请按需新增本地 APP 模块并接入菜单与路由。</p>
    </main>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.user-home-page {
  min-height: calc(100vh - 80px);
  padding: 40px 32px;
  background: #f3f6fb;
}

.brand-header {
  margin-bottom: 20px;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #1f3f75;
}

.home-content {
  background: #fff;
  border-radius: 12px;
  padding: 28px;
  border: 1px solid #e6ebf2;
}

.home-content h1 {
  margin: 0 0 12px;
  font-size: 28px;
  color: #1d3557;
}

.home-content p {
  margin: 0;
  color: #4e5f78;
  font-size: 15px;
  line-height: 1.7;
}
</style>
'@
    Set-Content -LiteralPath $FilePath -Value $content -Encoding UTF8
}

function Remove-ComponentEntriesByNames {
    param(
        [string]$FilePath,
        [string[]]$ComponentNames
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return
    }
    $patterns = @()
    foreach ($componentName in $ComponentNames) {
        if (-not $componentName) {
            continue
        }
        $escaped = [regex]::Escape($componentName)
        $patterns += "(?ms)^\s*`"$escaped`":\s*defineAsyncComponent\(\s*\r?\n\s*\(\)\s*=>\s*import\(`"@/views/(?:user_pages|admin_page)/$escaped`"\),\s*\r?\n\s*\),\s*\r?\n"
        $patterns += "(?ms)^\s*`"$escaped`":\s*\(\)\s*=>\s*\r?\n\s*import\(`"@/views/(?:user_pages|admin_page)/$escaped`"\),\s*\r?\n"
        $patterns += "(?m)^\s*`"$escaped`":\s*\(\)\s*=>\s*import\(`"@/views/(?:user_pages|admin_page)/$escaped`"\),\s*\r?\n"
    }
    if ($patterns.Count -gt 0) {
        Remove-RegexMatchesFromFile -FilePath $FilePath -Patterns $patterns
    }
}

function Normalize-RepoName {
    param([string]$RawName)
    $name = ($RawName ?? "").Trim()
    if (-not $name) {
        return ""
    }
    $name = $name -replace "\s+", "-"
    $name = $name -replace "[\\/:*?""<>|#%]+", "-"
    $name = $name.Trim(".")
    return $name
}

function Invoke-GitHubApi {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [string]$PAT,
        [object]$Body = $null
    )
    $headers = @{
        "Accept" = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "hertz-template-init-script"
    }
    if ($PAT -and $PAT.Trim().Length -gt 0) {
        $headers["Authorization"] = "Bearer $PAT"
    }
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers
    }
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -Body ($Body | ConvertTo-Json -Depth 10) -ContentType "application/json"
}

function Ensure-GitHubRepo {
    param(
        [string]$Owner,
        [string]$RepoName,
        [string]$Visibility,
        [string]$PAT,
        [string]$Description
    )

    if (-not $Owner) { throw "CreateGitHubRepo=true 时必须提供 GitHubOwner" }
    if (-not $PAT) { throw "CreateGitHubRepo=true 时必须提供 GitHubPAT" }
    if (-not $RepoName) { throw "CreateGitHubRepo=true 时必须提供有效 GitHubRepoName/ProjectNameCn" }

    $ownerInfo = Invoke-GitHubApi -Method "GET" -Url "https://api.github.com/users/$Owner" -PAT $PAT
    $ownerType = ($ownerInfo.type ?? "").ToString()
    $createUrl = if ($ownerType -eq "Organization") {
        "https://api.github.com/orgs/$Owner/repos"
    }
    else {
        "https://api.github.com/user/repos"
    }

    $payload = @{
        name = $RepoName
        private = ($Visibility -eq "private")
        auto_init = $false
        has_issues = $true
        has_projects = $true
        has_wiki = $true
        description = $Description
    }

    try {
        return Invoke-GitHubApi -Method "POST" -Url $createUrl -PAT $PAT -Body $payload
    }
    catch {
        $message = $_.Exception.Message
        if ($message -match "422") {
            # 仓库已存在，尝试直接读取
            return Invoke-GitHubApi -Method "GET" -Url "https://api.github.com/repos/$Owner/$RepoName" -PAT $PAT
        }
        throw
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$targetRoot = Join-Path $OutputRoot $ProjectSlug

if (Test-Path -LiteralPath $targetRoot) {
    throw "目标目录已存在: $targetRoot"
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null

Write-Step "复制项目骨架到新目录"
$excludeDirs = @(
    ".git",
    ".ace-tool",
    "venv",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist"
)

$excludeFiles = @(
    "*.pyc",
    "tmp_*.sql",
    "_ignore_write_test.txt",
    "db.sqlite3"
)

robocopy $sourceRoot $targetRoot /E /R:1 /W:1 /NFL /NDL /NJH /NJS /XD $excludeDirs /XF $excludeFiles | Out-Null

Write-Step "移除模板仓库标记文件"
$gitDir = Join-Path $targetRoot ".git"
if (Test-Path -LiteralPath $gitDir) {
    Remove-Item -LiteralPath $gitDir -Recurse -Force
}

$localApps = @(
    @{
        app = "amazon_store_assistant"
        backendDir = "amazon_store_assistant"
        settingsNeedles = @('"amazon_store_assistant"', "amazon_store_assistant")
        urlNeedles = @("amazon_store_assistant.urls", "api/amazon-store/")
        moduleKeys = @(
            "user.amazon-store-monitor",
            "user.amazon-store-analysis",
            "user.amazon-price-analysis"
        )
        menuKeys = @(
            "amazon-store-monitor",
            "amazon-store-analysis",
            "amazon-price-analysis"
        )
        componentNames = @(
            "AmazonStoreMonitor.vue",
            "AmazonStoreAnalysis.vue",
            "AmazonPriceAnalysis.vue"
        )
        frontendPaths = @(
            "hertz_server_django_ui\\src\\api\\amazon_store.ts",
            "hertz_server_django_ui\\src\\views\\user_pages\\AmazonStoreMonitor.vue",
            "hertz_server_django_ui\\src\\views\\user_pages\\AmazonStoreAnalysis.vue",
            "hertz_server_django_ui\\src\\views\\user_pages\\AmazonPriceAnalysis.vue"
        )
        docDirs = @("docs\\亚马逊店铺数据监测与运营优化系统")
        noAuthPatternFragments = @("^/api/amazon-store/.*$")
        apiExportPatterns = @(
            '(?m)^\s*export\s*\{\s*amazonStoreApi\s*\}\s*from\s*"\./amazon_store";\s*\r?\n',
            '(?ms)^\s*export type\s*\{\r?\n(?:(?!^\s*export type\s*\{).)*?^\s*\}\s*from\s*"\./amazon_store";\s*\r?\n'
        )
    },
    @{
        app = "health_rag_assistant"
        backendDir = "health_rag_assistant"
        settingsNeedles = @('"health_rag_assistant"', "health_rag_assistant")
        urlNeedles = @("health_rag_assistant.urls", "api/health-rag/")
        moduleKeys = @(
            "user.health-rag",
            "user.health-rag-recommend",
            "user.health-rag-kb"
        )
        menuKeys = @(
            "health-rag",
            "health-rag-recommend",
            "health-rag-kb"
        )
        componentNames = @(
            "HealthRagAssistant.vue",
            "HealthKnowledgeRecommend.vue",
            "HealthKnowledgeBase.vue",
            "HealthRagKbManagement.vue"
        )
        frontendPaths = @(
            "hertz_server_django_ui\\src\\api\\health_rag.ts",
            "hertz_server_django_ui\\src\\views\\admin_page\\HealthRagKbManagement.vue",
            "hertz_server_django_ui\\src\\views\\user_pages\\HealthRagAssistant.vue",
            "hertz_server_django_ui\\src\\views\\user_pages\\HealthKnowledgeRecommend.vue",
            "hertz_server_django_ui\\src\\views\\user_pages\\HealthKnowledgeBase.vue"
        )
        docDirs = @("docs\\基于RAG的身体健康智慧问答助手的设计与实现青岛理工大学")
        noAuthPatternFragments = @("^/api/health-rag/.*$")
        apiExportPatterns = @(
            '(?m)^\s*export\s*\{\s*healthRagApi\s*\}\s*from\s*"\./health_rag";\s*\r?\n',
            '(?ms)^\s*export type\s*\{\r?\n(?:(?!^\s*export type\s*\{).)*?^\s*\}\s*from\s*"\./health_rag";\s*\r?\n'
        )
    },
    @{
        app = "java_refactor_assistant"
        backendDir = "java_refactor_assistant"
        settingsNeedles = @('"java_refactor_assistant"', "java_refactor_assistant")
        urlNeedles = @("java_refactor_assistant.urls", "api/java-refactor/")
        moduleKeys = @("user.java-refactor")
        menuKeys = @("java-refactor")
        componentNames = @("JavaRefactorAssistant.vue")
        frontendPaths = @(
            "hertz_server_django_ui\\src\\api\\java_refactor.ts",
            "hertz_server_django_ui\\src\\views\\user_pages\\JavaRefactorAssistant.vue",
            "hertz_server_django_ui\\src\\views\\user_pages\\DetectionHistory.vue"
        )
        docDirs = @("docs\\JAVA重构助手")
        noAuthPatternFragments = @("^/api/java-refactor/.*$")
        apiExportPatterns = @(
            '(?m)^\s*export\s*\{\s*javaRefactorApi\s*\}\s*from\s*"\./java_refactor";\s*\r?\n',
            '(?ms)^\s*export type\s*\{\r?\n(?:(?!^\s*export type\s*\{).)*?^\s*\}\s*from\s*"\./java_refactor";\s*\r?\n'
        )
    }
)

$enabledSet = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($app in $EnableLocalApps) {
    [void]$enabledSet.Add($app)
}

$settingsPath = Join-Path $targetRoot "hertz_server_django\\settings.py"
$urlsPath = Join-Path $targetRoot "hertz_server_django\\urls.py"
$moduleConfigPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\config\\hertz_modules.ts"
$menuPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\router\\user_menu_ai.ts"
$adminMenuPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\router\\admin_menu.ts"
$apiIndexPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\api\\index.ts"
$routerIndexPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\router\\index.ts"
$userIndexPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\views\\user_pages\\index.vue"
$adminIndexPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\views\\admin_page\\index.vue"
$mainTsPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\main.ts"
$loginPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\views\\Login.vue"

Write-Step "按需启用/删除本地业务 App（纯净化处理）"
foreach ($meta in $localApps) {
    $enable = $enabledSet.Contains($meta.app)
    if ($enable) {
        Uncomment-MatchingLine -FilePath $settingsPath -ContainsText $meta.app -CommentPrefix "#"
        Uncomment-MatchingLine -FilePath $urlsPath -ContainsText $meta.app -CommentPrefix "#"
        continue
    }

    $backendPath = Join-Path $targetRoot $meta.backendDir
    Remove-PathIfExists -Path $backendPath

    foreach ($relativePath in $meta.frontendPaths) {
        Remove-PathIfExists -Path (Join-Path $targetRoot $relativePath)
    }
    foreach ($docDir in $meta.docDirs) {
        Remove-PathIfExists -Path (Join-Path $targetRoot $docDir)
    }

    Remove-LinesContainingAny -FilePath $settingsPath -Needles $meta.settingsNeedles
    Remove-LinesContainingAny -FilePath $urlsPath -Needles $meta.urlNeedles
    Remove-LinesContainingAny -FilePath $apiIndexPath -Needles @($meta.app)
    Remove-LiteralFragmentsFromFile -FilePath $settingsPath -Fragments $meta.noAuthPatternFragments

    $moduleMarkers = @()
    foreach ($moduleKey in $meta.moduleKeys) {
        $moduleMarkers += "key: `"$moduleKey`""
        $moduleMarkers += "key: '$moduleKey'"
    }
    Remove-ObjectBlocksByMarkers -FilePath $moduleConfigPath -Markers $moduleMarkers
    Remove-LinesContainingAny -FilePath $moduleConfigPath -Needles $meta.moduleKeys

    $menuMarkers = @()
    foreach ($menuKey in $meta.menuKeys) {
        $menuMarkers += "key: `"$menuKey`""
        $menuMarkers += "key: '$menuKey'"
    }
    foreach ($moduleKey in $meta.moduleKeys) {
        $menuMarkers += "moduleKey: `"$moduleKey`""
        $menuMarkers += "moduleKey: '$moduleKey'"
    }
    Remove-ObjectBlocksByMarkers -FilePath $menuPath -Markers $menuMarkers
    Remove-LinesContainingAny -FilePath $menuPath -Needles @($meta.menuKeys + $meta.moduleKeys)
    Remove-ComponentEntriesByNames -FilePath $menuPath -ComponentNames $meta.componentNames
    Remove-ComponentEntriesByNames -FilePath $adminMenuPath -ComponentNames $meta.componentNames

    if ($meta.apiExportPatterns -and $meta.apiExportPatterns.Count -gt 0) {
        Remove-RegexMatchesFromFile -FilePath $apiIndexPath -Patterns $meta.apiExportPatterns
    }
}

Write-Step "清理注释残留（仅关键配置文件）"
Remove-CommentOnlyLines -FilePath $settingsPath -CommentPrefixes @("#")
Remove-CommentOnlyLines -FilePath $urlsPath -CommentPrefixes @("#")
Remove-CommentOnlyLines -FilePath $moduleConfigPath -CommentPrefixes @("//")
Remove-CommentOnlyLines -FilePath $menuPath -CommentPrefixes @("//")
Remove-CommentOnlyLines -FilePath $adminMenuPath -CommentPrefixes @("//")
Remove-CommentOnlyLines -FilePath $apiIndexPath -CommentPrefixes @("//")

if ($enabledSet.Count -eq 0 -and (Test-Path -LiteralPath $userIndexPath)) {
    Write-Step "重建纯净用户首页模板"
    Write-CleanUserIndexTemplate -FilePath $userIndexPath
}

Write-Step "应用可选功能开关"
$disableFeatureSet = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($feature in $DisableOptionalFeatures) {
    if ($feature) {
        [void]$disableFeatureSet.Add($feature)
    }
}

if ($disableFeatureSet.Contains("user-profile")) {
    Write-Step "关闭可选功能: 用户个人信息页"
    Remove-ObjectBlocksByMarkers -FilePath $menuPath -Markers @('key: "profile"', "key: 'profile'")
    Remove-ComponentEntriesByNames -FilePath $menuPath -ComponentNames @("Profile.vue")
    Remove-PathIfExists -Path (Join-Path $targetRoot "hertz_server_django_ui\\src\\views\\user_pages\\Profile.vue")
}

if ($disableFeatureSet.Contains("theme-runtime")) {
    Write-Step "关闭可选功能: 主题运行时加载"
    Remove-LinesContainingAny -FilePath $mainTsPath -Needles @(
        "useThemeStore",
        "themeStore.loadTheme()",
        "const themeStore = useThemeStore()",
        "初始化主题（必须在挂载前加载）"
    )
}

if ($disableFeatureSet.Contains("admin-user-dropdown")) {
    Write-Step "关闭可选功能: 管理端右上角用户下拉"
    Remove-RegexMatchesFromFile -FilePath $adminIndexPath -Patterns @(
        '(?ms)\s*<!--\s*用户信息下拉菜单\s*-->\s*<a-dropdown[\s\S]*?</a-dropdown>\s*'
    )
}

Write-Step "隔离模块本地缓存键（避免沿用旧项目 localStorage）"
if (Test-Path -LiteralPath $moduleConfigPath) {
    $moduleContent = Get-Content -LiteralPath $moduleConfigPath -Raw -Encoding UTF8
    $newStorageKey = "hertz_enabled_modules_{0}" -f $ProjectSlug
    $moduleContent = [regex]::Replace(
        $moduleContent,
        'const LOCAL_STORAGE_KEY = "hertz_enabled_modules[^"]*";',
        "const LOCAL_STORAGE_KEY = `"$newStorageKey`";"
    )
    Set-Content -LiteralPath $moduleConfigPath -Value $moduleContent -Encoding UTF8
}

Write-Step "更新系统品牌文案"
if (Test-Path -LiteralPath $routerIndexPath) {
    $routerLines = Get-Content -LiteralPath $routerIndexPath -Encoding UTF8
    for ($i = 0; $i -lt $routerLines.Count; $i++) {
        if ($routerLines[$i] -match "document\.title\s*=" -and $routerLines[$i] -match "to\.meta\.title") {
            $routerLines[$i] = '    document.title = `${to.meta.title}-' + $ProjectNameCn + '`;'
        }
    }
    Set-Content -LiteralPath $routerIndexPath -Value $routerLines -Encoding UTF8
}

if (Test-Path -LiteralPath $userIndexPath) {
    $userIndexContent = Get-Content -LiteralPath $userIndexPath -Raw -Encoding UTF8
    $userIndexContent = [regex]::Replace(
        $userIndexContent,
        '<span class="logo-text">[^<]*</span>',
        "<span class=`"logo-text`">$ProjectNameCn</span>"
    )
    Set-Content -LiteralPath $userIndexPath -Value $userIndexContent -Encoding UTF8
}

if (Test-Path -LiteralPath $loginPath) {
    $loginContent = Get-Content -LiteralPath $loginPath -Raw -Encoding UTF8
    $systemNameLine = "基于Python的$ProjectNameCn"
    $loginContent = [regex]::Replace(
        $loginContent,
        '<div class="brand-badge">[^<]*</div>',
        "<div class=`"brand-badge`">$LoginBadge</div>"
    )
    $loginContent = [regex]::Replace(
        $loginContent,
        '<h1 class="welcome-title">[^<]*</h1>',
        "<h1 class=`"welcome-title`">$LoginWelcomeTitle</h1>"
    )
    $loginContent = [regex]::Replace(
        $loginContent,
        '<h2 class="system-name">[^<]*</h2>',
        "<h2 class=`"system-name`">$systemNameLine</h2>"
    )
    $loginContent = [regex]::Replace(
        $loginContent,
        '(?s)<p class="welcome-description">\s*.*?\s*</p>',
        "<p class=`"welcome-description`">$LoginDescription</p>"
    )
    Set-Content -LiteralPath $loginPath -Value $loginContent -Encoding UTF8
}

Write-Step "重置首页路由标题（用于浏览器标签）"
if (Test-Path -LiteralPath (Join-Path $targetRoot "hertz_server_django_ui\\src\\router\\user_menu_ai.ts")) {
    $menuPath = Join-Path $targetRoot "hertz_server_django_ui\\src\\router\\user_menu_ai.ts"
    $menuLines = Get-Content -LiteralPath $menuPath -Encoding UTF8
    for ($i = 0; $i -lt $menuLines.Count; $i++) {
        if ($menuLines[$i] -match 'meta:\s*\{\s*title:\s*"用户首页"\s*,\s*requiresAuth:\s*true\s*,\s*hideInMenu:\s*true\s*\}') {
            $menuLines[$i] = "    meta: { title: `"$BrowserHomeTitle`", requiresAuth: true, hideInMenu: true },"
        }
    }
    Set-Content -LiteralPath $menuPath -Value $menuLines -Encoding UTF8
}

if ($InitGit) {
    Write-Step "初始化 Git 仓库"
    Push-Location -LiteralPath $targetRoot
    try {
        git init | Out-Null
        if ($GitUserName -and $GitUserName.Trim().Length -gt 0) {
            git config user.name $GitUserName.Trim()
        }
        if ($GitUserEmail -and $GitUserEmail.Trim().Length -gt 0) {
            git config user.email $GitUserEmail.Trim()
        }
        git checkout -B $GitDefaultBranch | Out-Null
        git add . | Out-Null
        git commit -m "chore: initialize clean project template" | Out-Null
        if ($GitRemote -and $GitRemote.Trim().Length -gt 0) {
            $existingRemote = git remote | Select-String -Pattern "^origin$" -Quiet
            if ($existingRemote) {
                git remote set-url origin $GitRemote.Trim()
            }
            else {
                git remote add origin $GitRemote.Trim()
            }
        }
        if ($CreateGitHubRepo) {
            Write-Step "创建/检查 GitHub 仓库"
            $repoName = Normalize-RepoName $(if ($GitHubRepoName) { $GitHubRepoName } else { $ProjectNameCn })
            if (-not $repoName) {
                throw "无法生成有效的 GitHub 仓库名，请提供 -GitHubRepoName"
            }
            $repoInfo = Ensure-GitHubRepo -Owner $GitHubOwner.Trim() -RepoName $repoName -Visibility $GitHubVisibility -PAT $GitHubPAT.Trim() -Description $ProjectNameCn
            $cleanRemote = "https://github.com/$($GitHubOwner.Trim())/$repoName.git"
            $authRemote = "https://x-access-token:$($GitHubPAT.Trim())@github.com/$($GitHubOwner.Trim())/$repoName.git"

            $existingRemote = git remote | Select-String -Pattern "^origin$" -Quiet
            if ($existingRemote) {
                git remote set-url origin $cleanRemote
            }
            else {
                git remote add origin $cleanRemote
            }

            Write-Step "推送首个提交到 GitHub"
            git push -u $authRemote $GitDefaultBranch | Out-Null
            git remote set-url origin $cleanRemote
            Write-Step "GitHub 仓库就绪: $($repoInfo.html_url)"
        }
    }
    finally {
        Pop-Location
    }
}

Write-Step "完成"
Write-Host ""
Write-Host "新项目目录: $targetRoot" -ForegroundColor Green
Write-Host "系统名称: $ProjectNameCn" -ForegroundColor Green
Write-Host "启用本地App: $($EnableLocalApps -join ', ')" -ForegroundColor Green
if ($InitGit) {
    Write-Host "Git: 已初始化" -ForegroundColor Green
    if ($GitRemote) {
        Write-Host "Git Remote: $GitRemote" -ForegroundColor Green
    }
    if ($CreateGitHubRepo) {
        $repoNameOut = Normalize-RepoName $(if ($GitHubRepoName) { $GitHubRepoName } else { $ProjectNameCn })
        Write-Host "GitHub Repo: https://github.com/$($GitHubOwner.Trim())/$repoNameOut" -ForegroundColor Green
    }
}
