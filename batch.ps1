# run.ps1
# Activate venv and run main.py from this directory

# Change to script location
Set-Location -Path $PSScriptRoot

# Activate virtual environment
& "$PSScriptRoot\venv\Scripts\Activate.ps1"

# Run the main script (adjust file name if different)
python batchincamaro.py