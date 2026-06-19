"""测试不同大小的请求"""
import httpx, json, sys
sys.path.insert(0, '.')

# Read key from backend settings
settings_resp = httpx.get('http://127.0.0.1:18080/api/settings', timeout=10)
settings = settings_resp.json()
api_key = settings['api_key']
api_base = settings['api_base']
model = settings['model']

print(f"Using model={model}, base={api_base}")
print(f"Key: {api_key[:15]}...")

# Test: Real exploration prompt
long_system = """你是一个A股股票买点公式探索引擎，帮助用户找到能够精准识别合格买点的技术指标组合。

【市场背景】
- A股T+1制度：当天买入不能当天卖出
- 涨跌停板：单日涨跌幅限制10%（ST股5%）
- U1合格买点定义：在T1后第一个交易日按MA5买入，持有5个交易日内存在≥2.0%的盈利卖出机会

【目标股票】002096，各段U1买点分布：segment1:8个, segment2:8个, segment3:6个

【可用指标】MA5, RSI_6, VOL_RATIO, KDJ_J, MACD_DIF, BOLL_L, ATR, AMPLITUDE

【输出格式】每轮输出3个候选公式，直接输出JSON"""

payload = {
    'model': model,
    'messages': [
        {'role': 'system', 'content': long_system},
        {'role': 'user', 'content': '输出3个候选，包含diversity_type/logic_desc/formula_expr/indicators/confidence，用---包裹公式'}
    ],
    'temperature': 0.7,
    'max_tokens': 1500
}

print("Sending real exploration prompt...")
with httpx.Client(timeout=90.0) as client:
    resp = client.post(
        f'{api_base}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload
    )
    print('status:', resp.status_code)
    if resp.status_code != 200:
        print('error:', resp.text[:400])
    else:
        content = resp.json()['choices'][0]['message']['content']
        print('content (first 600):', repr(content[:600]))

        # Test our extraction
        import re
        stripped = re.sub(r'<THINK>.*?</THINK>', '', content, flags=re.DOTALL)
        stripped = re.sub(r'<think>.*?', '', stripped, flags=re.DOTALL)
        print()
        print('Stripped (first 400):', repr(stripped[:400]))
        print()
        cand_idx = stripped.find('"candidates":')
        print('candidates at:', cand_idx)
        if cand_idx != -1:
            depth = 0
            start = -1
            for i in range(cand_idx, -1, -1):
                c = stripped[i]
                if c == '{':
                    if depth == 0:
                        start = i
                        break
                    depth -= 1
                elif c == '}':
                    depth += 1
            print('JSON start:', start)
            if start != -1:
                for end_pos in range(start + 10, len(stripped) + 1):
                    try:
                        candidate = json.loads(stripped[start:end_pos])
                        if isinstance(candidate, dict) and "candidates" in candidate:
                            print('SUCCESS! candidates count:', len(candidate.get('candidates', [])))
                            for c in candidate.get('candidates', []):
                                print(f"  {c.get('diversity_type')}: {c.get('logic_desc')} | {c.get('formula_expr')}")
                            break
                    except:
                        continue
                else:
                    print('FAILED to parse JSON')