import requests, json

# 无日期范围：返回所有有机会点的股票
r1 = requests.get('http://127.0.0.1:18080/api/stocks/with-opportunities', timeout=5)
d1 = r1.json()
print(f'全部: {len(d1)} 只')
for s in d1:
    print(f'  {s["code"]} {s["name"]} opp={s["opp_count"]} a1={s["a1"]}')

# 日期范围 2026-01-01 ~ 2026-05-29
r2 = requests.get('http://127.0.0.1:18080/api/stocks/with-opportunities?start_date=2026-01-01&end_date=2026-05-29', timeout=5)
d2 = r2.json()
print(f'\n2026-01-01~2026-05-29: {len(d2)} 只')
for s in d2:
    dates = s['opp_dates']
    print(f'  {s["code"]} opp={s["opp_count"]} dates={dates[0]}~{dates[-1]}')