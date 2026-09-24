param(
    [Parameter(Mandatory = $true)][string]$Archive,
    [Parameter(Mandatory = $true)][string]$Manifest,
    [Parameter(Mandatory = $true)][string]$ExpectedManifestSha256,
    [Parameter(Mandatory = $true)][string]$SignatureReports
)

$ErrorActionPreference = "Stop"
$env:PSModulePath = $PSHOME + '\Modules'
$ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')

Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
public static class CuaManagedFile {
 [StructLayout(LayoutKind.Sequential)] struct Information {
  public uint attributes; public System.Runtime.InteropServices.ComTypes.FILETIME created,accessed,written;
  public uint volume,sizeHigh,sizeLow,links,indexHigh,indexLow;
 }
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandle(IntPtr file,out Information information);
 public static void AssertOrdinary(string path) {
  using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read)) {
   Information information;
   if(!GetFileInformationByHandle(stream.SafeFileHandle.DangerousGetHandle(),out information) ||
      information.links!=1 || (information.attributes & 0x410)!=0)
    throw new IOException("Managed broker file is linked or nonordinary");
  }
 }
}
'@

function Get-LowerSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-NoReparseParent([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrEmpty($current)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Managed broker path contains a reparse point"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Assert-Private([string]$Path, [bool]$Protected = $false) {
    Assert-NoReparseParent $Path
    $acl = Get-Acl -LiteralPath $Path
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $ownerSid.Value -or
        ($Protected -and -not $acl.AreAccessRulesProtected)) { throw 'Invalid managed broker owner or inheritance' }
    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) { throw 'Managed broker ACL must contain exactly owner and SYSTEM' }
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -notin @($ownerSid.Value, $systemSid.Value) -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl) {
            throw 'Managed broker ACL permits an unexpected principal'
        }
    }
    if (@($rules.IdentityReference.Value | Sort-Object -Unique).Count -ne 2) { throw 'Duplicate managed broker ACL principal' }
}

function Get-VerifiedFiles([string]$Root) {
    Assert-Private $Root $true
    if (-not (Get-Item -LiteralPath $Root -Force).PSIsContainer) { throw 'Managed broker root is not a directory' }
    $pending = [Collections.Generic.Queue[string]]::new()
    $pending.Enqueue($Root)
    while ($pending.Count -gt 0) {
        foreach ($entry in @(Get-ChildItem -LiteralPath $pending.Dequeue() -Force)) {
            Assert-Private $entry.FullName
            if ($entry.PSIsContainer) { $pending.Enqueue($entry.FullName) }
            else { [CuaManagedFile]::AssertOrdinary($entry.FullName); $entry }
        }
    }
}

function Read-SignatureReport([string]$Digest) {
    if ($Digest -notmatch '^[0-9a-f]{64}$') { throw "Invalid signature report digest" }
    if (-not (Test-Path -LiteralPath $SignatureReports -PathType Leaf)) {
        throw "Required signature report is missing"
    }
    $reports = Get-Content -LiteralPath $SignatureReports -Raw | ConvertFrom-Json
    $matched = @()
    foreach ($property in $reports.PSObject.Properties) {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($property.Value | ConvertTo-Json -Compress -Depth 20) + "`n")
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
        if ($hash -ceq $Digest) { $matched += $property.Value }
    }
    if ($matched.Count -ne 1) { throw "Signature report digest mismatch" }
    return $matched[0]
}

function Test-ManagedBundle([string]$Root, [object]$Metadata) {
    $actual = @(Get-VerifiedFiles $Root)
    $sidecar = Join-Path $Root 'broker-final-manifest.json'
    if (-not (Test-Path -LiteralPath $sidecar -PathType Leaf) -or
        (Get-LowerSha256 $sidecar) -cne $ExpectedManifestSha256.ToLowerInvariant()) { return $false }
    $expected = @{}
    $expected[[IO.Path]::GetFullPath($sidecar)] = $true
    foreach ($record in $Metadata.files) {
        $relative = ([string]$record.path).Replace('/', [IO.Path]::DirectorySeparatorChar)
        $path = [IO.Path]::GetFullPath((Join-Path $Root $relative))
        $rootPrefix = [IO.Path]::GetFullPath($Root) + [IO.Path]::DirectorySeparatorChar
        if (-not $path.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Managed broker member escapes its root"
        }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
        $file = Get-Item -LiteralPath $path -Force
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Managed broker member is a reparse point"
        }
        if ($file.Length -ne [long]$record.size -or (Get-LowerSha256 $path) -ne [string]$record.sha256) {
            return $false
        }
        $expected[$path] = $true
        $trustClass = [string]$record.trust_class
        if ($trustClass -eq 'data') {
            if ($null -ne $record.signature_report_sha256) {
                throw "Data member asserts a signature report"
            }
            continue
        }
        if ($trustClass -notin @('publisher-sign', 'vendor-preserve')) {
            throw "Unknown managed broker trust class"
        }
        $report = Read-SignatureReport ([string]$record.signature_report_sha256)
        if ([int]$report.schema -ne 1 -or
            [string]$report.file_sha256 -ne [string]$record.sha256 -or
            [string]$report.trust_class -ne $trustClass -or
            [int]$report.signtool_exit -ne 0 -or
            [string]$report.authenticode_status -ne 'Valid' -or
            $report.chain_valid -ne $true -or $report.timestamp_valid -ne $true) {
            throw "Signature report does not bind the managed broker member"
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
            throw "Managed broker signature is not valid"
        }
        if ($null -eq $signature.SignerCertificate -or
            $signature.SignerCertificate.Subject -ne [string]$report.signer) {
            throw "Managed broker signer identity differs from its reviewed report"
        }
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            $certificateHash = [BitConverter]::ToString(
                $sha.ComputeHash($signature.SignerCertificate.RawData)
            ).Replace('-', '').ToLowerInvariant()
        } finally { $sha.Dispose() }
        if ($certificateHash -ne [string]$report.certificate_sha256) {
            throw "Managed broker signer certificate differs from its reviewed report"
        }
        $chain = [Security.Cryptography.X509Certificates.X509Chain]::new()
        try {
            if (-not $chain.Build($signature.SignerCertificate) -or $chain.ChainElements.Count -lt 1) {
                throw "Managed broker certificate chain is invalid"
            }
            $trustRoot = $chain.ChainElements[$chain.ChainElements.Count - 1].Certificate.RawData
            $sha = [Security.Cryptography.SHA256]::Create()
            try {
                $rootHash = [BitConverter]::ToString($sha.ComputeHash($trustRoot)).Replace('-', '').ToLowerInvariant()
            } finally { $sha.Dispose() }
        } finally { $chain.Dispose() }
        if ($rootHash -ne [string]$report.chain_root_sha256 -or
            $null -eq $signature.TimeStamperCertificate) {
            throw "Managed broker chain or timestamp differs from its reviewed report"
        }
    }
    foreach ($file in $actual) {
        if (-not $expected.ContainsKey($file.FullName)) { return $false }
    }
    return $actual.Count -eq $expected.Count
}

if ((Get-LowerSha256 $Manifest) -ne $ExpectedManifestSha256.ToLowerInvariant()) {
    throw "Managed broker final manifest digest mismatch"
}
$metadata = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
if ([int]$metadata.schema -ne 1 -or [string]$metadata.mode -ne 'managed-signed') {
    throw "Unsupported managed broker final manifest"
}
if ((Get-LowerSha256 $Archive) -ne [string]$metadata.archive.sha256 -or
    (Get-Item -LiteralPath $Archive).Length -ne [long]$metadata.archive.size) {
    throw "Managed broker archive identity mismatch"
}

$localAppData = $env:VADGR_CUA_WINDOWS_LOCAL_APP_DATA
if ([string]::IsNullOrWhiteSpace($localAppData)) { $localAppData = $env:LOCALAPPDATA }
$parent = Join-Path $localAppData "vadgr-cua\browser-broker\$($metadata.cua_version)"
$destination = Join-Path $parent ([string]$metadata.archive.sha256)
Assert-NoReparseParent $parent

if (Test-Path -LiteralPath $destination) {
    if (-not (Test-ManagedBundle $destination $metadata)) {
        throw "Installed managed browser broker failed verification"
    }
} else {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Assert-NoReparseParent $parent
    $staging = Join-Path $parent ('.' + ([string]$metadata.archive.sha256).Substring(0, 12) + '-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $staging | Out-Null
    try {
        $owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls.exe $staging /inheritance:r | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to protect managed broker staging root" }
        & icacls.exe $staging /grant:r "${owner}:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" /T /C | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to protect managed broker staging payload" }

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $root = [IO.Path]::GetFullPath($staging) + [IO.Path]::DirectorySeparatorChar
        $seen = @{}
        $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
        try {
            foreach ($entry in $zip.Entries) {
                if ([string]::IsNullOrEmpty($entry.Name)) { throw "Directory entry is not allowed" }
                $name = $entry.FullName.Replace('\', '/')
                if ($name.Contains(':') -or $seen.ContainsKey($name.ToLowerInvariant())) {
                    throw "Unsafe or duplicate managed broker member"
                }
                $seen[$name.ToLowerInvariant()] = $true
                $target = [IO.Path]::GetFullPath((Join-Path $staging $name))
                if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Unsafe path in managed broker archive"
                }
                New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
            }
        } finally { $zip.Dispose() }
        Copy-Item -LiteralPath $Manifest -Destination (Join-Path $staging 'broker-final-manifest.json')
        if (-not (Test-ManagedBundle $staging $metadata)) {
            throw "Extracted managed broker failed verification"
        }
        try {
            [System.IO.Directory]::Move($staging, $destination)
        } catch {
            if (-not (Test-Path -LiteralPath $destination) -or
                -not (Test-ManagedBundle $destination $metadata)) { throw }
        }
    } finally {
        if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    }
}

$receipt = [ordered]@{
    schema = 1
    profile = [string]$env:VADGR_CUA_RELEASE_PROFILE
    broker_final_manifest_sha256 = $ExpectedManifestSha256.ToLowerInvariant()
    archive_sha256 = [string]$metadata.archive.sha256
    destination = $destination
    member_count = @($metadata.files).Count
}
$receipt | ConvertTo-Json -Compress
