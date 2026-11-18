# End-to-end check of the compiled exe against the REAL Worker code running locally (wrangler dev --local).
# Nothing here touches your live Cloudflare. Run from the labkit folder:  powershell -File smoke_test.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$exe  = Join-Path $root "dist\siraugga-lab.exe"
if (-not (Test-Path $exe)) { throw "Build first: build_windows.bat" }
$tmp  = Join-Path $env:TEMP "lab_smoke_$(Get-Random)"; New-Item -ItemType Directory $tmp | Out-Null
$secret = "smoke-" + [guid]::NewGuid().ToString("N")          # throwaway, local only
$port = 8799

Push-Location $root
npx --yes wrangler@4 d1 execute mikeytech --config wrangler.toml --local --persist-to "$tmp\d1" --file lab_schema.sql | Out-Null
$dev = Start-Process -PassThru -WindowStyle Hidden -FilePath "cmd.exe" -ArgumentList "/c npx --yes wrangler@4 dev --config wrangler.toml --local --persist-to `"$tmp\d1`" --port $port --var LAB_MASTER_SECRET:$secret > `"$tmp\dev.log`" 2>&1"
$ok = $false
for ($i = 0; $i -lt 60 -and -not $ok; $i++) { Start-Sleep 1; $ok = (Get-Content "$tmp\dev.log" -ErrorAction SilentlyContinue) -match "Ready on" }
if (-not $ok) { throw "local Worker did not start, see $tmp\dev.log" }

$env:LAB_MASTER_SECRET = $secret
$key = python issue_key.py smoke-learner
Remove-Item Env:LAB_MASTER_SECRET
$env:LOCALAPPDATA = $tmp
$env:SIRAUGGA_LAB_API = "http://127.0.0.1:$port/lab"
& $exe login smoke-learner $key | Out-Null
$out = "ls`ncat notes.txt`necho c2lyYXVnZ2E= > s.txt`nbase64 -d s.txt`nlabctl complete linux-basics-01" | & $exe run linux-basics-01
$real = ($out -join "`n") -match "\[server\] labctl: registered"

# offline -> queue -> sync
$env:SIRAUGGA_LAB_API = "http://127.0.0.1:9"
$off = "ls`ncat notes.txt`necho c2lyYXVnZ2E= > s.txt`nbase64 -d s.txt`nlabctl complete linux-basics-01" | & $exe run linux-basics-01 --restart
$sim = ($off -join "`n") -match "SIMULATED"
$env:SIRAUGGA_LAB_API = "http://127.0.0.1:$port/lab"
$sync = & $exe sync
Pop-Location
Stop-Process -Id $dev.Id -Force -ErrorAction SilentlyContinue
Get-Process workerd -ErrorAction SilentlyContinue | Stop-Process -Force

"server step (online):   " + $(if ($real) {"PASS"} else {"FAIL"})
"simulated when offline: " + $(if ($sim)  {"PASS"} else {"FAIL"})
"sync after offline:     " + $(if ($sync -match "sent 1, still waiting 0") {"PASS"} else {"FAIL ($sync)"})
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
