"""测试 MiniMax 探索请求的真实返回格式"""
import httpx, json, re, sys
sys.path.insert(0, '.')

# Read key from backend settings
settings_resp = httpx.get('http://127.0.0.1:18080/api/settings', timeout=10)
settings = settings_resp.json()
api_key = settings['api_key']
api_base = settings['api_base']
model = settings['model']

# 真实探索 prompt（截断到合理长度）
system_prompt = """你是一个A股股票买点公式探索引擎，帮助用户找到能够精准识别合格买点的技术指标组合。

【市场背景】
- A股T+1制度：当天买入不能当天卖出
- 涨跌停板：单日涨跌幅限制10%（ST股5%）
- U1合格买点定义：在T1后第一个交易日按MA5买入，持有5个交易日内存在≥2.0%的盈利卖出机会

【目标股票】002096，各段U1买点分布：segment1:8个, segment2:8个, segment3:6个

【可用指标】
趋势类：MA5, MA10, MA20, MA60
超买超卖：RSI_6, RSI_12, RSI_24（超卖<30，超买>70）
KDJ：KDJ_K, KDJ_D, KDJ_J（J<20超卖，J>80超买）
MACD：MACD_DIF, MACD_DEA, MACD_HIST
布林： BOLL_U, BOLL_M, BOLL_L
波动率：ATR, AMPLITUDE, RETURN
量能：VOL_RATIO（>1.5放量，<0.5缩量）
偏离度：MA20_DEVIATION, MA60_DEVIATION

【输出格式 - 重要！】
每轮输出3个候选公式，每种类型各1个：conservative（保守型）、aggressive（激进型）、creative（创意型）。
每个候选必须包含以下5个字段：
  - diversity_type：类型，值为 conservative / aggressive / creative 之一
  - logic_desc：公式逻辑的中文描述（20字以内）
  - formula_expr：公式表达式，用3个减号包裹首尾，如 ---RSI_6 < 30 and VOL_RATIO > 1.5---
  - indicators：使用的指标名列表，如 ["RSI_6", "VOL_RATIO"]
  - confidence：置信度，格式为"高/中/低+原因"

示例输出：
{"candidates":[{"diversity_type":"conservative","logic_desc":"RSI超卖且放量","formula_expr":"---RSI_6 < 30 and VOL_RATIO > 1.5---","indicators":["RSI_6","VOL_RATIO"],"confidence":"高+RSI处于超卖区间且量能放大"},{"diversity_type":"aggressive","logic_desc":"均线多头排列","formula_expr":"---MA5 > MA20 and VOL_RATIO > 2.0---","indicators":["MA5","MA20","VOL_RATIO"],"confidence":"中+趋势明确但信号较激进"},{"diversity_type":"creative","logic_desc":"布林下轨反弹","formula_expr":"---BOLL_L > 0 and AMPLITUDE > 3.0---","indicators":["BOLL_L","AMPLITUDE"],"confidence":"低+创意型组合，历史上表现待验证"}]}

格式要求：
1. 直接输出JSON，不要有任何其他文字、前缀或后缀
2. formula_expr 必须用 --- 包裹首尾
3. 每轮必须正好输出3个候选"""

user_prompt = """请输出3个候选公式，每种类型各1个。每候选包含diversity_type/logic_desc/formula_expr/indicators/confidence，公式用---包裹。直接输出JSON，不要解释。"""

payload = {
    'model': model,
    'messages': [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
    ],
    'temperature': 0.7,
    'max_tokens': 2000
}

print("Sending to MiniMax...")
with httpx.Client(timeout=90.0) as client:
    resp = client.post(
        f'{api_base}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload
    )
    print('status:', resp.status_code)
    result = resp.json()
    content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

    print()
    print('=== FULL RAW CONTENT ===')
    print(repr(content))
    print()
    print('=== CONTENT (formatted) ===')
    print(content)