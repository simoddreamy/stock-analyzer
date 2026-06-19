$ErrorActionPreference = 'Stop'
$headers = @{}
$headers['Content-Type'] = 'application/json'

$base = 'http://127.0.0.1:18080'
$code = '000001'

Write-Host "=== Testing update-opportunities flow ===" -ForegroundColor Cyan

# Step 1: GET formulas
$r1 = Invoke-WebRequest -Uri "$base/api/formulas/$code" -Method GET
$f1 = ConvertFrom-Json $r1.Content
Write-Host "`n[Step1] loadFormulas" -ForegroundColor Yellow
Write-Host "  count: $($f1.Count)"
if ($f1.Count -gt 0) {
    Write-Host "  a1=$($f1[0].a1) a2=$($f1[0].a2) a3=$($f1[0].a3)"
    Write-Host "  formula_expr: $($f1[0].formula_expr)"
}

# Step 2: GET opportunity points
$r2 = Invoke-WebRequest -Uri "$base/api/formulas/$code/opportunity" -Method GET
$opp = ConvertFrom-Json $r2.Content
Write-Host "`n[Step2] loadOpportunityPoints" -ForegroundColor Yellow
Write-Host "  count=$($opp.count) has_formula=$($opp.has_formula)"
if ($opp.opp_dates.Count -gt 0) {
    Write-Host "  first 3: $($opp.opp_dates[0..2] -join ', ')"
}

# Step 3: POST update-opportunities
Write-Host "`n[Step3] Click '更新机会点'..." -ForegroundColor Yellow
$r3 = Invoke-WebRequest -Uri "$base/api/formulas/$code/update-opportunities" -Method POST -ContentType 'application/json'
$result = ConvertFrom-Json $r3.Content
Write-Host "  Result: $($result | ConvertTo-Json -Compress)"

# Step 4: GET formulas again
$r4 = Invoke-WebRequest -Uri "$base/api/formulas/$code" -Method GET
$f4 = ConvertFrom-Json $r4.Content
Write-Host "`n[Step4] reloadFormulas" -ForegroundColor Yellow
if ($f4.Count -gt 0) {
    Write-Host "  a1=$($f4[0].a1) a2=$($f4[0].a2) a3=$($f4[0].a3)"
}

# Step 5: GET opportunity points again
$r5 = Invoke-WebRequest -Uri "$base/api/formulas/$code/opportunity" -Method GET
$opp5 = ConvertFrom-Json $r5.Content
Write-Host "`n[Step5] reloadOpportunityPoints" -ForegroundColor Yellow
Write-Host "  count=$($opp5.count)"

# Step 6: GET kline (check date range)
$r6 = Invoke-WebRequest -Uri "$base/api/kline/$code" -Method GET
$kline = ConvertFrom-Json $r6.Content
Write-Host "`n[Step6] kline" -ForegroundColor Yellow
Write-Host "  count=$($kline.Count) first=$($kline[0].date) last=$($kline[-1].date)"

# Step 7: Count matching opp dates in kline range
Write-Host "`n[Step7] markPoints simulation" -ForegroundColor Yellow
$kline_dates = @{}
foreach ($k in $kline) { $kline_dates[$k.date] = $true }
$matching = @($opp5.opp_dates | Where-Object { $kline_dates.ContainsKey($_) })
Write-Host "  opp in kline range: $($matching.Count) / $($opp5.count)"
if ($matching.Count -eq 0) {
    Write-Host "  PROBLEM: No opportunity points in kline range!" -ForegroundColor Red
} else {
    Write-Host "  first 3 matching: $($matching[0..2] -join ', ')"
}