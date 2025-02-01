# Parameters for the script with default values
Param(
    [string]$Organization = "histopathology",
    [string]$LocalRootPath = "E:\GitHub",
    # Path to Python (if python is in your PATH, you can simply use "python")
    [string]$PythonPath = "python",
    # Full path to your dump3.py script
    [string]$DumpScript = "D:\GitHub\repo2file\dump3.py",
    # Where to store all extracted text files
    [string]$ExtractedTextsDir = "D:\GitHub\PathologyCoder"
)

# Error handling function
function Write-ErrorLog {
    param(
        [string]$Message,
        [System.Management.Automation.ErrorRecord]$ErrorRecord
    )
    
    Write-Error "ERROR: $Message"
    if ($ErrorRecord) {
        Write-Error "Details: $($ErrorRecord.Exception.Message)"
    }
}

# 1. Ensure the root directory for repositories exists
try {
    if (-not (Test-Path $LocalRootPath)) {
        Write-Host "Creating directory $LocalRootPath..."
        New-Item -ItemType Directory -Path $LocalRootPath | Out-Null
    }
} catch {
    Write-ErrorLog "Failed to create or verify root directory" $_
    exit 1
}

# 2. Ensure the directory for extracted texts exists
try {
    if (-not (Test-Path $ExtractedTextsDir)) {
        Write-Host "Creating directory for extracted texts: $ExtractedTextsDir..."
        New-Item -ItemType Directory -Path $ExtractedTextsDir | Out-Null
    }
} catch {
    Write-ErrorLog "Failed to create or verify extracted texts directory" $_
    exit 1
}

# 3. Retrieve the list of repositories from the organization via GitHub CLI
Write-Host "Retrieving list of repositories from '$Organization'..."
try {
    $repoList = gh repo list $Organization --limit 300

    if (-not $repoList) {
        Write-Warning "No repositories found or an error occurred."
        exit 1
    }
} catch {
    Write-ErrorLog "Failed to retrieve repository list" $_
    exit 1
}

foreach ($repoLine in $repoList) {
    try {
        # Example line: "histopathology/wsidata Some description"
        $fields   = $repoLine -split '\s+'
        $fullName = $fields[0]              # e.g. histopathology/wsidata
        $repoName = $fullName.Split('/')[1] # e.g. wsidata

        Write-Host "`nProcessing repository: $fullName"

        # 4. Construct the local folder path where we'll clone the repo
        $destination = Join-Path $LocalRootPath $repoName

        # 5. Determine the default branch
        Write-Host "Finding default branch for $repoName..."
        $defaultBranch = gh api "repos/$fullName" -q ".default_branch"
        if (-not $defaultBranch) {
            Write-Warning "Failed to get default branch for $fullName; defaulting to 'main'."
            $defaultBranch = "main"
        }
        Write-Host "Default branch for $repoName is '$defaultBranch'."

        # 6. Clone if needed
        if (-not (Test-Path $destination)) {
            Write-Host "Local clone not found. Cloning $fullName -> $destination..."
            gh repo clone $fullName $destination

            # Optionally check out the default branch after cloning
            Push-Location $destination
            git checkout $defaultBranch 2>$null
            Pop-Location
        }
        else {
            Write-Host "Repository folder already exists at $destination. Pulling latest changes..."
            Push-Location $destination
            # Checkout the default branch and pull
            git checkout $defaultBranch 2>$null
            git pull origin $defaultBranch
            Pop-Location
        }

        # 7. Prepare to run dump3.py
        $repoPath      = Join-Path $LocalRootPath $repoName
        $repoTextFile  = Join-Path $ExtractedTextsDir "$($repoName).txt"
        $repoGitignore = Join-Path $repoPath ".gitignore"
        $excludeFile   = "exclude.txt"
        $skipSubstring = "iVBORw0"

        # Ensure old <repoName>.txt is removed so it's always fresh
        if (Test-Path $repoTextFile) {
            Write-Host "Removing existing file $repoTextFile so it can be overwritten..."
            Remove-Item $repoTextFile -Force
        }

        Write-Host "Running $DumpScript on $repoPath..."
        # Build an array of arguments for python
        $arguments = @(
            $DumpScript
            "`"$repoPath`""       # 1) repository path
            $repoTextFile         # 2) text file path
            "`"$repoGitignore`""  # 3) .gitignore path
            $excludeFile          # 4) exclude file
            "--skip-substring"    # 5) skip-substring
            $skipSubstring
            "--max-chunk-size"    # 6) new argument
            "2"
        )

        # Change directory to the repo, run python with the arguments
        Push-Location $repoPath
        try {
            & $PythonPath $arguments
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Dump script exited with code $LASTEXITCODE for $repoName"
            }
        } catch {
            Write-ErrorLog "Failed to run dump script for repository: $repoName" $_
        } finally {
            Pop-Location
        }
    } catch {
        Write-ErrorLog "Failed to process repository: $repoName" $_
        continue  # Continue with next repository even if this one failed
    }
}

Write-Host "`nScript completed!" -ForegroundColor Green