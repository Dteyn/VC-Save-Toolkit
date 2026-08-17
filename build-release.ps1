[CmdletBinding()]
param(
    [string]$OutputDirectory = "release"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$PackageRoot = Join-Path $ProjectRoot "vc_save_toolkit"
$MetadataFile = Join-Path $PackageRoot "__init__.py"

if (-not (Test-Path -LiteralPath $MetadataFile -PathType Leaf)) {
    throw "Could not find package metadata: $MetadataFile"
}

$Metadata = Get-Content -LiteralPath $MetadataFile -Raw
$VersionMatch = [regex]::Match($Metadata, 'APP_VERSION\s*=\s*["'']([^"'']+)["'']')
if (-not $VersionMatch.Success) {
    throw "Could not determine APP_VERSION from vc_save_toolkit\__init__.py."
}

$Version = $VersionMatch.Groups[1].Value
$ReleaseName = "VC-Save-Toolkit-v$Version"

if (-not [System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $ProjectRoot $OutputDirectory
}

$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$ZipPath = Join-Path $OutputDirectory "$ReleaseName.zip"
$StagingParent = Join-Path ([System.IO.Path]::GetTempPath()) ("vc-save-toolkit-release-" + [guid]::NewGuid().ToString("N"))
$StagingRoot = Join-Path $StagingParent $ReleaseName

$RequiredRootFiles = @(
    "vc_save_toolkit.pyw",
    "requirements.txt",
    "install-requirements.bat",
    "install-requirements-linux.sh",
    "install-requirements-macos.command",
    "README.md",
    "LICENSE",
    "THIRD-PARTY-NOTICES.md"
)

$RequiredAssets = @(
    "vc_save_toolkit.png",
    "vc_save_toolkit.svg"
)

try {
    Write-Host "Building $ReleaseName..." -ForegroundColor Cyan

    foreach ($RelativePath in $RequiredRootFiles) {
        $SourcePath = Join-Path $ProjectRoot $RelativePath
        if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
            throw "Required release file is missing: $RelativePath"
        }
    }

    if (-not (Test-Path -LiteralPath $PackageRoot -PathType Container)) {
        throw "Required package directory is missing: vc_save_toolkit"
    }

    foreach ($AssetName in $RequiredAssets) {
        $AssetPath = Join-Path (Join-Path $PackageRoot "assets") $AssetName
        if (-not (Test-Path -LiteralPath $AssetPath -PathType Leaf)) {
            throw "Required application asset is missing: vc_save_toolkit\assets\$AssetName"
        }
    }

    New-Item -ItemType Directory -Path $StagingRoot -Force | Out-Null

    foreach ($RelativePath in $RequiredRootFiles) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $RelativePath) -Destination (Join-Path $StagingRoot $RelativePath)
    }

    $PackageDestination = Join-Path $StagingRoot "vc_save_toolkit"
    New-Item -ItemType Directory -Path $PackageDestination -Force | Out-Null

    # Copy runtime Python modules only. This automatically includes future package
    # modules without pulling tests, caches, build output, or repository documents.
    Get-ChildItem -LiteralPath $PackageRoot -Recurse -File -Filter "*.py" | ForEach-Object {
        $RelativePath = $_.FullName.Substring($PackageRoot.Length).TrimStart([char[]]"\/")
        $DestinationPath = Join-Path $PackageDestination $RelativePath
        $DestinationDirectory = Split-Path -Parent $DestinationPath
        New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $DestinationPath
    }

    $AssetDestination = Join-Path $PackageDestination "assets"
    New-Item -ItemType Directory -Path $AssetDestination -Force | Out-Null
    foreach ($AssetName in $RequiredAssets) {
        Copy-Item -LiteralPath (Join-Path (Join-Path $PackageRoot "assets") $AssetName) -Destination (Join-Path $AssetDestination $AssetName)
    }

    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    if (Test-Path -LiteralPath $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }

    Compress-Archive -LiteralPath $StagingRoot -DestinationPath $ZipPath -CompressionLevel Optimal

    $Archive = Get-Item -LiteralPath $ZipPath
    $Hash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash

    Write-Host ""
    Write-Host "Release ZIP created:" -ForegroundColor Green
    Write-Host "  $($Archive.FullName)"
    Write-Host "  Size: $([math]::Round($Archive.Length / 1MB, 2)) MB"
    Write-Host "  SHA256: $Hash"
    Write-Host ""
    Write-Host "Included: runtime application files, icon assets, dependency installers, README, LICENSE, and third-party notices."
    Write-Host "Excluded: tests, pyproject.toml, changelog, contributor/UI docs, build scripts, caches, and build artifacts."
}
finally {
    if (Test-Path -LiteralPath $StagingParent) {
        Remove-Item -LiteralPath $StagingParent -Recurse -Force -ErrorAction SilentlyContinue
    }
}
