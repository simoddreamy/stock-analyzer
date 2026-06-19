"""
AI探索引擎
核心逻辑：AI提出指标组合 → 系统验证 → AI迭代优化
"""
import ast, json, re, time, uuid, logging
from datetime import datetime
from typing import Optional, Callable
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class CandidateFormula:
    logic_desc: str
    formula_expr: str
    indicators: list
    precision: float = 0.0
    coverage_count: int = 0
    u2_count: int = 0
    stage: str = ""


@dataclass
class ExplorationProgress:
    session_id: str
    code: str
    status: str
    elapsed_seconds: int
    total_seconds: int
    current_stage: str
    candidates_explored: int
    best_candidate: Optional[CandidateFormula]
    current_candidates: list
    message: str


# ============================================================================
# U1计算器
# ============================================================================

def compute_u1(db: Session, code: str, u1_config: dict) -> set:
    from indicators.calculator import calc_ma
    hold_days = u1_config.get('hold_days', 5)
    profit_pct = u1_config.get('profit_pct', 2.0) / 100.0
    buy_price_type = u1_config.get('buy_price', 'MA5')

    rows = db.execute(
        text("SELECT date, open, high, low, close, volume FROM daily_kline WHERE code = :code ORDER BY date"),
        {"code": code}
    ).fetchall()

    if len(rows) < hold_days + 10:
        return set()

    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = df['date'].astype(str)
    df['MA5'] = calc_ma(df['close'], 5)

    qualified = set()
    for i in range(len(df) - hold_days - 1):
        bp = df.iloc[i + 1]['MA5'] if buy_price_type == 'MA5' else df.iloc[i + 1]['close']
        if pd.isna(bp) or bp <= 0:
            continue
        found = any(df.iloc[j]['high'] >= bp * (1 + profit_pct)
                    for j in range(i + 2, min(i + hold_days + 2, len(df))))
        if found:
            qualified.add(df.iloc[i]['date'])
    return qualified


# ============================================================================
# 候选评估
# ============================================================================

def evaluate_candidate(db, code, u1_config, candidate, segment, segments_data):
    from indicators.calculator import precompute_indicators_for_stock
    seg = segments_data.get(segment, {})
    u1_dates = seg.get('u1_dates', set())
    kline_df = seg.get('kline_df')
    if kline_df is None or kline_df.empty or len(u1_dates) == 0:
        return 0.0, 0, 0
    ind_df = precompute_indicators_for_stock(code, kline_df)
    u2_dates = simulate_u2(ind_df, candidate)
    inter = u1_dates & u2_dates
    u2c = len(u2_dates)
    prec = len(inter) / u2c if u2c > 0 else 0.0
    return prec, len(inter), u2c


def simulate_u2(ind_df, candidate):
    import pandas as pd
    u2 = set()
    if not candidate.formula_expr:
        return u2
    try:
        res = _safe_eval(candidate.formula_expr, ind_df)
        for idx in ind_df.index[res == True]:
            u2.add(str(ind_df.at[idx, 'date']))
    except Exception:
        pass
    return u2


def simulate_u2_evaluation(ind_df, candidate, u1_config=None):
    """simulate_u2 的别名，兼容 main.py 的调用方式"""
    return simulate_u2(ind_df, candidate)


def _safe_eval(expr, df):
    expr = re.sub(r'\s+', ' ', expr.strip())
    if re.search(r'\band\b', expr, re.I) or re.search(r'\bor\b', expr, re.I):
        parts = re.split(r'\b(and|or)\b', expr, flags=re.I)
        parts = [p.strip() for p in parts if p.strip()]
        combined = _eval_one(parts[0], df)
        for i in range(1, len(parts), 2):
            op = parts[i].lower()
            sub = _eval_one(parts[i + 1], df)
            combined = (combined & sub) if op == 'and' else (combined | sub)
        return combined
    return _eval_one(expr, df)


def _eval_one(expr, df):
    has_cmp = any(op in expr for op in ('>', '<', '>=', '<=', '==', '!='))
    if not has_cmp:
        return _arith(expr, df).astype(bool)
    for op in ('>=', '<=', '==', '!=', '>', '<'):
        if op in expr:
            l, r = expr.split(op, 1)
            l, r = l.strip(), r.strip()
            break
    ls = _arith(l, df)
    try:
        rv = ast.literal_eval(r)
    except Exception:
        rv = _arith(r, df)
    ops = {'>': lambda a, b: a > b, '<': lambda a, b: a < b,
           '>=': lambda a, b: a >= b, '<=': lambda a, b: a <= b,
           '==': lambda a, b: a == b, '!=': lambda a, b: a != b}
    return ops[op](ls, rv)


def _arith(expr, df):
    ids = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', expr))
    ns = {}
    for col in [c for c in ids if c in df.columns]:
        s = df[col].copy().replace([np.inf, -np.inf], np.nan)
        ns[col] = s.values
    ns['np'] = np
    # PREV(col, n) → 前n天col的值（shift n天）
    ns['PREV'] = lambda col, n: df[col].shift(n).values
    # RATE(col, n) → 前n天变化率
    ns['RATE'] = lambda col, n: df[col].pct_change(n).values
    # DIFF(col, n) → 前n天差值（col - col.shift(n)）
    ns['DIFF'] = lambda col, n: (df[col] - df[col].shift(n)).values
    try:
        r = eval(expr, {"__builtins__": {}}, ns)
        return pd.Series(r, index=df.index) if isinstance(r, np.ndarray) else r
    except Exception as e:
        raise ValueError(f"eval failed: {e}") from e


# ============================================================================
# AI探索会话
# ============================================================================

class ExplorationSession:
    def __init__(self, db, code, u1_config, api_key, api_base, model,
                 time_limit=600, progress_callback: Optional[Callable] = None):
        self.db = db
        self.code = code
        self.u1_config = u1_config
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.time_limit = time_limit
        self.progress_callback = progress_callback
        self.session_id = str(uuid.uuid4())[:8]
        self.status = "running"
        self.start_time = time.time()
        self.candidates_explored = 0
        self.best_candidate: Optional[CandidateFormula] = None
        self.candidate_history: list = []
        self._prev_feedback: str = ""
        self.recent_candidates: list = []
        self.iteration_count: int = 0
        self.segment_u1: dict = {}
        self.segments_data: dict = {}
        self._consecutive_failures: int = 0
        db.execute(text(
            "INSERT INTO exploration_sessions (id,code,batch_id,u1_config_id,start_time,status,result) "
            "VALUES (NULL,:code,NULL,1,:st,'running',NULL)"),
            {"code": code, "st": datetime.now().isoformat()})
        db.commit()

    def _elapsed(self):
        return int(time.time() - self.start_time)

    def _remaining(self):
        return max(0, self.time_limit - self._elapsed())

    def _build_system_prompt(self) -> str:
        seg_info = "".join(f"  - {s}: {n}个U1买点" for s, n in self.segment_u1.items())
        ind_list = """可用指标（用于 formula_expr，指标名严格区分大小写）：

【原始行情】
close, high, low, open, volume（直接可用）

【均线类 MA（趋势）】
MA5, MA10, MA20, MA30, MA60, MA90, MA120, MA250
EMA12, EMA26

【均线关系（0/1 布尔）】
MA5_GT_MA10, MA5_GT_MA20, MA10_GT_MA20, MA5_GT_MA60, MA20_GT_MA60
CLOSE_GT_MA5, CLOSE_GT_MA10, CLOSE_GT_MA20, CLOSE_GT_MA60

【均线标准差（波动率）】
MA5_STD, MA10_STD, MA20_STD（20日波动率参考）

【RSI 超买超卖】
RSI_3, RSI_6, RSI_9, RSI_12, RSI_24（<30超卖，>70超买）

【KDJ】
KDJ_K, KDJ_D, KDJ_J（J<20超卖，J>80超买）

【MACD 多周期】
MACD_DIF, MACD_DEA, MACD_HIST（标准12/26/9）
MACD_DIF5, MACD_DEA5, MACD_HIST5（5/13/6 短周期）
MACD_DIF20, MACD_DEA20, MACD_HIST20（20/60/30 长周期）

【布林带】
BOLL_U, BOLL_M, BOLL_L

【ATR 波动率多周期】
ATR（14日）, ATR_7（7日）, ATR_21（21日）

【成交量/量能】
VOL_RATIO（量比，>1.5放量，<0.5缩量）
VOL_MA5, VOL_MA10
VOLUME_RATE_1, VOLUME_RATE_3（量变化率）

【涨跌幅/动量】
RETURN（当日收益率）, CLOSE_RATE_1, CLOSE_RATE_3, CLOSE_RATE_5

【偏离度】
MA20_DEVIATION, MA60_DEVIATION
AMPLITUDE（振幅）

【前 n 天移窗（函数式，公式中直接调用）】
PREV(close, 1)  前1日收盘价
PREV(volume, 3) 前3日成交量
PREV(RSI_6, 2)  前2日RSI_6值
RATE(close, 1)  1日变化率（等价于 CLOSE_RATE_1）
DIFF(close, 1)  1日收盘价差值（close - PREV(close,1)）

【前 n 天移窗（预计算列）】
PREV_CLOSE_1/2/3/5/10     前 n 日收盘价
PREV_OPEN_1/2/3/5/10       前 n 日开盘价
PREV_HIGH_1/2/3/5/10       前 n 日最高价
PREV_LOW_1/2/3/5/10        前 n 日最低价
PREV_VOLUME_1/2/3/5/10     前 n 日成交量

公式表达式支持：
  - 逻辑型：RSI_6 < 30 and VOL_RATIO > 1.5
  - 加权型：0.4*RSI_6 + 0.3*VOL_RATIO > 0.6
  - 移窗型：PREV(RSI_6, 2) < 30 and RSI_6 > RSI_6 - PREV(RSI_6, 1)
  - 混用型：(RSI_6 < 30 or KDJ_J < 20) and VOL_RATIO > 1.8
  - 比较符：> < >= <= == !=
  - 逻辑符：and or not

重要：公式中的指标名必须与上述列表完全一致，例如 RSI_6 不能写成 RSI、KDJ_J 不能写成 KDJ。"""

        return f"""你是一个A股股票买点公式探索引擎，帮助用户找到能够精准识别合格买点的技术指标组合。

【市场背景】
- A股T+1制度：当天买入不能当天卖出
- 涨跌停板：单日涨跌幅限制10%（ST股5%）
- U1合格买点定义：在T1后第一个交易日按MA5买入，持有{self.u1_config.get('hold_days', 5)}个交易日内存在≥{self.u1_config.get('profit_pct', 2.0)}%的盈利卖出机会

【目标股票】{self.code}，各段U1买点分布：
{seg_info}

【可用指标】
{ind_list}

【输出格式 - 重要！】

每轮输出3个候选公式，每种类型各1个：conservative（保守型）、aggressive（激进型）、creative（创意型）。

每个候选必须包含以下5个字段：
  - diversity_type：类型，值为 conservative / aggressive / creative 之一
  - logic_desc：公式逻辑的中文描述（20字以内）
  - formula_expr：公式表达式，用3个减号包裹首尾，如 ---RSI_6 < 30 and VOL_RATIO > 1.5---
  - indicators：使用的指标名列表，如 ["RSI_6", "VOL_RATIO"]
  - confidence：置信度，格式为"高/中/低+原因"

示例输出：
{{"candidates":[{{"diversity_type":"conservative","logic_desc":"RSI超卖且放量","formula_expr":"---RSI_6 < 30 and VOL_RATIO > 1.5---","indicators":["RSI_6","VOL_RATIO"],"confidence":"高+RSI处于超卖区间且量能放大"}},{{"diversity_type":"aggressive","logic_desc":"均线多头排列","formula_expr":"---MA5 > MA20 and VOL_RATIO > 2.0---","indicators":["MA5","MA20","VOL_RATIO"],"confidence":"中+趋势明确但信号较激进"}},{{"diversity_type":"creative","logic_desc":"布林下轨反弹","formula_expr":"---BOLL_L > 0 and AMPLITUDE > 3.0---","indicators":["BOLL_L","AMPLITUDE"],"confidence":"低+创意型组合，历史上表现待验证"}}]}}

格式要求：
1. 直接输出JSON，不要有任何其他文字、前缀或后缀
2. formula_expr 必须用 --- 包裹首尾，如 ---RSI_6 < 30---
3. 只使用【可用指标】中列出的指标名，不要自创名称
4. 每轮必须正好输出3个候选

【约束】
- 只使用当日及当日之前的数据
- 每轮必须正好3个候选，类型不能重复"""


    def _call_llm(self, prompt: str) -> Optional[dict]:
        import httpx
        try:
            with httpx.Client(timeout=90.0) as client:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self._build_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
                # 注意：MiniMax API 不接受 "thinking": false，thinking 参数类型为对象而非布尔值
                resp = client.post(
                    f"{self.api_base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload
                )
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except Exception as e:
                        logger.error(f"LLM返回非JSON: body=[{resp.text[:300]}] err={e}")
                        return None
                else:
                    logger.warning(f"LLM API error: {resp.status_code} {resp.text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return None


    def _fetch_kline_data(self):
        from indicators.calculator import precompute_indicators_for_stock
        rows = self.db.execute(
            text("SELECT date,open,high,low,close,volume FROM daily_kline WHERE code=:code ORDER BY date"),
            {"code": self.code}
        ).fetchall()
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        df['date'] = df['date'].astype(str)
        return df

    def _split_segments(self, df):
        n = len(df)
        if n < 300:
            s1, s2 = int(n * 0.4), int(n * 0.7)
        else:
            s1, s2 = int(n * 0.35), int(n * 0.65)
        segs = {}
        for name, (st, ed) in {'segment1': (0, s1), 'segment2': (s1, s2), 'segment3': (s2, n - 5)}.items():
            seg_df = df.iloc[st:ed].copy() if ed > st else df.iloc[:5].copy()
            all_u1 = compute_u1(self.db, self.code, self.u1_config)
            seg_u1 = {d for d in all_u1
                      if any(df['date'] == d) and st <= df[df['date'] == d].index[0] < ed}
            segs[name] = {'u1_dates': seg_u1, 'kline_df': seg_df}
        return segs

    def _report_progress(self, message=""):
        if self.progress_callback:
            self.progress_callback(ExplorationProgress(
                session_id=self.session_id, code=self.code, status=self.status,
                elapsed_seconds=self._elapsed(), total_seconds=self.time_limit,
                current_stage="第一段", candidates_explored=self.candidates_explored,
                best_candidate=self.best_candidate,
                current_candidates=self.recent_candidates, message=message))

    def _build_feedback(self) -> str:
        if not self.candidate_history:
            return "（首轮探索，暂无历史表现）"
        lines = ["【历史候选表现】"]
        for h in self.candidate_history[-8:]:
            s1 = h.get("segment1", {})
            p = s1.get('precision', 0)
            lines.append(f"{'✅' if p >= 0.80 else '❌'} {h['formula']}（{h['logic']}，精度={p:.2f}）")
        if self.best_candidate:
            lines.append(f"【最优】{self.best_candidate.formula_expr} 精度={self.best_candidate.precision:.2f}")
        return "\n".join(lines)

    def _extract_json(self, text: str):
        """从LLM输出中提取包含candidates字段的完整JSON对象。
        MiniMax会输出 <THINK>...</THINK> 或 <think>...</think> 标签包裹思考内容，
        JSON可能在标签内部或标签之后。
        策略：先剥除所有标签包裹的思考内容，再在剩余文本中查找JSON。
        """
        # 第一步：剥除 <THINK>...</THINK> 和 <think>...</think> 包裹的思考内容
        stripped = re.sub(r'<THINK>.*?</THINK>', '', text, flags=re.DOTALL)
        stripped = re.sub(r'<think>.*?</think>', '', stripped, flags=re.DOTALL)
        # 第二步：剥除 markdown 代码块标记（```json ``` 等）
        code_block_pattern = r'```[a-z]*\s*\n?'
        stripped = re.sub(code_block_pattern, '', stripped)
        # 剥除尾随的 ```
        stripped = re.sub(r'```', '', stripped)
        # 如果剥除后空了就用原始文本（容错）
        search_in = stripped.strip() if stripped.strip() else text

        # 找 "candidates": 字段（JSON中必有此字段）
        patterns = ['"candidates":', "'candidates':", "candidates:"]
        cand_idx = -1
        for p in patterns:
            idx = search_in.find(p)
            if idx != -1:
                cand_idx = idx
                break
        if cand_idx == -1:
            return None

        # 从 candidates 位置往前找最近的 {
        depth = 0
        start = -1
        for i in range(cand_idx, -1, -1):
            c = search_in[i]
            if c == '{':
                if depth == 0:
                    start = i
                    break
                depth -= 1
            elif c == '}':
                depth += 1

        if start == -1:
            return None

        # 尝试从 start 位置向后扩展找到完整JSON
        for end_pos in range(start + 10, len(search_in) + 1):
            try:
                candidate = json.loads(search_in[start:end_pos])
                if isinstance(candidate, dict) and "candidates" in candidate:
                    return candidate
            except Exception:
                continue

        return None


    def run(self) -> Optional[CandidateFormula]:
        logger.info(f"开始探索: {self.code}, 限时: {self.time_limit}s")
        df = self._fetch_kline_data()
        if df is None or len(df) < 50:
            self.status = "failed"
            return None

        segments = self._split_segments(df)
        self.segments_data = segments
        for seg_name, seg_data in segments.items():
            self.segment_u1[seg_name] = len(seg_data['u1_dates'])

        while self._remaining() > 0 and self.status == "running":
            self.iteration_count += 1

            candidates = self._propose_candidates(self.iteration_count, self._prev_feedback)

            if not candidates:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3:
                    self.status = "failed"
                    self._report_progress("连续3轮AI返回格式异常，探索终止")
                    return self.best_candidate
                self._report_progress(f"AI格式异常，跳过第{self.iteration_count}轮...")
                continue
            self._consecutive_failures = 0

            self.recent_candidates = [{"formula": c.formula_expr, "logic": c.logic_desc} for c in candidates]

            for cand in candidates:
                if self._remaining() <= 0:
                    break
                self.candidates_explored += 1

                prec, cov, u2c = evaluate_candidate(
                    self.db, self.code, self.u1_config, cand, 'segment1', segments)
                cand.precision = prec
                cand.coverage_count = cov
                cand.u2_count = u2c
                cand.stage = "segment1"

                self.candidate_history.append({
                    "formula": cand.formula_expr,
                    "logic": cand.logic_desc,
                    "segment1": {"precision": prec, "coverage": cov, "u2_count": u2c}
                })

                for rc in self.recent_candidates:
                    if rc["formula"] == cand.formula_expr:
                        rc["precision"] = round(prec, 3)
                        rc["coverage"] = cov
                        break

                self._report_progress(f"评估候选 {self.candidates_explored}...")
                if prec >= 0.80 and cov > 20:
                    logger.info(f"候选通过第一段: {cand.formula_expr} a1={prec}")
                    self.best_candidate = cand
                    p2, c2, u2 = evaluate_candidate(
                        self.db, self.code, self.u1_config, cand, 'segment2', segments)
                    cand.stage = "segment2"
                    if p2 >= 0.80:
                        p3, c3, u3 = evaluate_candidate(
                            self.db, self.code, self.u1_config, cand, 'segment3', segments)
                        cand.stage = "segment3"
                        if p3 >= 0.75:
                            self._save_best_formula(cand)
                            self.status = "completed"
                            return cand

            self._prev_feedback = self._build_feedback()
            time.sleep(1)

        self.status = "timeout"
        self._report_progress("探索超时")
        return self.best_candidate

    def _propose_candidates(self, iteration: int, prev_feedback: str = "") -> list:
        seg_stats = "\n".join(
            f"  {s}: 共{len(d['u1_dates'])}个U1买点（{d['kline_df']['date'].iloc[0]}~{d['kline_df']['date'].iloc[-1]}）"
            for s, d in self.segments_data.items())

        prompt = f"""【探索任务 - 第{iteration}轮】

目标股票：{self.code}
各数据段规模：
{seg_stats}

{prev_feedback if prev_feedback else "（首轮探索，暂无历史表现）"}

请输出3个候选公式，每种类型各1个：
- conservative（保守型）：偏好RSI超卖/布林下轨/价格低位信号
- aggressive（激进型）：偏好均线多头/量能放大/KDJ金叉
- creative（创意型）：非常规组合

每个候选必须包含：
- diversity_type：类型名
- logic_desc：中文描述，20字以内
- formula_expr：公式，用---包裹首尾，如 ---RSI_6 < 30 and VOL_RATIO > 1.5---
- indicators：指标名列表
- confidence：置信度

直接输出JSON，不要有任何其他文字
        """

        result = self._call_llm(prompt)
        if not result:
            logger.warning(f"第{iteration}轮 LLM调用失败")
            return []

        try:
            choices = result.get("choices", [])
            if not choices:
                logger.warning(f"第{iteration}轮 空choices")
                return []
            content = choices[0].get("message", {}).get("content", "").strip()
            if not content:
                logger.warning(f"第{iteration}轮 空content")
                return []

            data = self._extract_json(content)
            if not data:
                logger.warning(f"第{iteration}轮 JSON提取失败，内容前200: [{content[:200]}]")
                return []

            # 从 formula_expr 中移除 --- 包裹
            def clean_formula(expr):
                if isinstance(expr, str):
                    expr = expr.strip()
                    if expr.startswith("---"):
                        expr = expr[3:]
                    if expr.endswith("---"):
                        expr = expr[:-3]
                    return expr.strip()
                return str(expr)

            cand_list = []
            for c in data.get("candidates", []):
                fe = c.get("formula_expr", "")
                if c.get("diversity_type") and fe:
                    cand_list.append(CandidateFormula(
                        logic_desc=c.get("logic_desc", ""),
                        formula_expr=clean_formula(fe),
                        indicators=c.get("indicators", []),
                        precision=0.0, coverage_count=0, u2_count=0, stage=""))

            if cand_list:
                return cand_list
            logger.warning(f"第{iteration}轮 candidates为空")
            return []
        except Exception as e:
            logger.warning(f"第{iteration}轮 解析异常: {e}")
            return []

    def _save_best_formula(self, cand):
        self.db.execute(text(
            "INSERT INTO best_formulas (code,u1_config_id,logic_desc,formula_expr,a1,a2,a3,explored_at) "
            "VALUES (:code,1,:ld,:fe,:a1,:a2,:a3,:ea)"),
            {"code": self.code, "ld": cand.logic_desc, "fe": cand.formula_expr,
             "a1": cand.precision if cand.stage == "segment1" else None,
             "a2": cand.precision if cand.stage == "segment2" else None,
             "a3": cand.precision if cand.stage == "segment3" else None,
             "ea": datetime.now().isoformat()})
        self.db.commit()


class BatchExploration:
    def __init__(self, db, codes, u1_config, api_key, api_base, model,
                 time_per_stock=600, progress_callback: Optional[Callable] = None):
        self.db = db
        self.codes = codes
        self.u1_config = u1_config
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.time_per_stock = time_per_stock
        self.progress_callback = progress_callback
        self.batch_id = str(uuid.uuid4())[:8]
        self.results = {}
        self.status = "running"

    def run(self):
        for code in self.codes:
            if self.status == "stopped":
                break
            logger.info(f"批量探索 [{self.batch_id}]: {code}")
            session = ExplorationSession(
                db=self.db, code=code, u1_config=self.u1_config,
                api_key=self.api_key, api_base=self.api_base, model=self.model,
                time_limit=self.time_per_stock, progress_callback=self.progress_callback)
            self.results[code] = session.run()
        self.status = "completed"
        return self.results