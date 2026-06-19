#!/usr/bin/env python3
"""Simulate the FULL browser flow for a given stock, step by step"""
import requests, json, time

BASE = 'http://127.0.0.1:18080'

def get(path):
    r = requests.get(f'{BASE}{path}')
    r.raise_for_status()
    return r.json()

def post(path, json=None):
    r = requests.post(f'{BASE}{path}', json=json)
    r.raise_for_status()
    return r.json()

# Pick a stock WITHOUT formula (002463) to test the FULL flow
# Then also test one WITH formula (000001)
for code in ['002463', '000001']:
    print(f"\n{'='*60}")
    print(f"STOCK: {code}")
    print(f"{'='*60}")

    # Step 1: selectStock in browser → loadFormulas
    formulas = get(f'/api/formulas/{code}')
    print(f"\n[Step1] loadFormulas → formulas count: {len(formulas)}")
    if formulas:
        f = formulas[0]
        print(f"  a1={f['a1']}, a2={f['a2']}, a3={f['a3']}, hasFormula={True}")
    else:
        print(f"  hasFormula={False}")

    # Step 2: loadKlineData (all records)
    kline = get(f'/api/kline/{code}')
    print(f"\n[Step2] loadKlineData → {len(kline)} records, {kline[0]['date']} ~ {kline[-1]['date']}")

    # Step 3: loadOpportunityPoints
    opp = get(f'/api/formulas/{code}/opportunity')
    print(f"\n[Step3] loadOpportunityPoints → count: {opp['count']}, has_formula: {opp['has_formula']}")

    # If no formula, save one via override
    if not formulas:
        formula_expr = "MACD_HIST > 0 and BOLL_L > BOLL_M - 0.5 and ATR < MA20 and VOL_RATIO > 1.5"
        logic_desc = "MACD红柱且布袋下轨支撑且ATR适中且成交量放大"
        r = post(f'/api/formulas/{code}/override', json={
            "formula_expr": formula_expr,
            "logic_desc": logic_desc
        })
        print(f"\n[Step3b] overrideFormula → {r}")
        formulas = get(f'/api/formulas/{code}')
        print(f"  reload formulas: a1={formulas[0]['a1']}, a2={formulas[0]['a2']}, a3={formulas[0]['a3']}")

    # Step 4: loadOpportunityPoints (check again after override)
    opp2 = get(f'/api/formulas/{code}/opportunity')
    print(f"\n[Step4] after override, opp count: {opp2['count']}")

    # Step 5: Click "更新机会点" → updateOpportunitiesSingle
    print(f"\n[Step5] clicking '更新机会点'...")
    result = post(f'/api/formulas/{code}/update-opportunities')
    print(f"  result: {result}")

    # Step 6: reload formulas (a1/a2/a3 should now be non-zero)
    formulas2 = get(f'/api/formulas/{code}')
    f2 = formulas2[0]
    print(f"\n[Step6] reloadFormulas → a1={f2['a1']}, a2={f2['a2']}, a3={f2['a3']}")

    # Step 7: reload opportunity points
    opp3 = get(f'/api/formulas/{code}/opportunity')
    print(f"\n[Step7] reloadOpportunityPoints → count: {opp3['count']}")

    # Step 8: Simulate getMarkPoints
    print(f"\n[Step8] Simulating getMarkPoints (showOpp=true, hasFormula=true):")
    kline_dates = set(d['date'] for d in kline)
    matching = [d for d in opp3['opp_dates'] if d in kline_dates]
    print(f"  opp dates in kline range: {len(matching)} / {len(opp3['opp_dates'])}")
    if not matching:
        print(f"  WARNING: 0 marks! opp first dates: {opp3['opp_dates'][:5]}")
        print(f"  kline first dates: {list(kline_dates)[:5]}")
        # Check overlap
        opp_first = opp3['opp_dates'][0] if opp3['opp_dates'] else None
        kl_first = list(kline_dates)[0]
        if opp_first:
            print(f"  opp_first={opp_first} vs kl_first={kl_first} → overlap={opp_first >= kl_first}")