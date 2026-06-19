#!/usr/bin/env python3
"""Check BOLL_L > BOLL_M - 0.5 across FULL dataset for 002901"""
import sys
sys.path.insert(0, 'C:/Users/Administrator/.openclaw/workspace/stock_analyzer/backend')

import sqlite3
import pandas as pd
from indicators.calculator import precompute_indicators_for_stock

code = '002901'
conn = sqlite3.connect('data/stock_analyzer.db')
kline_rows = conn.execute(
    "SELECT date, open, high, low, close, volume FROM daily_kline WHERE code = :code ORDER BY date",
    {"code": code}
).fetchall()
conn.close()

df = pd.DataFrame(kline_rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
df['date'] = df['date'].astype(str)
indicator_df = precompute_indicators_for_stock(code, df)

# Filter to rows where all BOLL values are non-null
mask_valid = indicator_df['BOLL_L'].notna() & indicator_df['BOLL_M'].notna()
df_valid = indicator_df[mask_valid].copy()
print(f"Total rows: {len(indicator_df)}, with valid BOLL: {len(df_valid)}")

# Check the condition
df_valid['cond_BOLL'] = df_valid['BOLL_L'] > df_valid['BOLL_M'] - 0.5
true_count = (df_valid['cond_BOLL'] == True).sum()
print(f"BOLL_L > BOLL_M - 0.5: {true_count} True out of {len(df_valid)}")

# Show sample rows where condition is TRUE
if true_count > 0:
    true_rows = df_valid[df_valid['cond_BOLL']]
    print(f"\nSample TRUE rows (first 5):")
    print(true_rows[['date', 'BOLL_L', 'BOLL_M', 'BOLL_U']].head(5).to_string())
    print(f"\nSample FALSE rows (first 5):")
    false_rows = df_valid[~df_valid['cond_BOLL']]
    print(false_rows[['date', 'BOLL_L', 'BOLL_M', 'BOLL_U']].head(5).to_string())
else:
    # If still 0, look at the actual BOLL_L vs BOLL_M values
    print("\nBOLL value statistics:")
    print(df_valid[['BOLL_L', 'BOLL_M', 'BOLL_U']].describe().to_string())
    print(f"\nBOLL_L range: {df_valid['BOLL_L'].min():.2f} ~ {df_valid['BOLL_L'].max():.2f}")
    print(f"BOLL_M range: {df_valid['BOLL_M'].min():.2f} ~ {df_valid['BOLL_M'].max():.2f}")
    print(f"\nFor condition BOLL_L > BOLL_M - 0.5 to be TRUE:")
    print(f"  need BOLL_L > BOLL_M - 0.5")
    print(f"  i.e. BOLL_L + 0.5 > BOLL_M")
    # What's the actual max of (BOLL_L + 0.5) vs min of BOLL_M?
    print(f"\n  BOLL_L + 0.5 max: {(df_valid['BOLL_L'] + 0.5).max():.2f}")
    print(f"  BOLL_M min: {df_valid['BOLL_M'].min():.2f}")
    # Show rows where BOLL_L is closest to BOLL_M
    df_valid['diff'] = df_valid['BOLL_L'] - (df_valid['BOLL_M'] - 0.5)
    closest = df_valid.nsmallest(5, 'diff')[['date', 'BOLL_L', 'BOLL_M', 'diff']]
    print(f"\nRows where BOLL_L > BOLL_M - 0.5 is CLOSEST to being TRUE (top 5):")
    print(closest.to_string())