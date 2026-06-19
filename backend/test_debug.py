import sqlite3, json
conn = sqlite3.connect('data/stock_analyzer.db')

# Check the flow for all stocks
cur = conn.execute('SELECT code, source, a1, a2, a3, opportunity_dates FROM best_formulas ORDER BY ROWID DESC')
print('=== best_formulas ===')
for r in cur.fetchall():
    opp = json.loads(r[5]) if r[5] else []
    print('code=%s source=%s a1=%s a2=%s a3=%s opp_count=%d' % (r[0], r[1], r[2], r[3], r[4], len(opp)))

# Test the update flow for a specific stock using simulate
code = '000001'
fm = conn.execute('SELECT formula_expr, logic_desc FROM best_formulas WHERE code=? ORDER BY ROWID DESC LIMIT 1', (code,)).fetchone()
print('\nformula for %s: %s' % (code, fm[0][:60] if fm else 'NONE'))
print('logic_desc: %s' % (fm[1] if fm else 'NONE'))

# Check formula_overrides
cur2 = conn.execute('SELECT code, formula_expr, logic_desc FROM formula_overrides ORDER BY ROWID DESC LIMIT 5')
print('\n=== formula_overrides ===')
for r in cur2.fetchall():
    print('code=%s formula=%s' % (r[0], (r[1] or '')[:60]))

conn.close()