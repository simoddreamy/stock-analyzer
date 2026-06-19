"""
数据获取层 - AKShare + Baostock 双源支持
支持增量拉取：从本地最新日期的下一个交易日起拉取，避免重复不遗漏
"""
import akshare as ak
import baostock as bs
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple
import time
import logging

logger = logging.getLogger(__name__)

# 深圳主板股票代码前缀
SZ_PREFIXES = ('000', '001', '002', '003')


def is_sz_main_board(code: str) -> bool:
    """判断是否为深圳主板股票"""
    if len(code) != 6:
        return False
    return code.startswith(SZ_PREFIXES)


def normalise_code(code: str) -> str:
    """标准化股票代码，去除前后空格和前缀0"""
    code = code.strip()
    return code


# ============================================================================
# AKShare 数据源
# ============================================================================

def fetch_kline_akshare(code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    通过AKShare获取单只股票的日K线数据
    code: 股票代码，如 '000001'
    start_date: YYYYMMDD
    end_date: YYYYMMDD
    """
    try:
        # AKShare需要带交易所后缀
        symbol = f"sz{code}"  # 深圳股票前缀sz
        df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date, end_date=end_date, adjust="qfq")
        if df is None or df.empty:
            return None

        # 标准化列名
        df = df.rename(columns={
            '日期': 'date',
            '股票代码': 'code',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
        })
        df['code'] = code
        # 只保留需要的列
        df = df[['code', 'date', 'open', 'high', 'low', 'close', 'volume']]
        return df
    except Exception as e:
        logger.warning(f"AKShare获取 {code} 失败: {e}")
        return None


def fetch_stock_info_akshare(code: str) -> Optional[dict]:
    """通过AKShare获取股票基本信息（已弃用，慢）"""
    return None


def fetch_stock_info_baostock(code: str) -> Optional[dict]:
    """通过Baostock获取股票基本信息（快速）"""
    try:
        import baostock as bs
        bs.login()
        rs = bs.query_stock_basic(code=f"sz.{code}")
        bs.logout()
        if rs.error_code != '0':
            return None
        data = []
        while rs.next():
            data.append(rs.get_row_data())
        if not data:
            return None
        # data[0] = [code, name, list_date, industry, market, status]
        name = data[0][1]
        # Baostock returns GBK encoding, convert to UTF-8 for SQLite storage
        if isinstance(name, bytes):
            name = name.decode('gbk')
        elif isinstance(name, str):
            # Try to handle GBK encoded string by re-encoding
            try:
                name = name.encode('gbk').decode('utf-8')
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass  # keep original if conversion fails
        return {
            'code': code,
            'name': name,
            'list_date': data[0][2] or None,
            'segment': code[:3],
        }
    except Exception as e:
        logger.warning(f"Baostock获取股票信息 {code} 失败: {e}")
        return None


def fetch_stock_info(code: str) -> Optional[dict]:
    """获取股票基本信息，优先用Baostock（快速）"""
    info = fetch_stock_info_baostock(code)
    return info


def fetch_batch_kline_akshare(codes: list, start_date: str, end_date: str) -> pd.DataFrame:
    """
    批量获取多只股票的K线数据
    注意：AKShare有频率限制，每次获取后sleep
    """
    all_dfs = []
    for code in codes:
        df = fetch_kline_akshare(code, start_date, end_date)
        if df is not None and not df.empty:
            all_dfs.append(df)
        time.sleep(0.5)  # 避免触发频率限制
    if not all_dfs:
        return pd.DataFrame()
    return pd.concat(all_dfs, ignore_index=True)


# ============================================================================
# Baostock 数据源（备用）
# ============================================================================

def fetch_kline_baostock(code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    通过Baostock获取单只股票的日K线数据
    code: 股票代码，如 'sz.000001'
    """
    try:
        bs.login()
        # 转换日期格式：YYYYMMDD -> YYYY-MM-DD（Baostock要求）
        start_date_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        end_date_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        rs = bs.query_history_k_data_plus(
            f"sz.{code}",
            "date,open,high,low,close,volume",
            start_date=start_date_fmt,
            end_date=end_date_fmt,
            frequency="d",
            adjustflag="2"  # 前复权
        )
        if rs is None:
            bs.logout()
            logger.warning(f"Baostock获取 {code} 失败: 返回None（日期格式可能不正确）")
            return None

        if rs.error_code != '0':
            bs.logout()
            logger.warning(f"Baostock获取 {code} 失败: {rs.error_msg}")
            return None

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())

        bs.logout()

        if not data_list:
            return None

        df = pd.DataFrame(data_list, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        df['code'] = code
        # 转换数值类型
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df[['code', 'date', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        logger.warning(f"Baostock获取 {code} 失败: {e}")
        return None


def fetch_stock_info_baostock(code: str) -> Optional[dict]:
    """通过Baostock获取股票基本信息（含上市日期）"""
    try:
        bs.login()
        rs = bs.query_stock_basic(code=f"sz.{code}")
        bs.logout()

        if rs.error_code != '0' or rs.error_msg != 'success':
            return None

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            return None

        row = data_list[0]
        return {
            'code': code,
            'name': row[1],
            'list_date': row[2],  # 上市日期
            'segment': code[:3],
        }
    except Exception as e:
        logger.warning(f"Baostock获取股票信息 {code} 失败: {e}")
        return None


# ============================================================================
# 增量拉取逻辑
# ============================================================================

def get_latest_local_date(db_session, code: str) -> Optional[str]:
    """
    获取本地数据库中某股票的最新日期
    返回 YYYYMMDD 格式，无数据返回 None
    """
    from sqlalchemy import text
    result = db_session.execute(
        text("SELECT MAX(date) FROM daily_kline WHERE code = :code"),
        {"code": code}
    ).scalar()
    return result


def sync_stock_kline(db_session, code: str, end_date: str = None, source: str = "akshare") -> Tuple[int, str]:
    """
    同步单只股票的K线数据（增量拉取）
    返回: (新增条数, 状态信息)
    """
    # 确定结束日期
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    # 确定起始日期（从本地最新日期的下一个交易日起）
    latest = get_latest_local_date(db_session, code)
    if latest:
        # 从下一个交易日开始（简化处理，实际需要交易日历）
        start_date = (pd.to_datetime(latest) + timedelta(days=1)).strftime("%Y%m%d")
    else:
        # 本地无数据，从2010年开始（覆盖足够历史）
        start_date = "20100101"

    if start_date > end_date:
        return 0, "已是最新"

    # 尝试主数据源
    if source == "akshare":
        df = fetch_kline_akshare(code, start_date, end_date)
        if df is None or df.empty:
            # 切换到备用数据源
            df = fetch_kline_baostock(code, start_date, end_date)
    else:
        df = fetch_kline_baostock(code, start_date, end_date)
        if df is None or df.empty:
            df = fetch_kline_akshare(code, start_date, end_date)

    if df is None or df.empty:
        return 0, f"数据源获取失败 [{source}]"

    # 写入数据库
    from sqlalchemy import text
    from db.database import engine
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(
                text("""INSERT OR IGNORE INTO daily_kline (code, date, open, high, low, close, volume) VALUES (:code, :date, :open, :high, :low, :close, :volume)"""),
                {
                    'code': row['code'],
                    'date': row['date'],
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume'],
                }
            )

    return len(df), f"成功获取 {len(df)} 条 [{source}]"


def sync_all_watchlist(db_session, end_date: str = None, source: str = "akshare") -> dict:
    """
    同步所有自选股的K线数据
    返回: {code: (新增条数, 状态)}
    """
    from sqlalchemy import text
    codes = db_session.execute(text("SELECT code FROM watchlist")).scalars().all()

    results = {}
    for code in codes:
        count, status = sync_stock_kline(db_session, code, end_date, source)
        results[code] = (count, status)
    return results


if __name__ == "__main__":
    # 测试
    import logging
    logging.basicConfig(level=logging.INFO)
    from db.database import SessionLocal, create_tables
    create_tables()
    db = SessionLocal()
    print(sync_stock_kline(db, "000001", source="akshare"))
    db.close()