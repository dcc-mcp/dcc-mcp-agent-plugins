param([string]$OutputDirectory = (Join-Path $PSScriptRoot "..\dist"))

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
$version = (Get-Content (Join-Path $repo "plugins\dcc-mcp\.codex-plugin\plugin.json") | ConvertFrom-Json).version
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$pluginArchive = Join-Path $OutputDirectory "dcc-mcp-agent-plugin-$version.zip"

git -C $repo archive --format=zip --prefix=dcc-mcp/ --output=$pluginArchive HEAD:plugins/dcc-mcp
if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
python (Join-Path $PSScriptRoot "package_openclaw_skill.py") (Join-Path $repo ".github\clawhub-skills.json") (Join-Path $OutputDirectory "skills") --manifest
if ($LASTEXITCODE -ne 0) { throw "Skill packaging failed" }
