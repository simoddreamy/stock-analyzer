#!/usr/bin/env python3
import requests, json

BASE = 'http://127.0.0.1:18080'
code = '002901'

formula_expr = 'MACD_HIST > 0 and BOLL_L > BOLL_M - 0.5 and ATR < MA20 and VOL_RATIO > 1.5'
logic_desc = 'MACD红柱布袋支撑ATR适中量能放大'

# Step 1: Save formula
r = requests.post(f'{BASE}/api/formulas/{code}/override', json={
    'formula_expr': formula_expr,
    'logic_desc': logic_desc
})
print('[Step1] override:', r.json())

# Step 2: Check formula before update
r2 = requests.get(f'{BASE}/api/formulas/{code}')
f = r2.json()[0]
opp_before = f.get('opportunity_dates', []) or []
print(f'[Step2] BEFORE update-opportunities:')
print(f'  a1={f["a1"]}, a2={f["a2"]}, a3={f["a3"]}')
print(f'  opp_dates count: {len(opp_before)}, first 3: {opp_before[:3]}')

# Step 3: Update opportunities (click "更新机会点")
r3 = requests.post(f'{BASE}/api/formulas/{code}/update-opportunities')
result = r3.json()
print(f'[Step3] update-opportunities: {result}')

# Step 4: Reload and check
r4 = requests.get(f'{BASE}/api/formulas/{code}')
f4 = r4.json()[0]
opp_after = f4.get('opportunity_dates', []) or []
print(f'[Step4] AFTER update-opportunities:')
print(f'  a1={f4["a1"]}, a2={f4["a2"]}, a3={f4["a3"]}')
print(f'  opp_dates count: {len(opp_after)}, first 3: {opp_after[:3]}')

# Step 5: Check kline range
r5 = requests.get(f'{BASE}/api/kline/{code}')
kline = r5.json()
print(f'[Step5] kline: {len(kline)} records, {kline[0]["date"]} ~ {kline[-1]["date"]}')

# Step 6: Simulate markPoints (what the frontend chart does)
kline_dates = set(d['date'] for d in kline)
matching = [d for d in opp_after if d in kline_dates]
print(f'[Step6] markPoints that WOULD appear on chart: {len(matching)} / {len(opp_after)}')
if opp_after and not matching:
    print(f'  WARNING: opp_dates exist but none overlap with kline range!')
    print(f'  opp first date: {opp_after[0]}, kline first date: {kline[0]["date"]}')