"""独立调试脚本：直接测试MiniMax API调用完整流程"""
import httpx
import json
import logging
import sys
import os

# 直接从数据库读取配置
sys.path.insert(0, os.path.dirname(__file__))
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

db_path = r'C:\Users\Administrator\.openclaw\workspace\stock_analyzer\backend\data\stock_analyzer.db'
engine = create_engine(f'sqlite:///{db_path}')
with engine.connect() as conn:
    rows = dict(conn.execute(text('SELECT key, value FROM settings')).fetchall())

api_key = rows.get('api_key', '')
api_base = rows.get('api_base', 'https://api.minimaxi.com/v1')
model = rows.get('model', 'MiniMax-M2.7')

print(f"=== 配置 ===")
print(f"api_base: {api_base}")
print(f"model: {model}")
print(f"api_key: {api_key[:6]}...")
print()

# ===== 完整复刻 backend/explorer/engine.py 的调用逻辑 =====
system_prompt = """你是一个A股股票买点公式探索引擎，帮助用户找到能够精准识别合格买点的技术指标组合。

【市场背景】
- A股T+1制度：当天买入不能当天卖出
- 涨跌停板：单日涨跌幅限制10%（ST股5%）
- U1合格买点定义：在T1后第一个交易日按MA5买入，持有5个交易日内存在≥2.0%的盈利卖出机会

【目标股票】000001，各段U1买点分布：
  - segment1: 20个U1买点
  - segment2: 25个U1买点
  - segment3: 18个U1买点

【可用指标】
可用指标（直接用于formula_expr）：
  - MA5/MA10/MA20/MA60/MA120/MA250：简单移动平均
  - EMA12/EMA26：指数移动平均
  - RSI_6/RSI_12/RSI_24：相对强弱指数（超卖<30，超买>70）
  - KDJ_K/KDJ_D/KDJ_J：随机指标（J<20超卖，J>80超买）
  - MACD_DIF/MACD_DEA/MACD_HIST：MACD指标
  - BOLL_U/BOLL_M/BOLL_L：布林带上下中轨
  - ATR：平均真实波幅
  - VOL_RATIO：量比（>1.5放量，<0.5缩量）
  - MA20_DEVIATION：价格对20日均线偏离度（负偏离表示低于均线）
  - MA60_DEVIATION：价格对60日均线偏离度
  - AMPLITUDE：当日振幅
  - RETURN：当日收益率

【探索策略】
每轮必须提出3个候选公式，类型各不同：
1. 保守型：偏好布林下轨/RSI超卖/价格偏离等"低位信号"，适用于捕捉超跌反弹
2. 激进型：偏好量能放大/均线多头/KDJ金叉等"趋势确认"信号，适用于顺势而为
3. 创意型：非常规组合，如RSI背离、MACD交叉、ATR突破、振幅收缩后放量等

【公式表达式规则】
- 加权型："0.4*RSI_6 + 0.3*VOL_RATIO + 0.3*BOLL_DEVIATION > 0.6"
- 逻辑型："RSI_6 < 30 and VOL_RATIO > 1.5"
- 混用型："(RSI_6 < 30 or KDJ_J < 20) and VOL_RATIO > 1.8"
- 支持 and/or/not 逻辑运算符
- 支持比较符：> < >= <= ==

【输出格式】
{
  "candidates": [
    {
      "diversity_type": "conservative|aggressive|creative",
      "logic_desc": "描述逻辑",
      "formula_expr": "表达式",
      "indicators": ["指标名"],
      "confidence": "高/中/低及原因"
    }
  ],
  "reasoning": "本轮候选的整体思路和多样性说明"
}

【约束】
- 只使用当日及之前数据
- 每轮最多3个候选，至少包含上述3种类型各1个"""

user_prompt = """【探索任务 - 第1轮】

目标股票：000001
各数据段规模：
  segment1: 共20个U1买点（数据区间2010-01-04~2015-06-30）
  segment2: 共25个U1买点（数据区间2015-07-01~2019-12-31）
  segment3: 共18个U1买点（数据区间2020-01-02~2024-12-31）

（首轮探索，暂无历史表现）

请提出3个候选公式（必须包含保守型、激进型、创意型各1个），严格按以下JSON格式输出：
{
  "candidates": [
    {
      "diversity_type": "conservative",
      "logic_desc": "...",
      "formula_expr": "...",
      "indicators": ["..."],
      "confidence": "高/中/低 + 原因"
    },
    {
      "diversity_type": "aggressive",
      "logic_desc": "...",
      "formula_expr": "...",
      "indicators": ["..."],
      "confidence": "高/中/低 + 原因"
    },
    {
      "diversity_type": "creative",
      "logic_desc": "...",
      "formula_expr": "...",
      "indicators": ["..."],
      "confidence": "高/中/低 + 原因"
    }
  ],
  "reasoning": "整体思路和多样性说明",
  "failed_patterns_to_avoid": ["避免的模式1", "避免的模式2"]
}"""

print(f"=== System prompt长度: {len(system_prompt)} 字符 ===")
print(f"=== User prompt长度: {len(user_prompt)} 字符 ===")
print()

print("=== 发送请求到 MiniMax API ===")
try:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 1.2,
                "max_tokens": 2000
            }
        )
    print(f"Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type')}")
    print(f"Content-Length: {resp.headers.get('content-length')}")
    body = resp.text
    print(f"Body长度: {len(body)}")
    print(f"Body前500字符: {body[:500]}")
    print()
    if body:
        data = json.loads(body)
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            print(f"AI回复长度: {len(content)} 字符")
            print(f"AI回复前300字符: {content[:300]}")
        else:
            print("choices为空:", data)
    else:
        print("❌ BODY为空！")
        print(f"Headers: {dict(resp.headers)}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()