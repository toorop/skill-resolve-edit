# Installs (or updates) the resolve-edit skill into Claude's skills folder by mirror copy.
# A junction is not possible when %USERPROFILE%\.claude points to WSL (\wsl$\...): Windows can neither create
# nor follow such a link. Run again after every change or "git pull".
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
$src = Join-Path $PSScriptRoot "skills\resolve-edit"
$skills = Join-Path $env:USERPROFILE ".claude\skills"
$dst = Join-Path $skills "resolve-edit"
robocopy $src $dst /MIR /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Write-Error "robocopy failed (code $LASTEXITCODE)"; exit 1 }
Write-Output "Skill installed in $dst"
