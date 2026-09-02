param(
    [Parameter(Mandatory = $true)][string]$Archive,
    [Parameter(Mandatory = $true)][string]$Manifest
)

$ErrorActionPreference = "Stop"
$metadata = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
$archiveHash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($archiveHash -ne [string]$metadata.archive_sha256) {
    throw "Windows browser broker archive failed integrity verification"
}

$parent = Join-Path $env:LOCALAPPDATA "vadgr-cua\browser-broker\$($metadata.version)"
$destination = Join-Path $parent $archiveHash

function Test-Bundle([string]$Root) {
    $expected = @{}
    foreach ($item in $metadata.files) {
        $relative = ([string]$item.path).Replace('/', [IO.Path]::DirectorySeparatorChar)
        $path = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne [string]$item.sha256) { return $false }
        $expected[[IO.Path]::GetFullPath($path)] = $true
    }
    $actualFiles = @(Get-ChildItem -LiteralPath $Root -File -Recurse |
        Where-Object Name -ne "bundle-manifest.json")
    foreach ($file in $actualFiles) {
        if (-not $expected.ContainsKey($file.FullName)) { return $false }
    }
    return $actualFiles.Count -eq $expected.Count
}

if (Test-Path -LiteralPath $destination) {
    if (-not (Test-Bundle $destination)) {
        throw "Installed Windows browser broker payload failed integrity verification"
    }
    Write-Output $destination
    exit 0
}

New-Item -ItemType Directory -Path $parent -Force | Out-Null
$staging = Join-Path $parent ("." + $archiveHash.Substring(0, 12) + "-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $staging | Out-Null
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $root = [IO.Path]::GetFullPath($staging) + [IO.Path]::DirectorySeparatorChar
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            if ([string]::IsNullOrEmpty($entry.Name)) { continue }
            $target = [IO.Path]::GetFullPath((Join-Path $staging $entry.FullName))
            if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Unsafe path in Windows browser broker archive"
            }
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force |
                Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
        }
    }
    finally {
        $zip.Dispose()
    }
    if (-not (Test-Bundle $staging)) {
        throw "Extracted Windows browser broker payload failed integrity verification"
    }
    Copy-Item -LiteralPath $Manifest -Destination (Join-Path $staging "bundle-manifest.json")

    $owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $staging /inheritance:r | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to protect Windows browser broker root" }
    & icacls.exe $staging /grant:r "${owner}:F" "*S-1-5-18:F" /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to protect Windows browser broker payload" }
    & icacls.exe $staging /grant "${owner}:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" |
        Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to set broker inheritance rules" }

    try {
        Move-Item -LiteralPath $staging -Destination $destination
    }
    catch {
        if (-not (Test-Path -LiteralPath $destination) -or -not (Test-Bundle $destination)) {
            throw
        }
    }
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}

Write-Output $destination
