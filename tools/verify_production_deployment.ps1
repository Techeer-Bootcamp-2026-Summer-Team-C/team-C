[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [int]$MinimumOpenApiPaths = 25,
    [string]$SshHost
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")

function Invoke-CheckedRequest {
    param([Parameter(Mandatory)][string]$Path)

    if ($SshHost) {
        $content = & ssh $SshHost curl --fail --silent --show-error --max-time 15 "$base$Path"
        if ($LASTEXITCODE -ne 0) {
            throw "$Path failed through SSH host $SshHost."
        }
        return [pscustomobject]@{
            StatusCode = 200
            Content = $content -join "`n"
        }
    }

    $response = Invoke-WebRequest -Uri "$base$Path" -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -ne 200) {
        throw "$Path returned HTTP $($response.StatusCode)."
    }
    return $response
}

$nginx = Invoke-CheckedRequest -Path "/nginx-health"
if ($nginx.Content.Trim() -ne "ok") {
    throw "/nginx-health returned an unexpected body."
}

$readyResponse = Invoke-CheckedRequest -Path "/health/ready"
$ready = $readyResponse.Content | ConvertFrom-Json
if ($ready.status -ne "ready") {
    throw "/health/ready did not report ready."
}

$openApiResponse = Invoke-CheckedRequest -Path "/openapi.json"
$openApi = $openApiResponse.Content | ConvertFrom-Json
$paths = @($openApi.paths.PSObject.Properties.Name)
$requiredPaths = @(
    "/api/v1/users/me/locale",
    "/api/v1/dashboard/layouts/{dashboardKey}",
    "/api/v1/endpoints/{endpointId}/process-tree"
)

if ($paths.Count -lt $MinimumOpenApiPaths) {
    throw "OpenAPI exposes $($paths.Count) paths; expected at least $MinimumOpenApiPaths."
}

$missingPaths = @($requiredPaths | Where-Object { $_ -notin $paths })
if ($missingPaths.Count -gt 0) {
    throw "OpenAPI is missing required paths: $($missingPaths -join ', ')"
}

[pscustomobject]@{
    BaseUrl = $base
    Transport = if ($SshHost) { "ssh:$SshHost" } else { "direct" }
    NginxHealth = "ok"
    ApplicationReadiness = $ready.status
    OpenApiPathCount = $paths.Count
    RequiredPaths = "present"
}
