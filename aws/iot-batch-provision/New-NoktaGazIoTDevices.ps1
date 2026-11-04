[CmdletBinding()]
param(
    [int]$StartNumber = 201,
    [int]$EndNumber = 400,
    [string]$Region = "eu-north-1",
    [string]$PolicyName = "NoktaGazCihazPolitikasi",
    [string]$OutputRoot = (Join-Path (Get-Location) ("NoktaGaz-IoT-{0:D4}-{1:D4}" -f $StartNumber, $EndNumber))
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($StartNumber -lt 1 -or $EndNumber -lt $StartNumber -or ($EndNumber - $StartNumber + 1) -gt 500) {
    throw "Invalid device range."
}

$expectedCount = $EndNumber - $StartNumber + 1
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$outputParent = Split-Path -Parent $OutputRoot
$expectedLeaf = "NoktaGaz-IoT-{0:D4}-{1:D4}" -f $StartNumber, $EndNumber
if ((Split-Path -Leaf $OutputRoot) -ne $expectedLeaf) {
    throw "Output directory name must be $expectedLeaf."
}

function Invoke-AwsJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $result = & aws @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($result -join [Environment]::NewLine)
    }
    if (-not $result) {
        return $null
    }
    return ($result -join [Environment]::NewLine) | ConvertFrom-Json
}

function Invoke-AwsQuiet {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & aws @Arguments *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "AWS command failed: aws $($Arguments -join ' ')"
    }
}

$identity = Invoke-AwsJson -Arguments @("sts", "get-caller-identity", "--output", "json")
if ($identity.Account -ne "692859916285") {
    throw "Unexpected AWS account: $($identity.Account)"
}

$endpointResult = Invoke-AwsJson -Arguments @(
    "iot", "describe-endpoint", "--endpoint-type", "iot:Data-ATS",
    "--region", $Region, "--output", "json"
)
$endpoint = $endpointResult.endpointAddress
$existingThingResult = Invoke-AwsJson -Arguments @(
    "iot", "list-things", "--region", $Region,
    "--query", "things[].thingName", "--output", "json"
)
$existingThings = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($existingThingName in $existingThingResult) {
    [void]$existingThings.Add([string]$existingThingName)
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$resolvedRoot = (Resolve-Path -LiteralPath $OutputRoot).Path
if ($resolvedRoot -ne $OutputRoot) {
    $OutputRoot = $resolvedRoot
}

# The directory contains device private keys. Restrict it to the current user and SYSTEM.
$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls $OutputRoot /inheritance:r /grant:r "${currentIdentity}:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Could not restrict NTFS permissions on $OutputRoot"
}

$rootCaPath = Join-Path $OutputRoot "AmazonRootCA1.pem"
if (-not (Test-Path -LiteralPath $rootCaPath)) {
    Invoke-WebRequest -Uri "https://www.amazontrust.com/repository/AmazonRootCA1.pem" -OutFile $rootCaPath -UseBasicParsing
}
if ((Get-Item -LiteralPath $rootCaPath).Length -lt 1000) {
    throw "Downloaded AmazonRootCA1.pem is unexpectedly small."
}

$manifestPath = Join-Path $OutputRoot "manifest.csv"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    'ThingName,CertificateId,CertificateArn,Endpoint,PolicyName' | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}

$readmePath = Join-Path $OutputRoot "README.txt"
@"
NoktaGaz AWS IoT device credentials: $expectedLeaf

CONFIDENTIAL: Every device directory contains a unique private key.
Never share one device's private key with another device and never commit these files to Git.

AWS account: $($identity.Account)
Region: $Region
MQTT endpoint: $endpoint
MQTT TLS port: 8883
IoT policy: $PolicyName

Each device directory contains:
- certificate.pem.crt       Device certificate
- private.pem.key           CONFIDENTIAL device private key
- public.pem.key            Public key
- AmazonRootCA1.pem         Amazon Trust root CA
- device-config.json        Thing name, endpoint, topics and file names

The MQTT client ID must exactly match the Thing name.
Publish topic: depo/{ThingName}/telemetry
Subscribe topic: depo/{ThingName}/komut
"@ | Set-Content -LiteralPath $readmePath -Encoding UTF8

$completed = 0
foreach ($number in $StartNumber..$EndNumber) {
    $thingName = "NoktaGaz-{0:D4}" -f $number
    $devicePath = Join-Path $OutputRoot $thingName
    $completeMarker = Join-Path $devicePath ".provisioned"

    $thingExists = $existingThings.Contains($thingName)

    if ($thingExists -and (Test-Path -LiteralPath $completeMarker)) {
        $completed++
        Write-Output "[$completed/$expectedCount] $thingName already complete; skipped."
        continue
    }
    if ($thingExists) {
        throw "$thingName already exists in AWS but has no matching local completion marker. Stopping safely."
    }
    if (Test-Path -LiteralPath $devicePath) {
        throw "$devicePath exists without a completed AWS Thing. Stopping safely."
    }

    New-Item -ItemType Directory -Path $devicePath | Out-Null
    $thingCreated = $false
    $certificateId = $null
    $certificateArn = $null
    $principalAttached = $false
    $policyAttached = $false

    try {
        Invoke-AwsQuiet -Arguments @(
            "iot", "create-thing", "--thing-name", $thingName,
            "--region", $Region
        )
        $thingCreated = $true
        [void]$existingThings.Add($thingName)

        $certificatePath = Join-Path $devicePath "certificate.pem.crt"
        $privateKeyPath = Join-Path $devicePath "private.pem.key"
        $publicKeyPath = Join-Path $devicePath "public.pem.key"
        $certificate = Invoke-AwsJson -Arguments @(
            "iot", "create-keys-and-certificate", "--set-as-active",
            "--certificate-pem-outfile", $certificatePath,
            "--private-key-outfile", $privateKeyPath,
            "--public-key-outfile", $publicKeyPath,
            "--region", $Region,
            "--query", "{certificateId:certificateId,certificateArn:certificateArn}",
            "--output", "json"
        )
        $certificateId = $certificate.certificateId
        $certificateArn = $certificate.certificateArn

        Invoke-AwsQuiet -Arguments @(
            "iot", "attach-thing-principal", "--thing-name", $thingName,
            "--principal", $certificateArn, "--region", $Region
        )
        $principalAttached = $true

        Invoke-AwsQuiet -Arguments @(
            "iot", "attach-policy", "--policy-name", $PolicyName,
            "--target", $certificateArn, "--region", $Region
        )
        $policyAttached = $true

        Copy-Item -LiteralPath $rootCaPath -Destination (Join-Path $devicePath "AmazonRootCA1.pem")
        $config = [ordered]@{
            thingName = $thingName
            clientId = $thingName
            endpoint = $endpoint
            port = 8883
            region = $Region
            publishTopic = "depo/$thingName/telemetry"
            subscribeTopic = "depo/$thingName/komut"
            certificateFile = "certificate.pem.crt"
            privateKeyFile = "private.pem.key"
            publicKeyFile = "public.pem.key"
            rootCaFile = "AmazonRootCA1.pem"
        }
        $config | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $devicePath "device-config.json") -Encoding UTF8

        foreach ($requiredFile in @("certificate.pem.crt", "private.pem.key", "public.pem.key", "AmazonRootCA1.pem", "device-config.json")) {
            $requiredPath = Join-Path $devicePath $requiredFile
            if (-not (Test-Path -LiteralPath $requiredPath) -or (Get-Item -LiteralPath $requiredPath).Length -eq 0) {
                throw "Missing or empty output file: $requiredPath"
            }
        }

        "$thingName,$certificateId,$certificateArn,$endpoint,$PolicyName" | Add-Content -LiteralPath $manifestPath -Encoding UTF8
        "Provisioned $(Get-Date -Format o)" | Set-Content -LiteralPath $completeMarker -Encoding ASCII
        $completed++
        Write-Output "[$completed/$expectedCount] $thingName created and packaged."
    }
    catch {
        Write-Warning "Provisioning failed for $thingName. Rolling back only this incomplete device. $($_.Exception.Message)"
        if ($policyAttached -and $certificateArn) {
            & aws iot detach-policy --policy-name $PolicyName --target $certificateArn --region $Region *> $null
        }
        if ($principalAttached -and $certificateArn) {
            & aws iot detach-thing-principal --thing-name $thingName --principal $certificateArn --region $Region *> $null
        }
        if ($certificateId) {
            & aws iot update-certificate --certificate-id $certificateId --new-status INACTIVE --region $Region *> $null
            & aws iot delete-certificate --certificate-id $certificateId --region $Region *> $null
        }
        if ($thingCreated) {
            & aws iot delete-thing --thing-name $thingName --region $Region *> $null
        }

        if (Test-Path -LiteralPath $devicePath) {
            $resolvedDevicePath = (Resolve-Path -LiteralPath $devicePath).Path
            $expectedPrefix = $OutputRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
            if (-not $resolvedDevicePath.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove unexpected rollback path: $resolvedDevicePath"
            }
            Remove-Item -LiteralPath $resolvedDevicePath -Recurse -Force
        }
        throw
    }
}

$deviceDirectories = Get-ChildItem -LiteralPath $OutputRoot -Directory | Where-Object { $_.Name -match '^NoktaGaz-\d{4}$' }
if ($deviceDirectories.Count -ne $expectedCount) {
    throw "Expected $expectedCount device directories, found $($deviceDirectories.Count)."
}

$archivePath = "$OutputRoot.zip"
if (Test-Path -LiteralPath $archivePath) {
    throw "Archive already exists; refusing to overwrite: $archivePath"
}

& tar.exe -a -c -f $archivePath -C $outputParent (Split-Path -Leaf $OutputRoot)
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $archivePath)) {
    throw "Could not create archive: $archivePath"
}

$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
$hashLine = "$($hash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $archivePath)"
$hashLine | Set-Content -LiteralPath "$archivePath.sha256" -Encoding ASCII

Write-Output "COMPLETE"
Write-Output "Devices: $expectedCount"
Write-Output "Directory: $OutputRoot"
Write-Output "Archive: $archivePath"
Write-Output "SHA256: $($hash.Hash.ToLowerInvariant())"
