"""验证 _extract_json 修复是否有效"""
import httpx, json, re, sys
sys.path.insert(0, '.')

from explorer.engine import ExplorationSession

settings_resp = httpx.get('http://127.0.0.1:18080/api/settings', timeout=10)
settings = settings_resp.json()
api_key = settings['api_key']
api_base = settings['api_base']
model = settings['model']

# 真实返回格式测试
test_content = """<think>用户要求我作为A股股票买点公式探索引擎，输出3个候选公式给002096这只股票。

我需要考虑：
- 目标：找到能够精准识别合格买点的技术指标组合
- U1合格买点定义：在T1后第一个交易日按MA5买入，持有5个交易日内存在≥2.0%的盈利卖出机会

让我设计3个不同类型的公式...

```json
{"candidates":[{"diversity_type":"conservative","logic_desc":"双重超卖量能验证","formula_expr":"---RSI_6 < 30 and RSI_12 < 40 and VOL_RATIO > 1.5---","indicators":["RSI_6","RSI_12","VOL_RATIO"],"confidence":"高+双重超卖确认"},{"diversity_type":"aggressive","logic_desc":"均线粘合超卖","formula_expr":"---MA5 < MA20 and KDJ_J < 20---","indicators":["MA5","MA20","KDJ_J"],"confidence":"中+趋势极端超卖"},{"diversity_type":"creative","logic_desc":"MACD底背离","formula_expr":"---MACD_HIST > 0 and BOLL_L > 0---","indicators":["MACD_HIST","BOLL_L"],"confidence":"低+创新型组合"}]}
```



```json
{"candidates":[{"diversity_type":"conservative","logic_desc":"双重超卖量能验证","formula_expr":"---RSI_6 < 30 and RSI_12 < 40 and VOL_RATIO > 1.5---","indicators":["RSI_6","RSI_12","VOL_RATIO"],"confidence":"高+双重超卖确认且量能放大信号可靠性强"},{"diversity_type":"aggressive","logic_desc":"均线粘合超卖","formula_expr":"---MA5 < MA20 and KDJ_J < 20 and AMPLITUDE > 3.0---","indicators":["MA5","MA20","KDJ_J","AMPLITUDE"],"confidence":"中+趋势极端超卖组合敏感度高捕捉力强"},{"diversity_type":"creative","logic_desc":"MACD底背离布林反弹","formula_expr":"---MACD_HIST > 0 and BOLL_L > 0 and MA20_DEVIATION < -3---","indicators":["MACD_HIST","BOLL_L","MA20_DEVIATION"],"confidence":"低+创新型底背离组合历史上表现待验证"}]}
```
"""

# 创建一个假的 ExplorationSession 实例来测试 _extract_json
# 因为它是实例方法，我们需要 mock 一下
class FakeSession:
    pass

fs = FakeSession()
engine_mod = __import__('explorer.engine', fromlist=['ExplorationSession'])
# 直接测试函数
result = engine_mod.ExplorationSession._extract_json(fs, test_content)

print("=== TEST RESULT ===")
if result:
    print(f"SUCCESS! Found {len(result.get('candidates', []))} candidates:")
    for c in result.get('candidates', []):
        print(f"  {c.get('diversity_type')}: {c.get('logic_desc')} | {c.get('formula_expr')}")
else:
    print("FAILED: _extract_json returned None")