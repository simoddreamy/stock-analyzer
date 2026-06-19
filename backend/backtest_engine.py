"""
回测引擎
根据用户配置的公式和参数，运行股票历史回测
"""
import re
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from sqlalchemy import text
from db.database import SessionLocal
from indicators.calculator import (
    calc_ma, calc_ema, calc_rsi, calc_kdj, calc_macd,
    calc_boll, calc_atr, calc_vol_ratio, calc_return
)


def parse_formula_expr(expr: str) -> List[str]:
    """从公式表达式中提取所有序列号引用，如 'I001 AND I002' -> ['I001', 'I002']"""
    return re.findall(r'I\d+', expr)


def get_preset_indicators(db, seq_numbers: List[str]) -> Dict[str, dict]:
    """根据序列号列表获取预置指标配置"""
    result = {}
    for seq in seq_numbers:
        row = db.execute(text(
            "SELECT id, sequence_number, name, param_config FROM indicator_params WHERE sequence_number=:seq"
        ), {"seq": seq}).fetchone()
        if row:
            result[seq] = {
                "id": row[0],
                "sequence_number": row[1],
                "name": row[2],
                "param_config": json.loads(row[3]) if row[3] else {}
            }
    return result


def compute_indicator(close: pd.Series, high: pd.Series, low: pd.Series, volume: pd.Series,
                      indicator_name: str, params: dict) -> pd.Series:
    """
    根据指标名称和参数计算指标值序列
    indicator_name如 'RSI_6', 'KDJ_K', 'MACD_DIF' 等
    params如 {'period': 14} 或 {}
    """
    name = indicator_name.upper()

    # 从indicator_name提取基础类型和周期
    # 例如: RSI_6 -> type=RSI, period=6
    # KDJ_K -> type=KDJ_K
    # MACD_DIF -> type=MACD_DIF

    # RSI系列
    if name.startswith('RSI'):
        m = re.match(r'RSI_(\d+)', name)
        if m:
            period = int(m.group(1))
            return calc_rsi(close, period)

    # MA系列
    m = re.match(r'MA(\d+)', name)
    if m:
        period = int(m.group(1))
        return calc_ma(close, period)

    # KDJ系列
    if name == 'KDJ_K':
        k, d, j = calc_kdj(high, low, close)
        return k
    if name == 'KDJ_D':
        k, d, j = calc_kdj(high, low, close)
        return d
    if name == 'KDJ_J':
        k, d, j = calc_kdj(high, low, close)
        return j

    # MACD系列
    if name == 'MACD_DIF':
        dif, dea, hist = calc_macd(close)
        return dif
    if name == 'MACD_DEA':
        dif, dea, hist = calc_macd(close)
        return dea
    if name == 'MACD_HIST':
        dif, dea, hist = calc_macd(close)
        return hist

    # BOLL系列
    if name == 'BOLL_U':
        u, m, l = calc_boll(close)
        return u
    if name == 'BOLL_M':
        u, m, l = calc_boll(close)
        return m
    if name == 'BOLL_L':
        u, m, l = calc_boll(close)
        return l

    # ATR系列
    m = re.match(r'ATR_?(\d*)', name)
    if m:
        period_str = m.group(1)
        period = int(period_str) if period_str else 14
        return calc_atr(high, low, close, period)

    # VOL_RATIO
    if name == 'VOL_RATIO':
        m = re.match(r'VOL_RATIO', name)
        if m:
            period = params.get('period', 5)
            return calc_vol_ratio(volume, period)

    # RETURN
    if name == 'RETURN':
        return calc_return(close)

    # AMPLITUDE (当日振幅)
    if name == 'AMPLITUDE':
        return (high - low) / low * 100

    # 未知指标，返回0
    return pd.Series(0, index=close.index)


def evaluate_condition(indicator_value: float, op: str, threshold: float) -> bool:
    """评估单个条件是否满足"""
    if op == '>':
        return indicator_value > threshold
    elif op == '<':
        return indicator_value < threshold
    elif op == '>=':
        return indicator_value >= threshold
    elif op == '<=':
        return indicator_value <= threshold
    elif op == '=':
        return abs(indicator_value - threshold) < 1e-9
    return False


def evaluate_formula_day(indicator_values: Dict[str, float], seq_numbers: List[str],
                         preset_map: Dict[str, dict], formula_expr: str) -> bool:
    """
    评估某一天公式是否满足
    indicator_values: {seq_number: indicator_value}
    例如: {'I001': 35.5, 'I002': 0.8}
    返回 True 或 False
    """
    # 替换序列号为具体值，构建布尔表达式
    # 例如: "I001 AND I002" -> "True AND True"
    expr = formula_expr

    for seq in seq_numbers:
        value = indicator_values.get(seq, 0)
        preset = preset_map.get(seq, {})
        param_config = preset.get('param_config', {})

        # 提取阈值和运算符
        # param_config格式: {"period": 14, "threshold": {"op": ">", "value": 30}}
        threshold_cfg = param_config.get('threshold', {})
        if isinstance(threshold_cfg, dict):
            op = threshold_cfg.get('op', '=')
            threshold_value = threshold_cfg.get('value', 0)
        else:
            # 兼容旧格式
            op = '='
            threshold_value = threshold_cfg

        cond_result = evaluate_condition(value, op, threshold_value)
        expr = re.sub(r'\b' + seq + r'\b', 'True' if cond_result else 'False', expr)

    # 处理 AND/OR (简单处理，不考虑括号优先级)
    # 先处理 AND
    while ' AND ' in expr:
        expr = re.sub(r'True AND True', 'True', expr)
        expr = re.sub(r'True AND False', 'False', expr)
        expr = re.sub(r'False AND True', 'False', expr)
        expr = re.sub(r'False AND False', 'False', expr)

    # 再处理 OR
    while ' OR ' in expr:
        expr = re.sub(r'True OR True', 'True', expr)
        expr = re.sub(r'True OR False', 'True', expr)
        expr = re.sub(r'False OR True', 'True', expr)
        expr = re.sub(r'False OR False', 'False', expr)

    # 处理括号
    while '(' in expr:
        # 找到最内层括号并求值
        m = re.search(r'\((True|False)\)', expr)
        if m:
            expr = expr[:m.start()] + m.group(1) + expr[m.end():]
        else:
            break

    return expr.strip() == 'True'


def run_backtest(
    db,
    stock_code: str,
    formula_id: int,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000,
    position_type: str = 'percent_capital',
    position_value: float = 10,
    stop_loss_type: str = 'percent',
    stop_loss_value: float = -5,
    take_profit_type: str = 'percent',
    take_profit_value: float = 15,
    entry_price_type: str = 'open'
) -> dict:
    """
    运行回测
    返回结果字典
    """
    # 1. 获取公式配置
    formula_row = db.execute(text(
        "SELECT sequence_number, name, formula_expr, indicator_refs FROM formula_combinations WHERE id=:id"
    ), {"id": formula_id}).fetchone()

    if not formula_row:
        return {"error": f"Formula {formula_id} not found"}

    formula_seq = formula_row[0]
    formula_name = formula_row[1]
    formula_expr = formula_row[2]
    indicator_refs = json.loads(formula_row[3]) if formula_row[3] else []

    # 2. 解析公式表达式，获取序列号列表
    seq_numbers = parse_formula_expr(formula_expr)

    # 3. 获取预置指标配置
    preset_map = get_preset_indicators(db, seq_numbers)

    # 4. 获取K线数据
    rows = db.execute(text(
        """SELECT date, open, high, low, close, volume FROM daily_kline
           WHERE code=:code AND date>=:start AND date<=:end
           ORDER BY date ASC"""
    ), {"code": stock_code, "start": start_date, "end": end_date}).fetchall()

    if len(rows) < 10:
        return {"error": "Insufficient data for backtest (need at least 10 days)"}

    # 转换为DataFrame
    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)

    # 5. 预计算所有需要的指标
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # 为每个序列号计算其指标
    indicator_series = {}  # {seq_number: pd.Series}
    for seq, preset in preset_map.items():
        indicator_name = preset['name']  # 如 "RSI_6"
        param_config = preset.get('param_config', {})
        # 提取params (period等)
        params = {k: v for k, v in param_config.items() if k not in ('threshold',)}
        indicator_series[seq] = compute_indicator(close, high, low, volume, indicator_name, params)

    # 6. 逐日回测
    capital = initial_capital
    position = 0  # 持仓股数
    entry_price = 0
    entry_date = None
    equity_curve = []  # 每日资金曲线
    trade_log = []  # 交易日志
    was_true_yesterday = False  # 昨日公式是否满足

    for i in range(len(df)):
        date = df.index[i]
        row = df.iloc[i]

        # 当日开盘价、收盘价、最高价、最低价
        open_price = row['open']
        close_price = row['close']
        high_price = row['high']
        low_price = row['low']
        avg_price = (high_price + low_price) / 2  # 均价

        # 计算当日各指标值
        indicator_values = {}
        for seq, series in indicator_series.items():
            if i < len(series):
                indicator_values[seq] = series.iloc[i]
            else:
                indicator_values[seq] = 0

        # 评估公式条件
        is_true_today = evaluate_formula_day(indicator_values, seq_numbers, preset_map, formula_expr)

        # 交易信号判断：昨日不满足，今日满足 -> 买入信号
        buy_signal = not was_true_yesterday and is_true_today

        # 入场价格类型
        if entry_price_type == 'open':
            trade_price = open_price
        elif entry_price_type == 'close':
            trade_price = close_price
        elif entry_price_type == 'avg':
            trade_price = avg_price
        else:
            trade_price = open_price

        # 止损止盈价格（基于入场价格）
        if position > 0 and entry_price > 0:
            if stop_loss_type == 'percent':
                stop_price = entry_price * (1 + stop_loss_value / 100)
            else:
                stop_price = entry_price + stop_loss_value

            if take_profit_type == 'percent':
                target_price = entry_price * (1 + take_profit_value / 100)
            else:
                target_price = entry_price + take_profit_value

            # 检查是否触发止损/止盈
            # 条件：最高价>=止盈触发价 或 最低价<=止损触发价
            sell_triggered = False
            sell_reason = None
            sell_price = None

            if high_price >= target_price:
                # 止盈触发，按触发价格卖出
                sell_triggered = True
                sell_reason = 'take_profit'
                # 卖出价格：止盈触发时的价格（如果最高价刚好触发行情，收盘价作为实际执行价）
                sell_price = min(target_price, close_price) if close_price >= target_price else close_price

            if low_price <= stop_price:
                # 止损触发
                if not sell_triggered or stop_price < (target_price if sell_triggered else float('inf')):
                    sell_triggered = True
                    sell_reason = 'stop_loss'
                    sell_price = max(stop_price, close_price) if close_price <= stop_price else close_price

            if sell_triggered:
                # 卖出
                proceeds = position * sell_price
                pnl = proceeds - (position * entry_price)
                capital += proceeds

                trade_log.append({
                    "entry_date": str(entry_date.date()) if entry_date else "",
                    "exit_date": str(date.date()),
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(sell_price, 2),
                    "shares": position,
                    "pnl": round(pnl, 2),
                    "return_pct": round(pnl / (position * entry_price) * 100, 2),
                    "reason": sell_reason
                })

                position = 0
                entry_price = 0
                entry_date = None

        # 买入信号处理
        if buy_signal and position == 0:
            # 按仓位买入
            if position_type == 'percent_capital':
                # 持仓比例
                buy_amount = capital * (position_value / 100)
            else:
                # 固定股数
                buy_amount = position_value * trade_price

            if buy_amount > 0 and trade_price > 0:
                shares_to_buy = int(buy_amount / trade_price)
                if shares_to_buy > 0:
                    cost = shares_to_buy * trade_price
                    capital -= cost
                    position = shares_to_buy
                    entry_price = trade_price
                    entry_date = date

        # 更新was_true_yesterday
        was_true_yesterday = is_true_today

        # 记录当日资金（持仓市值 + 现金）
        position_value_now = position * close_price if position > 0 else 0
        equity = capital + position_value_now
        equity_curve.append({
            "date": str(date.date()),
            "equity": round(equity, 2),
            "position": position,
            "close": round(close_price, 2)
        })

    # 如果还有持仓，按最后收盘价平仓
    if position > 0:
        last_close = df.iloc[-1]['close']
        proceeds = position * last_close
        pnl = proceeds - (position * entry_price)
        capital += proceeds

        trade_log.append({
            "entry_date": str(entry_date.date()) if entry_date else "",
            "exit_date": str(df.index[-1].date()),
            "entry_price": round(entry_price, 2),
            "exit_price": round(last_close, 2),
            "shares": position,
            "pnl": round(pnl, 2),
            "return_pct": round(pnl / (position * entry_price) * 100, 2),
            "reason": "close_position"
        })
        position = 0

    # 计算统计指标
    total_trades = len(trade_log)
    win_trades = len([t for t in trade_log if t['pnl'] > 0])
    loss_trades = len([t for t in trade_log if t['pnl'] <= 0])

    total_pnl = sum(t['pnl'] for t in trade_log)
    total_return = (capital - initial_capital) / initial_capital * 100

    # 最大回撤
    peak = initial_capital
    max_drawdown = 0
    for eq in equity_curve:
        if eq['equity'] > peak:
            peak = eq['equity']
        dd = (peak - eq['equity']) / peak * 100
        if dd > max_drawdown:
            max_drawdown = dd

    # 夏普比率 (简化版：日收益 / 日波动率 * sqrt(252))
    returns = []
    prev_equity = initial_capital
    for eq in equity_curve:
        ret = (eq['equity'] - prev_equity) / prev_equity
        returns.append(ret)
        prev_equity = eq['equity']

    if len(returns) > 1:
        mean_ret = np.mean(returns) * 252
        std_ret = np.std(returns) * np.sqrt(252)
        sharpe_ratio = mean_ret / std_ret if std_ret > 0 else 0
    else:
        sharpe_ratio = 0

    # 盈亏比
    if loss_trades > 0:
        avg_win = sum(t['pnl'] for t in trade_log if t['pnl'] > 0) / win_trades if win_trades > 0 else 0
        avg_loss = abs(sum(t['pnl'] for t in trade_log if t['pnl'] <= 0) / loss_trades)
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0
    else:
        profit_factor = 0

    return {
        "stock_code": stock_code,
        "formula_id": formula_id,
        "formula_name": formula_name,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "final_capital": round(capital, 2),
        "total_return": round(total_return, 2),
        "total_trades": total_trades,
        "win_trades": win_trades,
        "loss_trades": loss_trades,
        "win_rate": round(win_trades / total_trades * 100, 2) if total_trades > 0 else 0,
        "max_drawdown": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "profit_factor": round(profit_factor, 2),
        "equity_curve": equity_curve,
        "trade_log": trade_log
    }


if __name__ == "__main__":
    # 测试回测引擎
    from db.database import SessionLocal
    db = SessionLocal()

    # 测试：获取预设指标
    seq_numbers = ['I001', 'I002']
    presets = get_preset_indicators(db, seq_numbers)
    print("Presets:", json.dumps(presets, ensure_ascii=False, indent=2))

    db.close()
