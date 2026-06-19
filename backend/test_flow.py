# Test: what does the API actually return for K-line and formulas for each stock?
import requests, json

base = 'http://127.0.0.1:18080'

# List all stocks
r = requests.get(f'{base}/api/stocks/list')
stocks = r.json()
print('stocks:', [s['code'] for s in stocks])

for s in stocks:
    code = s['code']
    
    # K-line data
    r2 = requests.get(f'{base}/api/kline/{code}')
    kline = r2.json()
    kline_count = len(kline)
    kline_first = kline[0]['date'] if kline else 'N/A'
    kline_last = kline[-1]['date'] if kline else 'N/A'
    
    # Opportunity points
    r3 = requests.get(f'{base}/api/formulas/{code}/opportunity')
    opp_data = r3.json()
    
    # Formula info
    r4 = requests.get(f'{base}/api/formulas/{code}')
    fm_data = r4.json()
    fm = fm_data[0] if fm_data else {}
    
    print(f'\ncode={code} name={s.get("name","")}')
    print(f'  kline: {kline_count} records [{kline_first} to {kline_last}]')
    print(f'  opp: {opp_data["count"]} points, first={opp_data["opp_dates"][:2] if opp_data["opp_dates"] else "none"}')
    print(f'  formula a1={fm.get("a1","N/A")} a2={fm.get("a2","N/A")} a3={fm.get("a3","N/A")}')