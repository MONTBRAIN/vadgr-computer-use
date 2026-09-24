# Copyright 2026 Victor Santiago Montano Diaz
# Licensed under the Apache License, Version 2.0.

$ErrorActionPreference = 'Stop'
$env:PSModulePath = $PSHOME + '\Modules'
$inputText = [Console]::In.ReadToEnd()
if ($inputText.Length -gt 4194304) { throw 'Adoption request exceeds its limit' }
$request = $inputText | ConvertFrom-Json
$owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$local = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if (-not [IO.Path]::IsPathRooted($local)) { throw 'Local application folder is unavailable' }
$installed = Join-Path $local 'Programs\Vadgr'
if ($request.architecture -notin @('x86_64', 'aarch64')) { throw 'Invalid adoption architecture' }
if ($request.operation -ne 'attestation' -and $request.input_key -notmatch '^[0-9a-f]{64}$') { throw 'Invalid adoption input key' }
$stateParent = Join-Path $local ('vadgr-cua\adoption\' + $request.architecture)
$stateRoot = if ($request.operation -eq 'attestation') { $stateParent } else { Join-Path $stateParent $request.input_key }
$statePath = Join-Path $stateRoot 'state.json'

function Assert-Keys($Value, [string[]]$Keys) {
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    if (($actual -join "`n") -cne (($Keys | Sort-Object) -join "`n")) { throw 'Invalid native request fields' }
}
function Hash-Bytes([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Hash-File([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert-Path([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Linked adoption path refused' }
        }
        $next = [IO.Path]::GetDirectoryName($current)
        if ($next -eq $current) { break }
        $current = $next
    }
}
function Within([string]$Root, [string]$Path) {
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $value = [IO.Path]::GetFullPath($Path)
    if (-not $value.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Native adoption path escapes its root' }
    Assert-Path $value
    return $value
}
function Assert-Private([string]$Path, [bool]$Protected = $false) {
    Assert-Path $Path
    $acl = Get-Acl -LiteralPath $Path
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $owner.Value -or
        ($Protected -and -not $acl.AreAccessRulesProtected)) { throw 'Adoption owner or inheritance is invalid' }
    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) { throw 'Adoption ACL must contain exactly owner and SYSTEM' }
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -notin @($owner.Value, $system.Value) -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl) {
            throw 'Adoption ACL permits an unexpected principal'
        }
    }
    if (@($rules.IdentityReference.Value | Sort-Object -Unique).Count -ne 2) { throw 'Duplicate adoption ACL principal' }
}
function Protect-Directory([string]$Path) {
    Assert-Path $Path
    if (Test-Path -LiteralPath $Path) {
        if (-not (Get-Item -LiteralPath $Path -Force).PSIsContainer) { throw 'Adoption directory is not a directory' }
        # Released install.ps1 created dedicated descendants that inherited the
        # already-private owner/SYSTEM ACL. Validate that exact inheritance
        # before converting it to protected explicit rules; never accept or
        # preserve an additional principal.
        Assert-Private $Path $false
        $existing = Get-Acl -LiteralPath $Path
        $existing.SetOwner($owner)
        $existing.SetAccessRuleProtection($true, $true)
        Set-Acl -LiteralPath $Path -AclObject $existing
        Assert-Private $Path $true
        return
    }
    [IO.Directory]::CreateDirectory($Path) | Out-Null
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($owner)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($owner, $system)) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
    Assert-Private $Path $true
}
function Read-State {
    Assert-Path $stateRoot
    if (Test-Path -LiteralPath (Join-Path $local 'vadgr-cua\adoption')) {
        foreach ($parent in @((Join-Path $local 'vadgr-cua'), (Join-Path $local 'vadgr-cua\adoption'), $stateParent, $stateRoot)) {
            if (Test-Path -LiteralPath $parent) { Assert-Private $parent $true }
        }
    }
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    Assert-Private $stateRoot $true
    Assert-Private $statePath
    if ((Get-Item -LiteralPath $statePath).Length -gt 4194304) { throw 'Adoption state exceeds its limit' }
    return [IO.File]::ReadAllText($statePath, [Text.UTF8Encoding]::new($false, $true))
}
if ($request.operation -eq 'probe') {
    Assert-Keys $request @('operation', 'architecture', 'input_key')
    Assert-Path $installed
    @{installed_root=$installed;state=(Read-State)} | ConvertTo-Json -Compress
    exit 0
}

if ($request.operation -eq 'attestation') {
    Assert-Keys $request @('operation','architecture','subject','bundle','policy')
    $policy = $request.policy
    $package = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ('..\adoption\' + $request.architecture)))
    $verifier = Join-Path $package 'gh.exe'
    $trustedRoot = Join-Path $package 'trusted-root.json'
    Assert-Path $verifier
    Assert-Path $trustedRoot
    if ((Hash-File $verifier) -cne $policy.verifier_sha256 -or
        (Hash-File $trustedRoot) -cne $policy.root_sha256) { throw 'Offline verifier changed' }
    Protect-Directory (Join-Path $local 'vadgr-cua')
    $verificationRoot = Join-Path $local 'vadgr-cua\adoption-verification'
    Protect-Directory $verificationRoot
    $temporary = Join-Path $verificationRoot ([guid]::NewGuid().ToString('N'))
    Protect-Directory $temporary
    Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
public static class CuaBoundedVerifier {
 static string Read(StreamReader reader, Process process) {
  var text=new StringBuilder(); var buffer=new char[4096]; int count;
  while((count=reader.Read(buffer,0,buffer.Length))>0) {
   if(text.Length+count>4194304) { try {process.Kill();} catch {} throw new IOException("Verifier output exceeds limit"); }
   text.Append(buffer,0,count);
  }
  return text.ToString();
 }
 public static string Run(string executable,string arguments,string config,string systemRoot) {
  using(var process=new Process()) {
   var start=new ProcessStartInfo(executable,arguments);
   start.UseShellExecute=false;start.CreateNoWindow=true;
   start.RedirectStandardOutput=true;start.RedirectStandardError=true;
   start.RedirectStandardInput=true;
   start.EnvironmentVariables.Clear();
   start.EnvironmentVariables["SystemRoot"]=systemRoot;
   start.EnvironmentVariables["WINDIR"]=systemRoot;
   start.EnvironmentVariables["GH_CONFIG_DIR"]=config;
   start.EnvironmentVariables["GH_PROMPT_DISABLED"]="1";
   start.EnvironmentVariables["GH_NO_UPDATE_NOTIFIER"]="1";
   start.EnvironmentVariables["GH_NO_EXTENSION_UPDATE_NOTIFIER"]="1";
   process.StartInfo=start;process.Start();process.StandardInput.Close();
   var output=Task.Factory.StartNew(()=>Read(process.StandardOutput,process));
   var error=Task.Factory.StartNew(()=>Read(process.StandardError,process));
   if(!process.WaitForExit(45000)) {process.Kill();process.WaitForExit();throw new IOException("Verifier timeout");}
   Task.WaitAll(output,error);
   if(process.ExitCode!=0) throw new IOException("Offline attestation did not verify");
   return output.Result;
  }
 }
}
'@
    try {
        $subject = Join-Path $temporary 'subject.json'
        $bundle = Join-Path $temporary 'bundle.json'
        [IO.File]::WriteAllBytes($subject,[Convert]::FromBase64String($request.subject))
        [IO.File]::WriteAllBytes($bundle,[Convert]::FromBase64String($request.bundle))
        Assert-Private $subject
        Assert-Private $bundle
        $arguments = @('attestation','verify',$subject,'--bundle',$bundle,'--custom-trusted-root',$trustedRoot,
            '--repo',$policy.repository,'--cert-identity',$policy.certificate_identity,
            '--cert-oidc-issuer',$policy.issuer,'--source-ref',$policy.source_ref,
            '--deny-self-hosted-runners','--format','json')
        if (@($policy.source_sha_allowlist).Count -gt 4 -or @($policy.signer_sha_allowlist).Count -gt 4) { throw 'Too many trust pins' }
        foreach ($source in $policy.source_sha_allowlist) {
            foreach ($signer in $policy.signer_sha_allowlist) {
                $all = $arguments + @('--source-digest',$source,'--signer-digest',$signer)
                # Every fixed argument is quoted, and embedded quotes are refused.
                foreach ($argument in $all) { if ([string]$argument -match '["\r\n]' -or [string]$argument -match '\\$') { throw 'Invalid verifier argument' } }
                $command = ($all | ForEach-Object { '"' + $_ + '"' }) -join ' '
                try {
                    $proof = [CuaBoundedVerifier]::Run($verifier,$command,$temporary,[Environment]::GetFolderPath('Windows'))
                    @{proof=$proof} | ConvertTo-Json -Compress -Depth 5
                    exit 0
                } catch { }
            }
        }
        throw 'No approved offline attestation verified'
    } finally {
        $safe = Within $verificationRoot $temporary
        Remove-Item -LiteralPath $safe -Recurse -Force
    }
}

if ($request.operation -notin @('deploy', 'publish-state')) { throw 'Unknown native adoption operation' }
$keys = @('operation','architecture','input_key','archive','archive_sha256','manifest','manifest_path','manifest_sha256','relay','relay_member','policy','installed_root')
if ($request.operation -eq 'publish-state') { $keys += @('previous','state','authorization_sha256') }
Assert-Keys $request $keys
if ($request.installed_root -cne $installed) { throw 'Installed root does not match its known folder' }
Assert-Private $installed $true
$archive = Within $installed $request.archive
Assert-Private $archive
if ($request.archive_sha256 -notmatch '^[0-9a-f]{64}$' -or
    (Hash-File $archive) -cne $request.archive_sha256 -or
    (Get-Item -LiteralPath $archive).Length -ne $request.manifest.archive.size) { throw 'Archive identity differs' }
$manifest = $request.manifest
$manifestPath = Within $installed $request.manifest_path
Assert-Private $manifestPath
if ((Hash-File $manifestPath) -cne $request.manifest_sha256) { throw 'Native final manifest changed' }
if ($manifest.mode -cne 'managed-signed' -or $manifest.architecture -cne $request.architecture -or
    $manifest.cua_version -notmatch '^\d+\.\d+\.\d+$' -or
    $request.manifest_sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid native manifest' }
$relay = Within $installed $request.relay.path
Assert-Private $relay

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.IO;
public static class CuaOfflineTrust {
 [StructLayout(LayoutKind.Sequential)] struct FileInformation {
  public uint attributes; public System.Runtime.InteropServices.ComTypes.FILETIME created,accessed,written;
  public uint volume,sizeHigh,sizeLow,links,indexHigh,indexLow;
 }
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandle(IntPtr file,out FileInformation information);
 public static void AssertOrdinary(string path) {
  using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read)) {
   FileInformation information;
   if(!GetFileInformationByHandle(stream.SafeFileHandle.DangerousGetHandle(),out information) ||
      information.links!=1 || (information.attributes & 0x410)!=0)
    throw new InvalidOperationException("Linked or nonordinary signed member refused");
  }
 }
 static int Der(byte[] bytes,ref int cursor,int tag) {
  if(cursor+2>bytes.Length || bytes[cursor++]!=tag) throw new InvalidOperationException("Invalid timestamp DER");
  int size=bytes[cursor++];
  if((size & 128)!=0) {
   int count=size & 127;size=0;
   if(count==0 || count>4 || cursor+count>bytes.Length || bytes[cursor]==0) throw new InvalidOperationException("Invalid timestamp DER length");
   for(int i=0;i<count;i++) size=checked(size*256+bytes[cursor++]);
   if(size<128) throw new InvalidOperationException("Noncanonical timestamp length");
  }
  if(size<0 || size>bytes.Length-cursor) throw new InvalidOperationException("Truncated timestamp DER");
  return cursor+size;
 }
 public static void AssertTimestampSha256(byte[] bytes) {
  int cursor=0;int end=Der(bytes,ref cursor,48);
  if(end!=bytes.Length) throw new InvalidOperationException("Timestamp trailing data");
  cursor=Der(bytes,ref cursor,2);cursor=Der(bytes,ref cursor,6);
  int imprintEnd=Der(bytes,ref cursor,48);int algorithmEnd=Der(bytes,ref cursor,48);
  int oidEnd=Der(bytes,ref cursor,6);
  byte[] sha256={0x60,0x86,0x48,0x01,0x65,0x03,0x04,0x02,0x01};
  if(oidEnd-cursor!=sha256.Length || algorithmEnd>imprintEnd || imprintEnd>end)
   throw new InvalidOperationException("Timestamp imprint algorithm differs");
  for(int i=0;i<sha256.Length;i++) if(bytes[cursor+i]!=sha256[i]) throw new InvalidOperationException("Timestamp must use SHA-256 imprint");
 }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct FileInfo {
  public uint size; public string path; public IntPtr file; public IntPtr known;
 }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct TrustData {
  public uint size; public IntPtr policy; public IntPtr sip; public uint ui;
  public uint revocation; public uint choice; public IntPtr file;
  public uint action; public IntPtr state; public string url; public uint flags;
  public uint context; public IntPtr signature;
 }
 [StructLayout(LayoutKind.Sequential)] struct Signer {
  public uint size; public System.Runtime.InteropServices.ComTypes.FILETIME time;
  public uint count; public IntPtr certs; public uint type; public IntPtr signer;
  public uint error; public uint counters; public IntPtr counterSigners; public IntPtr chain;
 }
 [StructLayout(LayoutKind.Sequential)] struct CertHead { public uint size; public IntPtr cert; }
 [DllImport("wintrust.dll", ExactSpelling=true)] static extern int WinVerifyTrust(IntPtr window, ref Guid action, ref TrustData data);
 [DllImport("wintrust.dll", ExactSpelling=true)] static extern IntPtr WTHelperProvDataFromStateData(IntPtr state);
 [DllImport("wintrust.dll", ExactSpelling=true)] static extern IntPtr WTHelperGetProvSignerFromChain(IntPtr data, uint index, bool counter, uint counterIndex);
 [DllImport("wintrust.dll", ExactSpelling=true)] static extern IntPtr WTHelperGetProvCertFromChain(IntPtr signer, uint index);
 static string Hash(byte[] value) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(value)).Replace("-", "").ToLowerInvariant(); }
 public static string[] Verify(string path) {
  var file = new FileInfo { size=(uint)Marshal.SizeOf(typeof(FileInfo)), path=path };
  IntPtr memory=Marshal.AllocHGlobal(Marshal.SizeOf(file));
  Marshal.StructureToPtr(file,memory,false);
  var data = new TrustData { size=(uint)Marshal.SizeOf(typeof(TrustData)), ui=2, choice=1,
    file=memory, action=1, flags=0x1000 | 0x80, context=0 };
  var action=new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
  try {
   // CACHE_ONLY_URL_RETRIEVAL + REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT. No online fallback.
   int status=WinVerifyTrust(new IntPtr(-1),ref action,ref data);
   if(status!=0) throw new InvalidOperationException("Offline Authenticode validation failed");
   IntPtr provider=WTHelperProvDataFromStateData(data.state);
   IntPtr pointer=WTHelperGetProvSignerFromChain(provider,0,false,0);
   if(pointer==IntPtr.Zero) throw new InvalidOperationException("Missing validated signer");
   var signer=(Signer)Marshal.PtrToStructure(pointer,typeof(Signer));
   if(signer.count<2 || signer.counters<1) throw new InvalidOperationException("Missing verified chain or timestamp");
   var first=(CertHead)Marshal.PtrToStructure(WTHelperGetProvCertFromChain(pointer,0),typeof(CertHead));
   var last=(CertHead)Marshal.PtrToStructure(WTHelperGetProvCertFromChain(pointer,signer.count-1),typeof(CertHead));
   using(var leaf=new X509Certificate2(first.cert)) using(var root=new X509Certificate2(last.cert))
    return new [] {leaf.Subject,Hash(leaf.RawData),Hash(root.RawData)};
  } finally {
   data.action=2; WinVerifyTrust(new IntPtr(-1),ref action,ref data);
   Marshal.DestroyStructure(memory,typeof(FileInfo)); Marshal.FreeHGlobal(memory);
  }
 }
}
'@

function Verify-File([string]$Path, $Record, $Policy) {
    Assert-Private $Path
    [CuaOfflineTrust]::AssertOrdinary($Path)
    if ((Get-Item -LiteralPath $Path).Length -ne $Record.size -or (Hash-File $Path) -cne $Record.sha256) {
        throw 'Deployed helper bytes differ'
    }
    if ($Policy.trust_class -eq 'data') { return }
    if ($Policy.trust_class -notin @('publisher-sign','vendor-preserve')) { throw 'Unknown native trust class' }
    $signature = [CuaOfflineTrust]::Verify($Path)
    if ($signature[0] -cne $Policy.signer -or $signature[1] -cne $Policy.certificate_sha256 -or
        $signature[2] -cne $Policy.chain_root_sha256) { throw 'Native signature identity differs from packaged policy' }
    Add-Type -AssemblyName System.Security
    $bytes = [IO.File]::ReadAllBytes($Path)
    $pe = [BitConverter]::ToInt32($bytes,60)
    $security = $pe + 24 + 112 + 32
    $offset = [BitConverter]::ToInt32($bytes,$security)
    $size = [BitConverter]::ToInt32($bytes,$security+4)
    if ($offset -lt 0 -or $size -lt 8 -or $offset + $size -ne $bytes.Length) { throw 'Invalid PE signature table' }
    $length = [BitConverter]::ToInt32($bytes,$offset)
    if ($length -lt 8 -or $length -gt $size) { throw 'Invalid PE certificate length' }
    $signedBytes = [byte[]]::new($length-8)
    [Array]::Copy($bytes,$offset+8,$signedBytes,0,$signedBytes.Length)
    $cms = [Security.Cryptography.Pkcs.SignedCms]::new()
    $cms.Decode($signedBytes)
    $cms.CheckSignature($true)
    if ($cms.SignerInfos.Count -ne 1 -or $Policy.digest_algorithm -cne 'sha256' -or
        $cms.SignerInfos[0].DigestAlgorithm.Value -cne '2.16.840.1.101.3.4.2.1') { throw 'Native signature digest algorithm differs' }
    $timestamps = @($cms.SignerInfos[0].UnsignedAttributes | Where-Object { $_.Oid.Value -eq '1.3.6.1.4.1.311.3.3.1' })
    if ($Policy.timestamp_algorithm -cne 'rfc3161-sha256' -or $timestamps.Count -ne 1 -or
        $timestamps[0].Values.Count -ne 1) { throw 'Native RFC 3161 timestamp is missing' }
    $timestamp = [Security.Cryptography.Pkcs.SignedCms]::new()
    $timestamp.Decode($timestamps[0].Values[0].RawData)
    $timestamp.CheckSignature($true)
    if ($timestamp.ContentInfo.ContentType.Value -cne '1.2.840.113549.1.9.16.1.4' -or
        $timestamp.SignerInfos.Count -ne 1 -or
        $timestamp.SignerInfos[0].DigestAlgorithm.Value -cne '2.16.840.1.101.3.4.2.1') { throw 'Native timestamp digest differs' }
    [CuaOfflineTrust]::AssertTimestampSha256($timestamp.ContentInfo.Content)
}
function Verify-Bundle([string]$Root) {
    Assert-Private $Root $true
    $expected = @{}
    foreach ($record in $manifest.files) {
        $path = Within $Root (Join-Path $Root ([string]$record.path))
        $expected[$path] = $true
        $pin = $request.policy.PSObject.Properties[[string]$record.path]
        if ($null -eq $pin) { throw 'Native member policy is missing' }
        Verify-File $path $record $pin.Value
    }
    $sidecar = Join-Path $Root 'broker-final-manifest.json'
    Assert-Private $sidecar
    [CuaOfflineTrust]::AssertOrdinary($sidecar)
    if ((Hash-File $sidecar) -cne $request.manifest_sha256) { throw 'Deployed final manifest changed' }
    $actual = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force | Where-Object { $_.FullName -cne $sidecar })
    if ($actual.Count -ne $expected.Count) { throw 'Unexpected deployed member count' }
    foreach ($file in $actual) { if (-not $expected.ContainsKey($file.FullName)) { throw 'Unexpected deployed member' } }
    foreach ($directory in @(Get-ChildItem -LiteralPath $Root -Directory -Recurse -Force)) { Assert-Private $directory.FullName }
}
$relayPin = $request.policy.PSObject.Properties[[string]$request.relay_member]
if ($null -eq $relayPin) { throw 'Native relay policy is missing' }
Verify-File $relay $request.relay $relayPin.Value
$parent = Join-Path $local ('vadgr-cua\browser-broker\' + $manifest.cua_version)
$destination = Join-Path $parent $request.archive_sha256
Assert-Path $destination
if (-not (Test-Path -LiteralPath $destination)) {
    if ($request.operation -eq 'publish-state') { throw 'Verified deployment vanished before publication' }
    Protect-Directory (Join-Path $local 'vadgr-cua')
    Protect-Directory (Join-Path $local 'vadgr-cua\browser-broker')
    Protect-Directory $parent
    $staging = Join-Path $parent ('.adoption-' + [guid]::NewGuid().ToString('N'))
    Protect-Directory $staging
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        try {
            $seen=@{}; [long]$expanded=0
            if ($zip.Entries.Count -gt 4096) { throw 'Too many native archive members' }
            foreach ($entry in $zip.Entries) {
                $name=[string]$entry.FullName
                $expanded += $entry.Length
                if ($expanded -gt 268435456 -or [string]::IsNullOrEmpty($entry.Name) -or $name.Contains(':') -or
                    $name.Contains('\') -or $name.StartsWith('/') -or $seen.ContainsKey($name.ToLowerInvariant()) -or
                    @($name.Split('/') | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0) { throw 'Unsafe native archive member' }
                $seen[$name.ToLowerInvariant()]=$true
                $target = Within $staging (Join-Path $staging $name)
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$false)
            }
        } finally { $zip.Dispose() }
        Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $staging 'broker-final-manifest.json')
        Verify-Bundle $staging
        [IO.Directory]::Move($staging,$destination)
    } finally {
        if (Test-Path -LiteralPath $staging) {
            $safe = Within $parent $staging
            Remove-Item -LiteralPath $safe -Recurse -Force
        }
    }
}
Verify-Bundle $destination
if ($request.operation -eq 'deploy') {
    @{destination=$destination;relay=$relay;archive_sha256=$request.archive_sha256;manifest_sha256=$request.manifest_sha256} | ConvertTo-Json -Compress
    exit 0
}

$state = [string]$request.state
$parsed = $state | ConvertFrom-Json
Assert-Keys $parsed @('schema','architecture','input_closure','final_closure','authorization_sha256','mode')
if ($parsed.schema -ne 1 -or $parsed.mode -cne 'managed-signed' -or $parsed.architecture -cne $request.architecture -or
    $parsed.final_closure.archive_sha256 -cne $request.archive_sha256 -or
    $parsed.final_closure.manifest_sha256 -cne $request.manifest_sha256 -or
    $parsed.final_closure.relay_sha256 -cne $request.relay.sha256 -or
    $parsed.authorization_sha256 -cne $request.authorization_sha256) { throw 'Adoption state differs from verified closure' }
$inputIdentity = [ordered]@{archive_sha256=$parsed.input_closure.archive_sha256;manifest_sha256=$parsed.input_closure.manifest_sha256;relay_sha256=$parsed.input_closure.relay_sha256}
$inputBytes = [Text.UTF8Encoding]::new($false,$true).GetBytes(($inputIdentity | ConvertTo-Json -Compress) + "`n")
if ((Hash-Bytes $inputBytes) -cne $request.input_key) { throw 'Adoption state key differs from the input closure' }
Protect-Directory (Join-Path $local 'vadgr-cua\adoption')
Protect-Directory $stateParent
Protect-Directory $stateRoot
$lockPath = Join-Path $stateRoot 'publication.lock'
$lock = [IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
    Assert-Private $lockPath
    $previous = Read-State
    if (($null -eq $previous) -ne ($null -eq $request.previous) -or $previous -cne $request.previous) { throw 'Adoption state changed concurrently' }
    if ($null -ne $previous -and $previous -cne $state) { throw 'Signed adoption transition is not authorized' }
    $temporary = Join-Path $stateRoot ('.state-' + [guid]::NewGuid().ToString('N'))
    try {
        $bytes = [Text.UTF8Encoding]::new($false,$true).GetBytes($state)
        $stream = [IO.File]::Open($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { Assert-Private $temporary; $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) }
        finally { $stream.Dispose() }
        if (Test-Path -LiteralPath $statePath) { [IO.File]::Replace($temporary,$statePath,$null) }
        else { [IO.File]::Move($temporary,$statePath) }
        Assert-Private $statePath
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
    @{state_sha256=(Hash-Bytes $bytes)} | ConvertTo-Json -Compress
} finally { $lock.Dispose() }
