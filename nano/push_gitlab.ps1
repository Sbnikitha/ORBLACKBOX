# Push to GitLab using the project token stored outside this repo.
# Token file: %USERPROFILE%\.or-sentinel\gitlab-token
# Remote file: %USERPROFILE%\.or-sentinel\gitlab-remote.txt
# This does not write git config and does not put the token in the remote URL.

$ErrorActionPreference = "Stop"
$dir = Join-Path $env:USERPROFILE ".or-sentinel"
$tokenFile = Join-Path $dir "gitlab-token"
$remoteFile = Join-Path $dir "gitlab-remote.txt"
$askpass = Join-Path $PSScriptRoot "gitlab_askpass.py"

if (-not (Test-Path $tokenFile)) {
    Write-Error "Save the project access token in $tokenFile (one line). Do not paste it into chat."
}
if (-not (Test-Path $remoteFile)) {
    Write-Error "Save the GitLab project URL in $remoteFile, for example https://gitlab.com/group/orblackbox.git"
}

$remote = (Get-Content -Raw $remoteFile).Trim()
$env:GIT_ASKPASS = "python"
$env:GIT_ASKPASS_REQUIRE = $askpass
# Git runs GIT_ASKPASS as the program. Point it at python plus the script via a wrapper.
$wrapper = Join-Path $dir "askpass.cmd"
@"
@echo off
python "$askpass" %*
"@ | Set-Content -Path $wrapper -Encoding ascii
$env:GIT_ASKPASS = $wrapper
$env:GIT_TERMINAL_PROMPT = "0"
git push $remote HEAD:main
