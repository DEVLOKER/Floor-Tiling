<#
.SYNOPSIS
    Docker & WSL2 disk-space utility — clean images/containers, deep-purge, and
    compact the WSL2 docker_data.vhdx so freed space is returned to the C: drive.

.NOTES
    Standalone helper (not part of the build/run flow). Run from an elevated
    PowerShell for option [3] (diskpart/compact needs admin).
#>

# Ensure the terminal can display emojis properly
[console]::InputEncoding = [console]::OutputEncoding = [System.Text.Encoding]::UTF8
Clear-Host

# Helper function to center headers
function Write-Header ($text) {
    $line = "=" * 60
    Write-Host "`n$line" -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor White
    Write-Host "$line" -ForegroundColor Cyan
}

# Helper function for pausing
function Pause-Menu {
    Write-Host "`n[ℹ️] Press any key to return to the menu..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# Dynamic check to find the true literal path for diskpart
$vhdxPath = "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx"
if (-not (Test-Path $vhdxPath)) {
    # Fallback to check default profile path directly
    $vhdxPath = "C:\Users\$env:USERNAME\AppData\Local\Docker\wsl\disk\docker_data.vhdx"
}

do {
    Clear-Host
    Write-Header "🐳 DOCKER & WSL2 SPACE SAVER UTILITY 🐳"

    # Live space checking
    if (Test-Path $vhdxPath) {
        $fileSize = (Get-Item $vhdxPath).Length / 1GB
        Write-Host "📊 Current vhdx size: " -NoNewline -ForegroundColor Gray
        Write-Host ("{0:N2} GB" -f $fileSize) -ForegroundColor Yellow
        Write-Host "📍 Path: $vhdxPath" -ForegroundColor DarkGray
    } else {
        Write-Host "⚠️ Warning: docker_data.vhdx not detected at default location." -ForegroundColor Yellow
    }
    Write-Host "============================================================" -ForegroundColor Cyan

    # Menu Options
    Write-Host " [1] 🧼 Clean Containers & Images (Safe - Deletes Unused)" -ForegroundColor Green
    Write-Host " [2] 🚨 Deep Purge Everything (Deletes ALL Volumes & Data)" -ForegroundColor Yellow
    Write-Host " [3] 🗜️  Compact VHDX File (Shrink C:\ drive space)" -ForegroundColor Magenta
    Write-Host " [4] 📈 Show Current Docker Disk Usage Breakdown" -ForegroundColor Cyan
    Write-Host " [5] ❌ Exit" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Cyan

    $choice = Read-Host "👉 Select an option (1-5)"

    switch ($choice) {
        "1" {
            Clear-Host
            Write-Header "🧼 RUNNING SAFE CLEANUP"
            Write-Host "Running: docker system prune -a" -ForegroundColor Gray
            docker system prune -a --force
            Pause-Menu
        }
        "2" {
            Clear-Host
            Write-Header "🚨 RUNNING DEEP PURGE"
            Write-Host "⚠️ WARNING: This permanently deletes ALL local data volumes!" -ForegroundColor Red
            $confirm = Read-Host "Are you absolutely sure? (y/N)"
            if ($confirm -eq "y" -or $confirm -eq "Y") {
                Write-Host "Running: docker system prune -a --volumes" -ForegroundColor Gray
                docker system prune -a --volumes --force
            } else {
                Write-Host "❌ Operation canceled." -ForegroundColor Yellow
            }
            Pause-Menu
        }
        "3" {
            Clear-Host
            Write-Header "🗜️ COMPACTING VHDX VIRTUAL DISK"

            Write-Host "🛑 Step 1: Stopping WSL Subsystem..." -ForegroundColor Yellow
            wsl --shutdown
            Start-Sleep -Seconds 2

            if (Test-Path $vhdxPath) {
                Write-Host "📝 Step 2: Creating temporary diskpart script..." -ForegroundColor Yellow

                # Create a literal script text file for diskpart so variables aren't misinterpreted
                $dpScript = New-TemporaryFile
                @("select vdisk file=`"$vhdxPath`"", "compact vdisk", "exit") | Out-File $dpScript -Encoding ascii

                Write-Host "⚡ Step 3: Compacting virtual drive... (Please wait)" -ForegroundColor Cyan
                diskpart /s $dpScript.FullName

                # Cleanup temp script
                Remove-Item $dpScript -Force
                Write-Host "`n✅ Compact process finished successfully!" -ForegroundColor Green
            } else {
                Write-Host "❌ Error: Could not find the VHDX file to compact." -ForegroundColor Red
            }
            Pause-Menu
        }
        "4" {
            Clear-Host
            Write-Header "📈 DOCKER DISK USAGE BREAKDOWN"
            docker system df
            Pause-Menu
        }
        "5" {
            Clear-Host
            Write-Host "👋 Goodbye! Keep your disk clean." -ForegroundColor Cyan
            exit
        }
        default {
            Write-Host "❌ Invalid choice, try again." -ForegroundColor Red
            Start-Sleep -Seconds 1
        }
    }
} while ($true)
