"""
技术指标计算层
支持基础指标预计算 + AI动态自定义指标
"""
import pandas as pd
import numpy as np
from typing import Optional
from sqlalchemy import text
from db.database import SessionLocal, engine


# ============================================================================
# 基础技术指标计算
# ============================================================================

def calc_ma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period).mean()


def calc_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series,
             n: int = 9, m1: int = 3, m2: int = 3) -> tuple:
    """
    计算KDJ指标
    返回 (K, D, J) 三个Series
    """
    lowest_low = low.rolling(window=n).min()
    highest_high = high.rolling(window=n).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    rsv = rsv.fillna(50)

    K = pd.Series(index=close.index, dtype=float)
    D = pd.Series(index=close.index, dtype=float)
    K.iloc[0] = 50
    D.iloc[0] = 50
    for i in range(1, len(close)):
        K.iloc[i] = (2/3) * K.iloc[i-1] + (1/3) * rsv.iloc[i]
        D.iloc[i] = (2/3) * D.iloc[i-1] + (1/3) * K.iloc[i]
    J = 3 * K - 2 * D
    return K, D, J


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """
    计算MACD指标
    返回 (DIF, DEA, MACD柱)
    """
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    DIF = ema_fast - ema_slow
    DEA = calc_ema(DIF, signal)
    MACD = (DIF - DEA) * 2
    return DIF, DEA, MACD


def calc_boll(close: pd.Series, period: int = 20, std_dev: float = 2) -> tuple:
    """
    计算布林带
    返回 (BOLL_U, BOLL_M, BOLL_L)
    """
    BOLL_M = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    BOLL_U = BOLL_M + std_dev * std
    BOLL_L = BOLL_M - std_dev * std
    return BOLL_U, BOLL_M, BOLL_L


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """计算ATR（Average True Range）"""
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    TR = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    ATR = TR.rolling(window=period).mean()
    return ATR


def calc_vol_ratio(volume: pd.Series, ma_period: int = 5) -> pd.Series:
    """计算量比"""
    vol_ma = calc_ma(volume, ma_period)
    return volume / vol_ma


def calc_return(close: pd.Series, period: int = 1) -> pd.Series:
    """计算收益率"""
    return close.pct_change(period)


def calc_ma_deviation(close: pd.Series, ma_period: int = 20) -> pd.Series:
    """计算收盘价对均线的偏离度"""
    ma = calc_ma(close, ma_period)
    return (close - ma) / ma


# ============================================================================
# 批量预计算所有基础指标
# ============================================================================

def precompute_indicators_for_stock(code: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    对一只股票的K线数据，预计算所有基础指标
    df要求包含: date, open, high, low, close, volume
    """
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    result = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()

    # 均线
    for p in [5, 10, 20, 60, 120, 250]:
        result[f'MA{p}'] = calc_ma(close, p)

    # EMA
    for p in [12, 26]:
        result[f'EMA{p}'] = calc_ema(close, p)

    # RSI
    for p in [6, 12, 24]:
        result[f'RSI_{p}'] = calc_rsi(close, p)

    # KDJ
    K, D, J = calc_kdj(high, low, close)
    result['KDJ_K'] = K
    result['KDJ_D'] = D
    result['KDJ_J'] = J

    # MACD
    DIF, DEA, MACD = calc_macd(close)
    result['MACD_DIF'] = DIF
    result['MACD_DEA'] = DEA
    result['MACD_HIST'] = MACD

    # 布林带
    BOLL_U, BOLL_M, BOLL_L = calc_boll(close)
    result['BOLL_U'] = BOLL_U
    result['BOLL_M'] = BOLL_M
    result['BOLL_L'] = BOLL_L

    # ATR
    result['ATR'] = calc_atr(high, low, close)

    # 量比
    result['VOL_RATIO'] = calc_vol_ratio(volume)
    result['VOL_MA5'] = calc_ma(volume, 5)
    result['VOL_MA10'] = calc_ma(volume, 10)

    # 涨跌幅
    result['RETURN'] = calc_return(close)

    # 均线偏离度
    result['MA20_DEVIATION'] = calc_ma_deviation(close, 20)
    result['MA60_DEVIATION'] = calc_ma_deviation(close, 60)

    # 振幅
    result['AMPLITUDE'] = (high - low) / low

    # ---- 移窗价格/成交量（PREV_n 表示前n天的值，AI探索时可用 PREV(close,1) 语法） ----
    for col, ser in [('CLOSE', close), ('OPEN', df['open']),
                     ('HIGH', high), ('LOW', low), ('VOLUME', volume)]:
        for n in [1, 2, 3, 5, 10]:
            result[f'PREV_{col}_{n}'] = ser.shift(n)

    # ---- 涨跌幅/变化率 ----
    result['CLOSE_RATE_1'] = close.pct_change(1)        # 1日收益率
    result['CLOSE_RATE_3'] = close.pct_change(3)        # 3日收益率
    result['CLOSE_RATE_5'] = close.pct_change(5)        # 5日收益率
    result['VOLUME_RATE_1'] = volume.pct_change(1)      # 1日量比变化
    result['VOLUME_RATE_3'] = volume.pct_change(3)       # 3日量比变化

    # ---- 均线关系布尔（0/1化，方便AI做加权组合） ----
    result['MA5_GT_MA10']  = (result['MA5']  > result['MA10']).astype(float)
    result['MA5_GT_MA20']  = (result['MA5']  > result['MA20']).astype(float)
    result['MA10_GT_MA20'] = (result['MA10'] > result['MA20']).astype(float)
    result['MA5_GT_MA60']  = (result['MA5']  > result['MA60']).astype(float)
    result['MA20_GT_MA60'] = (result['MA20'] > result['MA60']).astype(float)
    result['CLOSE_GT_MA5'] = (close > result['MA5']).astype(float)
    result['CLOSE_GT_MA10'] = (close > result['MA10']).astype(float)
    result['CLOSE_GT_MA20'] = (close > result['MA20']).astype(float)
    result['CLOSE_GT_MA60'] = (close > result['MA60']).astype(float)

    # ---- 额外均线周期 ----
    result['MA30'] = calc_ma(close, 30)
    result['MA90'] = calc_ma(close, 90)

    # ---- 额外ATR周期 ----
    result['ATR_7']  = calc_atr(high, low, close, 7)
    result['ATR_21'] = calc_atr(high, low, close, 21)

    # ---- 均线标准差（波动率） ----
    result['MA5_STD']  = close.rolling(5).std()
    result['MA10_STD'] = close.rolling(10).std()
    result['MA20_STD'] = close.rolling(20).std()

    # ---- 额外RSI周期 ----
    for p in [3, 9]:
        result[f'RSI_{p}'] = calc_rsi(close, p)

    # ---- MACD多周期 ----
    DIF5,  DEA5,  MACD5  = calc_macd(close, 5,  13, 6)
    DIF20, DEA20, MACD20 = calc_macd(close, 20, 60, 30)
    result['MACD_DIF5']  = DIF5;   result['MACD_DEA5']  = DEA5;   result['MACD_HIST5']  = MACD5
    result['MACD_DIF20'] = DIF20;  result['MACD_DEA20'] = DEA20;  result['MACD_HIST20'] = MACD20

    return result


# ============================================================================
# 存储指标定义到数据库
# ============================================================================

BUILTIN_INDICATORS = [
    # (name, formula描述, params_json, category)
    ("MA5", "收盘价的5日简单移动平均", '{"period": 5}', "builtin"),
    ("MA10", "收盘价的10日简单移动平均", '{"period": 10}', "builtin"),
    ("MA20", "收盘价的20日简单移动平均", '{"period": 20}', "builtin"),
    ("MA60", "收盘价的60日简单移动平均", '{"period": 60}', "builtin"),
    ("MA120", "收盘价的120日简单移动平均", '{"period": 120}', "builtin"),
    ("MA250", "收盘价的250日简单移动平均", '{"period": 250}', "builtin"),
    ("RSI_6", "6日相对强弱指数", '{"period": 6}', "builtin"),
    ("RSI_12", "12日相对强弱指数", '{"period": 12}', "builtin"),
    ("RSI_24", "24日相对强弱指数", '{"period": 24}', "builtin"),
    ("KDJ_K", "KDJ指标的K值", '{"period": 9}', "builtin"),
    ("KDJ_D", "KDJ指标的D值", '{"period": 9}', "builtin"),
    ("KDJ_J", "KDJ指标的J值", '{"period": 9}', "builtin"),
    ("MACD_DIF", "MACD的DIF线", '{"fast": 12, "slow": 26}', "builtin"),
    ("MACD_DEA", "MACD的DEA线", '{"fast": 12, "slow": 26, "signal": 9}', "builtin"),
    ("MACD_HIST", "MACD柱状图", '{"fast": 12, "slow": 26, "signal": 9}', "builtin"),
    ("BOLL_U", "布林带上轨", '{"period": 20}', "builtin"),
    ("BOLL_M", "布林带中轨", '{"period": 20}', "builtin"),
    ("BOLL_L", "布林带下轨", '{"period": 20}', "builtin"),
    ("ATR", "平均真实波幅", '{"period": 14}', "builtin"),
    ("VOL_RATIO", "量比（成交量/5日均量）", '{"period": 5}', "builtin"),
    ("VOL_MA5", "5日均量", '{"period": 5}', "builtin"),
    ("VOL_MA10", "10日均量", '{"period": 10}', "builtin"),
    ("RETURN", "当日收益率", '{"period": 1}', "builtin"),
    ("MA20_DEVIATION", "收盘价对20日均线的偏离度", '{"ma_period": 20}', "builtin"),
    ("MA60_DEVIATION", "收盘价对60日均线的偏离度", '{"ma_period": 60}', "builtin"),
    ("AMPLITUDE", "当日振幅", '{}', "builtin"),
]


def register_builtin_indicators(db_session):
    """注册所有内置指标到数据库"""
    from datetime import datetime
    for name, formula, params, category in BUILTIN_INDICATORS:
        db_session.execute(
            text("""INSERT OR IGNORE INTO indicator_definitions
                    (name, formula, params, category, created_at)
                    VALUES (:name, :formula, :params, :category, :created_at)"""),
            {
                "name": name,
                "formula": formula,
                "params": params,
                "category": category,
                "created_at": datetime.now().isoformat()
            }
        )
    db_session.commit()


if __name__ == "__main__":
    # 测试
    from db.database import create_tables, SessionLocal
    create_tables()
    db = SessionLocal()
    register_builtin_indicators(db)
    print("内置指标注册完成")
    db.close()