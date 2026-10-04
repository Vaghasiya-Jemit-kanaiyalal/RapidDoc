<#
Prints a fingerprint of the backend requirement files.

run_dev.bat compares this against a stamp next to the virtualenv so an edited
requirement triggers an install and an unchanged one does not. Printing the hash
from a file rather than an inline -Command keeps the batch quoting simple: the
inline form cannot contain the braces and parentheses PowerShell needs.
#>

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$parts = @()
foreach ($name in @('requirements.txt', 'requirements-dev.txt')) {
    $path = Join-Path $root $name
    if (Test-Path $path) {
        $parts += "$name`n" + (Get-Content $path -Raw)
    }
}

if ($parts.Count -eq 0) {
    Write-Output 'NO-REQUIREMENTS'
    exit 0
}

$sha = [System.Security.Cryptography.SHA256]::Create()
$bytes = [Text.Encoding]::UTF8.GetBytes(($parts -join "`n"))
Write-Output ([BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLower())