<#
.SYNOPSIS
    Run commands for the Olist BDA project stack.
.DESCRIPTION
    Every project command goes through this script. It stops on the first failing
    step and prints what it is doing. Pass-through commands (hdfs, status,
    mongo-check, logs) write to the normal output stream so they can be piped.
.EXAMPLE
    .\tasks.ps1 up
    .\tasks.ps1 hdfs dfs -ls -R /olist
    .\tasks.ps1 validate --mongo
#>
param([string]$Command = "help")

# Deliberately a simple script: no [CmdletBinding()] and no [Parameter()]
# attribute, since either one turns on strict parameter binding. The
# pass-through arguments are taken from $args rather than a declared parameter.
# With strict binding, PowerShell prefix-matches a leading-dash argument against
# parameter names, so "hdfs dfs -ls -R /olist/raw" would bind -R to -Rest and
# fail. Collecting $args instead lets every hdfs flag through untouched.
$Rest = @($args)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Compose ignores services whose profile is not named, so every profile is
# listed whenever we need to see or stop the whole stack.
$AllProfiles = @("--profile", "hdfs", "--profile", "db", "--profile", "serve", "--profile", "jobs")
$HdfsServices = @("namenode", "datanode1", "datanode2")

# ---------------------------------------------------------------- helpers ----

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Note {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor DarkGray
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Exe $($Arguments -join ' ')"
    }
}

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    Invoke-Checked -Exe "docker" -Arguments (@("compose") + $Arguments)
}

function Test-EnvFile {
    $path = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path $path)) {
        throw ".env not found. See README.md for the command that generates it."
    }
}

function Get-RawFileMap {
    # Reads the flat "file: table" block under raw_files: in config/settings.yaml
    # so the CSV-to-table mapping has exactly one source of truth.
    $path = Join-Path $PSScriptRoot "config\settings.yaml"
    if (-not (Test-Path $path)) { throw "config/settings.yaml not found." }

    $map = [ordered]@{}
    $inBlock = $false
    foreach ($line in Get-Content $path) {
        if ($line -match '^raw_files:\s*$') { $inBlock = $true; continue }
        if (-not $inBlock) { continue }
        if ($line -match '^\S') { break }
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s+([^:#]+?)\s*:\s*(\S+)\s*$') {
            $map[$Matches[1].Trim()] = $Matches[2].Trim()
        }
    }
    if ($map.Count -eq 0) { throw "No raw_files entries found in config/settings.yaml" }
    return $map
}

function Get-ServiceId {
    param([string]$Service)
    $id = & docker compose @AllProfiles ps -q $Service 2>$null
    if ($id -is [array]) { $id = $id | Select-Object -First 1 }
    return $id
}

function Wait-Healthy {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [int]$TimeoutSeconds = 240
    )
    Write-Step "Waiting for $Service to report healthy"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $id = Get-ServiceId -Service $Service
        if ($id) {
            $status = & docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}nohealthcheck{{end}}' $id 2>$null
            if ($status -eq "healthy") {
                Write-Note "$Service is healthy"
                return
            }
            if ($status -eq "nohealthcheck") {
                Write-Note "$Service has no healthcheck; treating as ready"
                return
            }
        }
        Start-Sleep -Seconds 3
    }
    throw "$Service did not become healthy within $TimeoutSeconds seconds. Check: .\tasks.ps1 logs $Service"
}

function Invoke-Namenode {
    # Runs a command inside the namenode container (-T: no TTY, safe for piping).
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    Invoke-Compose -Arguments (@("--profile", "hdfs", "exec", "-T", "namenode") + $Arguments)
}

function Invoke-SparkJob {
    # One-off spark container per job, with the Spark UI published on 4040.
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    Test-EnvFile
    Invoke-Compose -Arguments (@("--profile", "jobs", "run", "--rm", "--service-ports", "spark") + $Arguments)
}

function Get-LiveDataNodeCount {
    $report = & docker compose --profile hdfs exec -T namenode hdfs dfsadmin -report 2>$null
    if (-not $report) { return -1 }
    $line = $report | Select-String -Pattern 'Live datanodes \((\d+)\)'
    if ($line) { return [int]$line.Matches[0].Groups[1].Value }
    return -1
}

# --------------------------------------------------------------- commands ----

function Invoke-Build {
    Test-EnvFile
    Write-Step "Building the spark and dashboard images"
    Write-Note "First build downloads Java and Python packages; expect several minutes."
    # The db profile is included so that mongo is part of the project: dashboard
    # declares depends_on mongo, and Compose resolves depends_on across the whole
    # project even when it is only building. mongo has no build section, so it is
    # skipped and nothing extra is built or started.
    Invoke-Compose -Arguments @("--profile", "jobs", "--profile", "serve", "--profile", "db", "build")
}

function Invoke-Up {
    Test-EnvFile
    Write-Step "Starting pipeline mode (HDFS cluster + MongoDB)"
    Invoke-Compose -Arguments @("--profile", "hdfs", "--profile", "db", "up", "-d")
    Wait-Healthy -Service "namenode"
    Wait-Healthy -Service "mongo"

    Write-Step "Creating the /olist root directory in HDFS"
    Invoke-Namenode -Arguments @("hdfs", "dfs", "-mkdir", "-p", "/olist")

    Write-Step "Pipeline mode is up"
    Write-Note "NameNode UI: http://localhost:9870"
    Write-Note "DataNode UIs: http://localhost:9864 and http://localhost:9865"
}

function Invoke-Serve {
    Test-EnvFile
    Write-Step "Switching to serve mode (stopping HDFS to free memory)"
    Invoke-Compose -Arguments (@("--profile", "hdfs", "stop") + $HdfsServices)

    Write-Step "Starting MongoDB and the dashboard"
    Invoke-Compose -Arguments @("--profile", "db", "--profile", "serve", "up", "-d")
    Wait-Healthy -Service "mongo"

    Write-Step "Serve mode is up"
    Write-Note "Dashboard: http://localhost:8501"
}

function Invoke-Down {
    Write-Step "Stopping all containers (volumes are never removed)"
    Invoke-Compose -Arguments ($AllProfiles + @("down"))
}

function Invoke-Status {
    Write-Step "Containers"
    & docker compose @AllProfiles ps

    Write-Step "HDFS live DataNodes"
    $count = Get-LiveDataNodeCount
    if ($count -ge 0) {
        "Live datanodes: $count"
    }
    else {
        "HDFS is not running (start it with: .\tasks.ps1 up)"
    }

    Write-Step "Resource use"
    & docker stats --no-stream
}

function Invoke-Download {
    Write-Step "Downloading the Kaggle CSVs into data/raw (skips files already present)"
    Invoke-SparkJob -Arguments @("python", "-m", "pipeline.jobs.download")
}

function Invoke-Ingest {
    Write-Step "Uploading the raw CSVs from /staging into HDFS"
    $map = Get-RawFileMap
    foreach ($file in $map.Keys) {
        $table = $map[$file]
        Write-Note "$file -> /olist/raw/$table/"
        Invoke-Namenode -Arguments @("hdfs", "dfs", "-mkdir", "-p", "/olist/raw/$table")
        Invoke-Namenode -Arguments @("hdfs", "dfs", "-put", "-f", "/staging/$file", "/olist/raw/$table/")
    }

    Write-Step "Space used by /olist/raw"
    & docker compose --profile hdfs exec -T namenode hdfs dfs -du -h /olist/raw

    Write-Step "Replication summary for /olist/raw"
    & docker compose --profile hdfs exec -T namenode hdfs fsck /olist/raw | Select-String -Pattern 'Average block replication|Total blocks|Corrupt blocks|Under-replicated'
}

function Invoke-Silver {
    Write-Step "Building the silver layer"
    Invoke-SparkJob -Arguments @("python", "-m", "pipeline.jobs.silver")
}

function Invoke-Gold {
    Write-Step "Building the gold layer"
    Invoke-SparkJob -Arguments @("python", "-m", "pipeline.jobs.gold")
}

function Invoke-Export {
    Write-Step "Exporting gold to MongoDB"
    Invoke-SparkJob -Arguments (@("python", "-m", "pipeline.jobs.export_mongo") + $Rest)
}

function Invoke-Validate {
    Write-Step "Running validation checks"
    Invoke-SparkJob -Arguments (@("python", "-m", "pipeline.jobs.validate") + $Rest)
}

function Invoke-Pipeline {
    Write-Step "Full pipeline: up, download, ingest, silver, gold, validate, export, validate --mongo"
    Invoke-Up
    Invoke-Download
    Invoke-Ingest
    Invoke-Silver
    Invoke-Gold
    Invoke-SparkJob -Arguments @("python", "-m", "pipeline.jobs.validate")
    Invoke-SparkJob -Arguments @("python", "-m", "pipeline.jobs.export_mongo")
    Invoke-SparkJob -Arguments @("python", "-m", "pipeline.jobs.validate", "--mongo")
    Write-Step "Pipeline finished"
}

function Invoke-Test {
    Write-Step "Running the test suite"
    Test-EnvFile
    # pytest.ini already sets addopts = -q; passing -q again makes it -qq, which
    # silences even the summary line.
    & docker compose --profile jobs run --rm spark pytest
    # pytest exits 5 when it collects no tests at all, which is expected until the
    # first real tests land in Phase 3. Anything else non-zero is a real failure.
    if ($LASTEXITCODE -eq 5) {
        Write-Note "No tests collected yet (pytest exit 5); treating as success."
        return
    }
    if ($LASTEXITCODE -ne 0) { throw "pytest failed (exit $LASTEXITCODE)" }
}

function Invoke-Lint {
    Write-Step "Linting with ruff"
    Test-EnvFile
    Invoke-Compose -Arguments @("--profile", "jobs", "run", "--rm", "spark", "ruff", "check", ".")
}

function Invoke-Hdfs {
    if ($Rest.Count -eq 0) {
        throw "Usage: .\tasks.ps1 hdfs <args>, for example: .\tasks.ps1 hdfs dfs -ls -R /olist"
    }
    & docker compose --profile hdfs exec -T namenode hdfs @Rest
    if ($LASTEXITCODE -ne 0) { throw "hdfs command failed (exit $LASTEXITCODE)" }
}

function Invoke-MongoCheck {
    Write-Step "Collections in MongoDB (read-only user)"
    # The password is read from the container's own environment, so it never
    # appears in a command line or in this script's output.
    # The JavaScript below uses single quotes only. Windows PowerShell 5.1
    # mangles embedded double quotes when handing an argument to a native
    # executable, which made mongosh read the script as command-line options.
    $js = "const dbName = process.env.MONGO_DB;" +
          "const pw = encodeURIComponent(process.env.OLIST_DASHBOARD_PASSWORD);" +
          "const uri = 'mongodb://olist_dashboard:' + pw + '@localhost:27017/' + dbName + '?authSource=' + dbName;" +
          "const d = Mongo(uri).getDB(dbName);" +
          "const names = d.getCollectionNames().sort();" +
          "if (names.length === 0) { print('(no collections yet - run the export task)'); }" +
          "names.forEach(function (c) { print(c.padEnd(24) + d.getCollection(c).countDocuments()); });"
    & docker compose --profile db exec -T mongo mongosh --quiet --eval $js
    if ($LASTEXITCODE -ne 0) { throw "mongo-check failed (exit $LASTEXITCODE)" }
}

function Invoke-SparkUi {
    Write-Step "Running Spark work, then holding the Spark UI open for screenshots"
    Write-Note "The Spark UI only exists while a job runs, so this job deliberately"
    Write-Note "stays alive after finishing. Open http://localhost:4040 when prompted."
    Write-Note "Press Ctrl+C when you have the screenshots."
    Invoke-SparkJob -Arguments (@("python", "-m", "pipeline.jobs.sparkui") + $Rest)
}

function Invoke-Notebook {
    Write-Step "Starting Jupyter Lab in the spark container"
    Write-Note "Open http://localhost:8888 and use the token printed below. Ctrl+C to stop."
    Test-EnvFile
    Invoke-Compose -Arguments @(
        "--profile", "jobs", "run", "--rm", "--service-ports", "spark",
        "jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root"
    )
}

function Invoke-Shell {
    Write-Step "Opening a shell in the spark container"
    Test-EnvFile
    Invoke-Compose -Arguments @("--profile", "jobs", "run", "--rm", "spark", "bash")
}

function Invoke-Logs {
    if ($Rest.Count -eq 0) { throw "Usage: .\tasks.ps1 logs <service>" }
    & docker compose @AllProfiles logs --tail 100 @Rest
}

function Invoke-FailoverDemo {
    Write-Step "HDFS failover demo: reads keep working with one DataNode down"

    Write-Step "1/6 Reading a file from HDFS with both DataNodes up"
    & docker compose --profile hdfs exec -T namenode bash -c "hdfs dfs -cat /olist/raw/orders/olist_orders_dataset.csv | head -3"
    if ($LASTEXITCODE -ne 0) { throw "Could not read the orders file. Run the ingest task first." }

    Write-Step "2/6 Stopping datanode2"
    Invoke-Compose -Arguments @("--profile", "hdfs", "stop", "datanode2")

    Write-Step "3/6 Waiting 100 seconds for the NameNode to mark it dead"
    Write-Note "dfs.namenode.heartbeat.recheck-interval is 30000 ms, so this takes about 90 s."
    for ($i = 100; $i -gt 0; $i -= 10) {
        Write-Note "$i seconds remaining"
        Start-Sleep -Seconds 10
    }

    Write-Step "4/6 Cluster report (expect 1 live, 1 dead)"
    & docker compose --profile hdfs exec -T namenode hdfs dfsadmin -report | Select-String -Pattern 'Live datanodes|Dead datanodes|^Name:|Decommission'

    Write-Step "5/6 Reading the same file again with only one DataNode"
    & docker compose --profile hdfs exec -T namenode bash -c "hdfs dfs -cat /olist/raw/orders/olist_orders_dataset.csv | head -3"
    if ($LASTEXITCODE -ne 0) { throw "Read failed with one DataNode down - replication is not working as expected." }
    Write-Note "Read succeeded: every block still had a replica on datanode1."

    Write-Step "6/6 Restarting datanode2 and waiting for 2 live nodes"
    Invoke-Compose -Arguments @("--profile", "hdfs", "start", "datanode2")
    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        $count = Get-LiveDataNodeCount
        Write-Note "Live datanodes: $count"
        if ($count -ge 2) { break }
        Start-Sleep -Seconds 10
    }
    if ((Get-LiveDataNodeCount) -lt 2) { throw "datanode2 did not rejoin within 180 seconds." }
    Write-Step "Failover demo complete: 2 live DataNodes again"
}

function Invoke-ResetHdfs {
    Write-Host ""
    Write-Host "This deletes /olist from HDFS (raw, silver and gold data)." -ForegroundColor Yellow
    Write-Host "Docker volumes are NOT touched and the NameNode is NOT reformatted." -ForegroundColor Yellow
    $answer = Read-Host "Type 'yes' to continue"
    if ($answer -ne "yes") {
        Write-Note "Cancelled; nothing was deleted."
        return
    }
    Write-Step "Removing /olist from HDFS"
    Invoke-Namenode -Arguments @("hdfs", "dfs", "-rm", "-r", "-f", "-skipTrash", "/olist")
    Invoke-Namenode -Arguments @("hdfs", "dfs", "-mkdir", "-p", "/olist")
    Write-Note "/olist is empty again."
}

function Invoke-Help {
    @"
Usage: .\tasks.ps1 <command> [args]

Stack
  build              build the spark and dashboard images
  up                 pipeline mode: HDFS cluster + MongoDB, then create /olist
  serve              serve mode: stop HDFS, start MongoDB + dashboard
  down               stop all containers (volumes are kept)
  status             container list, live DataNode count, resource use
  logs <service>     last 100 log lines for one service

Pipeline
  download           fetch the Kaggle CSVs into data/raw (skips existing)
  ingest             upload data/raw into /olist/raw in HDFS
  silver             build the silver layer
  gold               build the gold layer
  export [args]      export gold into MongoDB (for example --driver-fallback)
  validate [args]    run validation checks (for example --mongo)
  pipeline           the whole chain from up to validate --mongo

Checks and tools
  test               pytest
  lint               ruff check .
  hdfs <args>        run an hdfs command, e.g. hdfs dfs -ls -R /olist
  mongo-check        list MongoDB collections with document counts
  sparkui [--minutes N]  run Spark work and hold the Spark UI open at :4040
  notebook           Jupyter Lab on http://localhost:8888 (blocks until Ctrl+C)
  shell              bash inside the spark container
  failover-demo      stop a DataNode, prove reads still work, restart it
  reset-hdfs         delete /olist after confirmation (volumes are kept)
"@
}

# --------------------------------------------------------------- dispatch ----

try {
    switch ($Command.ToLower()) {
        "build"         { Invoke-Build }
        "up"            { Invoke-Up }
        "serve"         { Invoke-Serve }
        "down"          { Invoke-Down }
        "status"        { Invoke-Status }
        "logs"          { Invoke-Logs }
        "download"      { Invoke-Download }
        "ingest"        { Invoke-Ingest }
        "silver"        { Invoke-Silver }
        "gold"          { Invoke-Gold }
        "export"        { Invoke-Export }
        "validate"      { Invoke-Validate }
        "pipeline"      { Invoke-Pipeline }
        "test"          { Invoke-Test }
        "lint"          { Invoke-Lint }
        "hdfs"          { Invoke-Hdfs }
        "mongo-check"   { Invoke-MongoCheck }
        "sparkui"       { Invoke-SparkUi }
        "notebook"      { Invoke-Notebook }
        "shell"         { Invoke-Shell }
        "failover-demo" { Invoke-FailoverDemo }
        "reset-hdfs"    { Invoke-ResetHdfs }
        "help"          { Invoke-Help }
        default {
            Write-Host "Unknown command: $Command" -ForegroundColor Red
            Invoke-Help
            exit 1
        }
    }
    # A command that returned normally succeeded, even if the last native call it
    # made left a non-zero $LASTEXITCODE behind (pytest exit 5, for example).
    exit 0
}
catch {
    Write-Host ""
    Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
