#!/usr/bin/env python3
import sqlite3, json

conn = sqlite3.connect('data/stock_analyzer.db')
c = conn.cursor()

# Check 002901 specifically
c.execute("SELECT code, formula_expr, logic_desc, a1, a2, a3, opportunity_dates, source, explored_at FROM best_formulas WHERE code = '002901'")
row = c.fetchone()
if row:
    print('=== 002901 best_formulas ===')
    print('code:', row[0])
    print('formula_expr:', row[1])
    print('a1:', row[3], 'a2:', row[4], 'a3:', row[5])
    print('opp_count:', row[7])
    opp_dates = row[6]
    source = row[7]
    explored_at = row[8]
    if opp_dates:
        dates = json.loads(opp_dates)
        print('opp_dates count:', len(dates) if opp_dates else 0, 'first 5:', dates[:5] if opp_dates else 'N/A')
    else:
        print('opp_dates: NULL/empty')
    print('source:', source)
    print('explored_at:', explored_at)
else:
    print('002901: NO formula in best_formulas')

# Check kline count
c.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM daily_kline WHERE code = '002901'")
kc = c.fetchone()
print()
print('=== 002901 K线 ===')
print('count:', kc[0], 'range:', kc[1], '~', kc[2])

# Check opportunity_points table
c.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM opportunity_points WHERE code = '002901'")
op = c.fetchone()
print()
print('=== 002901 opportunity_points ===')
print('count:', op[0], 'range:', op[1], '~', op[2])