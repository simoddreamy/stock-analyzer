"""
FastAPI 主服务 - 股票分析后端API
提供股票数据管理、公式探索、K线查询等接口
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uvicorn
import logging
import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from db.database import get_db, create_tables
from data_fetcher.fetcher import (
    sync_stock_kline,
    sync_all_watchlist,
    fetch_stock_info,
    is_sz_main_board,
)
from indicators.calculator import register_builtin_indicators, precompute_indicators_for_stock, BUILTIN_INDICATORS
from explorer.engine import ExplorationSession, BatchExploration, compute_u1

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Stock Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# 请求/响应模型
# ============================================================================

class U1Config(BaseModel):
    hold_days: int = 5
    profit_pct: float = 2.0
    buy_price: str = "MA5"


class SyncStockRequest(BaseModel):
    code: str
    source: Optional[str] = "akshare"


class AddStockRequest(BaseModel):
    code: str


class ExploreRequest(BaseModel):
    codes: List[str]
    u1_config: U1Config
    mode: str = "single"
    api_key: str
    api_base: str
    model: str = "gpt-4o"


class TestConnectionRequest(BaseModel):
    api_key: str
    api_base: str
    model: str


class SetSettingRequest(BaseModel):
    value: str


# ============================================================================
# 系统接口
# ============================================================================

@app.on_event("startup")
def startup_event():
    create_tables()
    db = next(get_db())
    register_builtin_indicators(db)
    db.close()
    logger.info("系统初始化完成")


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# ============================================================================
# 股票管理
# ============================================================================

@app.post("/api/stocks/add")
def add_stock(req: AddStockRequest, db: Session = Depends(get_db)):
    code = req.code.strip()
    if not is_sz_main_board(code):
        raise HTTPException(400, "仅支持深圳主板股票（000/001/002/003开头）")
    info = fetch_stock_info(code)
    if info is None:
        raise HTTPException(400, f"无法获取股票 {code} 的信息")
    from sqlalchemy import text
    exists = db.execute(text("SELECT 1 FROM watchlist WHERE code = :code"), {"code": code}).scalar()
    if exists:
        return {"code": code, "name": info['name'], "status": "already_exists"}
    db.execute(
        text("INSERT INTO watchlist (code, name, added_at) VALUES (:code, :name, :added_at)"),
        {"code": code, "name": info['name'], "added_at": datetime.now().isoformat()}
    )
    db.commit()
    return {"code": code, "name": info['name'], "status": "added"}


@app.get("/api/stocks/list")
def list_stocks(db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text("SELECT id, code, name, added_at FROM watchlist ORDER BY added_at DESC")).fetchall()
    return [{"id": r[0], "code": r[1], "name": r[2], "added_at": r[3]} for r in rows]


@app.get("/api/stocks/with-opportunities")
def list_stocks_with_opportunities(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    返回有机会点标记的股票列表（按日期范围过滤）
    - start_date / end_date: 可选的范围边界，格式 YYYY-MM-DD
    - 如果不指定范围，返回所有有过机会点的股票
    """
    from sqlalchemy import text

    query = text("""
        SELECT w.code, w.name,
               bf.opportunity_dates,
               bf.formula_expr,
               bf.a1, bf.a2, bf.a3,
               bf.explored_at
        FROM watchlist w
        JOIN best_formulas bf ON w.code = bf.code
        WHERE bf.opportunity_dates IS NOT NULL
          AND bf.opportunity_dates != '[]'
        ORDER BY bf.explored_at DESC
    """)
    rows = db.execute(query).fetchall()
    result = []
    for r in rows:
        opp_dates = json.loads(r[2]) if r[2] else []
        # 按日期范围过滤
        if start_date:
            opp_dates = [d for d in opp_dates if d >= start_date]
        if end_date:
            opp_dates = [d for d in opp_dates if d <= end_date]
        if opp_dates or (not start_date and not end_date):
            result.append({
                "code": r[0],
                "name": r[1],
                "formula_expr": r[3],
                "a1": r[4],
                "a2": r[5],
                "a3": r[6],
                "explored_at": r[7],
                "opp_dates": sorted(opp_dates),
                "opp_count": len(opp_dates),
                "has_opportunities": len(opp_dates) > 0,
            })
    return result


@app.delete("/api/stocks/{code}")
def delete_stock(code: str, db: Session = Depends(get_db)):
    from sqlalchemy import text
    db.execute(text("DELETE FROM watchlist WHERE code = :code"), {"code": code})
    db.commit()
    return {"status": "deleted", "code": code}


class ImportStocksRequest(BaseModel):
    codes: List[str]


@app.post("/api/stocks/import")
def import_stocks(req: ImportStocksRequest, db: Session = Depends(get_db)):
    from sqlalchemy import text
    added, failed = [], []
    for code in req.codes:
        code = code.strip()
        if not is_sz_main_board(code):
            failed.append(code); continue
        info = fetch_stock_info(code)
        if info is None:
            failed.append(code); continue
        try:
            db.execute(
                text("INSERT OR IGNORE INTO watchlist (code, name, added_at) VALUES (:code, :name, :added_at)"),
                {"code": code, "name": info['name'], "added_at": datetime.now().isoformat()}
            )
            added.append(code)
        except Exception:
            failed.append(code)
    db.commit()
    return {"added": added, "failed": failed}


# ============================================================================
# 数据同步
# ============================================================================

@app.post("/api/data/sync-all")
def sync_all(db: Session = Depends(get_db)):
    results = sync_all_watchlist(db, source="akshare")
    from sqlalchemy import text
    # 增量同步完成后，对每只有公式且有新数据的股票自动更新机会点
    for code, (count, status) in results.items():
        if count > 0:
            fm_row = db.execute(
                text("SELECT COUNT(*) FROM best_formulas WHERE code = :code AND formula_expr IS NOT NULL"),
                {"code": code}
            ).fetchone()
            if fm_row and fm_row[0] > 0:
                update_opportunities_single(code, db)
    db.execute(text("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync', :val)"),
               {"val": datetime.now().isoformat()})
    db.commit()
    return {"results": {code: {"count": r[0], "status": r[1]} for code, r in results.items()}, "synced_at": datetime.now().isoformat()}


@app.post("/api/data/sync-stock")
def sync_stock(req: SyncStockRequest, db: Session = Depends(get_db)):
    count, status = sync_stock_kline(db, req.code, source=req.source)
    opp_result = None
    # 如果有新增K线数据 且该股票已有公式，自动更新机会点
    if count > 0:
        fm_row = db.execute(
            text("SELECT COUNT(*) FROM best_formulas WHERE code = :code AND formula_expr IS NOT NULL"),
            {"code": req.code}
        ).fetchone()
        if fm_row and fm_row[0] > 0:
            opp_result = update_opportunities_single(req.code, db)
    return {
        "code": req.code,
        "new_records": count,
        "status": status,
        "opportunity_updated": opp_result is not None,
        "opp_result": opp_result,
    }


# ============================================================================
# K线与指标
# ============================================================================

@app.get("/api/kline/{code}")
def get_kline(code: str, db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(
        text("SELECT date, open, high, low, close, volume FROM daily_kline WHERE code = :code ORDER BY date"),
        {"code": code}
    ).fetchall()
    return [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]


@app.get("/api/indicators/{code}")
def get_indicators(code: str, db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(
        text("SELECT date, open, high, low, close, volume FROM daily_kline WHERE code = :code ORDER BY date"),
        {"code": code}
    ).fetchall()
    if not rows:
        return []
    import pandas as pd
    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = df['date'].astype(str)
    ind_df = precompute_indicators_for_stock(code, df)
    records = []
    for _, row in ind_df.iterrows():
        record = {"date": row['date']}
        for col in ind_df.columns:
            if col != 'date':
                val = row[col]
                record[col] = None if pd.isna(val) else float(val)
        records.append(record)
    return records


# ============================================================================
# 优选公式
# ============================================================================

@app.get("/api/formulas/{code}")
def get_formulas(code: str, db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(
        text("SELECT id, code, logic_desc, formula_expr, a1, a2, a3, explored_at FROM best_formulas WHERE code = :code ORDER BY explored_at DESC"),
        {"code": code}
    ).fetchall()
    return [{"id": r[0], "code": r[1], "logic_desc": r[2], "formula_expr": r[3], "a1": r[4], "a2": r[5], "a3": r[6], "explored_at": r[7]} for r in rows]


@app.get("/api/formulas/{code}/opportunity")
def get_opportunity_points(code: str, db: Session = Depends(get_db)):
    """读取数据库中该股票的机会点（从best_formulas.opportunity_dates读取）"""
    from sqlalchemy import text
    row = db.execute(
        text("SELECT opportunity_dates FROM best_formulas WHERE code = :code ORDER BY explored_at DESC LIMIT 1"),
        {"code": code}
    ).fetchone()
    if not row or row[0] is None:
        return {"code": code, "opp_dates": [], "count": 0, "has_formula": False}
    opp_dates = json.loads(row[0])
    return {"code": code, "opp_dates": opp_dates, "count": len(opp_dates), "has_formula": True}


@app.post("/api/formulas/{code}/update-opportunities")
def update_opportunities_single(code: str, db: Session = Depends(get_db)):
    """重新计算并保存该股票的买点（U1）和机会点（U2），全量替换，同时更新三段精度a1/a2/a3"""
    from sqlalchemy import text
    import pandas as pd
    import numpy as np
    from indicators.calculator import precompute_indicators_for_stock
    from explorer.engine import simulate_u2_evaluation, CandidateFormula, compute_u1

    # 优先读取手动覆盖公式，其次读取AI探索的最佳公式
    override_row = db.execute(
        text("SELECT logic_desc, formula_expr FROM formula_overrides WHERE code = :code LIMIT 1"),
        {"code": code}
    ).fetchone()
    if override_row:
        logic_desc, formula_expr = override_row[0], override_row[1]
    else:
        fm_row = db.execute(
            text("SELECT logic_desc, formula_expr FROM best_formulas WHERE code = :code ORDER BY explored_at DESC LIMIT 1"),
            {"code": code}
        ).fetchone()
        if not fm_row:
            return {"code": code, "updated": False, "error": "No best formula found"}
        logic_desc, formula_expr = fm_row[0], fm_row[1]

    kline_rows = db.execute(
        text("SELECT date, open, high, low, close, volume FROM daily_kline WHERE code = :code ORDER BY date"),
        {"code": code}
    ).fetchall()
    if not kline_rows:
        return {"code": code, "updated": False, "error": "No K-line data"}

    df = pd.DataFrame(kline_rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = df['date'].astype(str)

    # 读取 u1_config 配置（买点计算参数：买入价方式、持有天数、盈利目标）
    cfg = db.execute(text("SELECT hold_days, profit_pct, buy_price FROM u1_config WHERE enabled=1")).fetchone()
    u1_cfg = {'hold_days': cfg[0], 'profit_pct': float(cfg[1]), 'buy_price': cfg[2]} if cfg else {'hold_days': 5, 'profit_pct': 2.0, 'buy_price': 'MA5'}

    # 获取完整K线数据（增量同步后已更新）
    kline_rows = db.execute(
        text("SELECT date, open, high, low, close, volume FROM daily_kline WHERE code = :code ORDER BY date"),
        {"code": code}
    ).fetchall()
    if not kline_rows:
        return {"code": code, "updated": False, "error": "No K-line data"}

    df = pd.DataFrame(kline_rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = df['date'].astype(str)

    # 计算指标 dataframe（用于 U2 公式求值）
    indicator_df = precompute_indicators_for_stock(code, df)

    candidate = CandidateFormula(
        logic_desc=logic_desc, formula_expr=formula_expr,
        indicators=[], precision=0.0, coverage_count=0, u2_count=0, stage=''
    )

    # ----------------------------------------------------------------
    # Step 1: 用完整新K线数据重新计算 U1 买点（买点可能因新数据而增加）
    # ----------------------------------------------------------------
    u1_dates = compute_u1(db, code, u1_cfg)
    u1_dates_str = json.dumps(sorted(list(u1_dates)))

    # ----------------------------------------------------------------
    # Step 2: 用 U1 买点 + 最优公式 计算 U2 机会点（可能因新买点或新K线而增加）
    # ----------------------------------------------------------------
    u2_dates = simulate_u2_evaluation(indicator_df, candidate, u1_cfg)
    opp_dates_str = json.dumps(sorted(list(u2_dates)))

    # ----------------------------------------------------------------
    # Step 3: 计算三段精度 a1/a2/a3
    #    a1 = 段1中 U1∩U2 合格点数 / 段1中 U2 总点数
    #    a2 = 段2中 U1∩U2 合格点数 / 段2中 U2 总点数
    #    a3 = 段3中 U1∩U2 合格点数 / 段3中 U2 总点数
    # ----------------------------------------------------------------
    n = len(df)
    if n < 300:
        s1, s2 = int(n * 0.4), int(n * 0.7)
    else:
        s1, s2 = int(n * 0.35), int(n * 0.65)

    def segment_precision(df_sub):
        """计算子区间 df_sub 的 a 精度：U1买点∩U2机会点 / U2机会点"""
        if df_sub.empty:
            return 0.0
        sub_code = df_sub['code'].iloc[0] if 'code' in df_sub.columns else code
        u1_sub = compute_u1(db, sub_code, u1_cfg) if sub_code == code else set()
        if len(u1_sub) == 0:
            return 0.0
        seg_indicator = precompute_indicators_for_stock(code, df_sub)
        u2_sub = simulate_u2_evaluation(seg_indicator, candidate, u1_cfg)
        inter = u1_sub & u2_sub
        return len(inter) / len(u2_sub) if len(u2_sub) > 0 else 0.0

    a1 = segment_precision(df.iloc[:s1])
    a2 = segment_precision(df.iloc[s1:s2])
    a3 = segment_precision(df.iloc[s2:n-5]) if s2 < n - 5 else 0.0

    # ----------------------------------------------------------------
    # Step 4: 持久化 —— 买点（u1_dates）、机会点（opp_dates）、三段精度
    # ----------------------------------------------------------------
    db.execute(
        text("UPDATE best_formulas SET opportunity_dates = :opp, u1_dates = :u1, a1 = :a1, a2 = :a2, a3 = :a3 WHERE code = :code"),
        {"opp": opp_dates_str, "u1": u1_dates_str, "a1": a1, "a2": a2, "a3": a3, "code": code}
    )
    db.commit()
    return {"code": code, "updated": True, "u1_count": len(u1_dates), "u2_count": len(u2_dates), "a1": round(a1,3), "a2": round(a2,3), "a3": round(a3,3)}


@app.post("/api/formulas/update-opportunities")
def update_opportunities(db: Session = Depends(get_db)):
    """Recalculate opportunity points for all stocks with a best formula"""
    from sqlalchemy import text
    import pandas as pd
    from indicators.calculator import precompute_indicators_for_stock
    from explorer.engine import simulate_u2_evaluation, CandidateFormula

    # Get all stocks with best formulas
    stock_rows = db.execute(text("SELECT DISTINCT code FROM best_formulas")).fetchall()
    results = []

    for (code,) in stock_rows:
        try:
            fm_row = db.execute(
                text("SELECT logic_desc, formula_expr FROM best_formulas WHERE code = :code ORDER BY explored_at DESC LIMIT 1"),
                {"code": code}
            ).fetchone()
            if not fm_row:
                continue
            logic_desc, formula_expr = fm_row[0], fm_row[1]

            kline_rows = db.execute(
                text("SELECT date, open, high, low, close, volume FROM daily_kline WHERE code = :code ORDER BY date"),
                {"code": code}
            ).fetchall()
            if not kline_rows:
                continue

            df = pd.DataFrame(kline_rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
            df['date'] = df['date'].astype(str)

            indicator_df = precompute_indicators_for_stock(code, df)

            candidate = CandidateFormula(
                logic_desc=logic_desc, formula_expr=formula_expr,
                indicators=[], precision=0.0, coverage_count=0, u2_count=0, stage=''
            )

            cfg = db.execute(text("SELECT hold_days, profit_pct, buy_price FROM u1_config WHERE enabled=1")).fetchone()
            u1_cfg = {'hold_days': cfg[0], 'profit_pct': float(cfg[1]), 'buy_price': cfg[2]} if cfg else {'hold_days': 5, 'profit_pct': 2.0, 'buy_price': 'MA5'}

            u2_dates = simulate_u2_evaluation(indicator_df, candidate, u1_cfg)
            opp_dates_str = json.dumps(sorted(list(u2_dates)))

            db.execute(
                text("UPDATE best_formulas SET opportunity_dates = :opp WHERE code = :code"),
                {"opp": opp_dates_str, "code": code}
            )
            results.append({"code": code, "count": len(u2_dates)})
        except Exception as e:
            results.append({"code": code, "error": str(e)})

    db.commit()
    return {"updated": results}


@app.get("/api/formulas/{code}/u1")
def get_u1_buy_points(code: str, db: Session = Depends(get_db)):
    from sqlalchemy import text
    cfg = db.execute(text("SELECT hold_days, profit_pct, buy_price FROM u1_config WHERE enabled=1")).fetchone()
    u1_cfg = {'hold_days': cfg[0], 'profit_pct': float(cfg[1]), 'buy_price': cfg[2]} if cfg else {'hold_days': 5, 'profit_pct': 2.0, 'buy_price': 'MA5'}
    u1_dates = compute_u1(db, code, u1_cfg)
    return {"code": code, "u1_dates": list(u1_dates), "count": len(u1_dates)}


# ============================================================================
# 探索任务状态（内存中的进度追踪，支持页面切换后恢复）
# ============================================================================

_exploration_state = {
    "code": "",
    "status": "idle",  # idle | running | paused | completed | timeout
    "elapsed": 0,
    "stage": "",
    "candidates_explored": 0,
    "best_candidate": None,
    "session_id": None,
    "current_candidates": [],  # 本轮候选列表（含公式+逻辑+当前精度/覆盖率）
}
_running_session = None  # 当前后台运行的 ExplorationSession 引用


@app.get("/api/explore/status")
def get_explore_status():
    """查询当前探索任务状态，前端页面切换后可用此接口恢复状态"""
    return {
        "status": _exploration_state["status"],
        "code": _exploration_state["code"],
        "elapsed": _exploration_state["elapsed"],
        "stage": _exploration_state["stage"],
        "candidates_explored": _exploration_state["candidates_explored"],
        "best_candidate": _exploration_state["best_candidate"],
        "current_candidates": _exploration_state["current_candidates"],
    }


@app.post("/api/explore/stop")
def stop_exploration():
    """终止当前探索任务"""
    if _running_session:
        _running_session.status = "stopped"
    _exploration_state["status"] = "idle"
    return {"ok": True}


@app.post("/api/explore/pause")
def pause_exploration():
    """暂停当前探索任务（ ExplorationSession.run 循环会检查 self.status != 'running'）"""
    if _running_session:
        _running_session.status = "paused"
    if _exploration_state["status"] == "running":
        _exploration_state["status"] = "paused"
    return {"ok": True}


# ============================================================================
# 探索任务
# ============================================================================

@app.post("/api/explore")
def start_exploration(req: ExploreRequest, db: Session = Depends(get_db)):
    global _running_session
    u1_cfg = req.u1_config.dict()

    # 如果已经有任务在跑，拒绝
    if _exploration_state["status"] == "running":
        raise HTTPException(409, "已有探索任务正在进行")

    if req.mode != "single":
        raise HTTPException(400, "当前只支持单只股票模式")

    code = req.codes[0]

    # 初始化状态
    _exploration_state.update({
        "code": code,
        "status": "running",
        "elapsed": 0,
        "stage": "准备数据",
        "candidates_explored": 0,
        "best_candidate": None,
    })

    def progress_handler(progress):
        _exploration_state["elapsed"] = progress.elapsed_seconds
        _exploration_state["stage"] = progress.current_stage
        _exploration_state["candidates_explored"] = progress.candidates_explored
        if progress.best_candidate:
            _exploration_state["best_candidate"] = {
                "formula_expr": progress.best_candidate.formula_expr,
                "logic_desc": progress.best_candidate.logic_desc,
                "precision": progress.best_candidate.precision,
                "coverage_count": progress.best_candidate.coverage_count,
            }
        _exploration_state["current_candidates"] = progress.current_candidates or []

    def save_report(session, status):
        """探索结束时保存报告到数据库"""
        import json
        from datetime import datetime
        best = session.best_candidate
        history = session.candidate_history
        # 找第一段表现最好的候选
        best_in_s1 = None
        if history:
            scored = [(h, h.get('segment1', {}).get('precision', 0)) for h in history]
            best_in_s1 = max(scored, key=lambda x: x[1])[0] if scored else None
        segments_data = json.dumps(session.segment_u1, ensure_ascii=False)
        best_formula = best.formula_expr if best else (best_in_s1['formula'] if best_in_s1 else None)
        best_precision = best.precision if best else (best_in_s1['segment1']['precision'] if best_in_s1 else None)
        best_coverage = best.coverage_count if best else (best_in_s1['segment1']['coverage'] if best_in_s1 else None)
        final_msg = {"completed": "探索完成", "timeout": "探索超时", "stopped": "探索已终止"}.get(status, "探索失败")
        db = next(get_db())
        try:
            db.execute(text(
                """INSERT INTO exploration_reports
                (session_id, code, status, total_seconds, candidates_total, segments_data,
                 best_formula, best_precision, best_coverage, iterations, final_message, created_at)
                VALUES (:sid, :code, :status, :total, :cands, :segs, :bf, :bp, :bc, :iter, :msg, :at)"""
            ), {
                "sid": None, "code": session.code, "status": status,
                "total": session._elapsed(), "cands": session.candidates_explored,
                "segs": segments_data, "bf": best_formula, "bp": best_precision,
                "bc": best_coverage, "iter": session.iteration_count,
                "msg": final_msg, "at": datetime.now().isoformat()
            })
            db.commit()
            logger.info(f"探索报告已保存: {session.code} status={status}")
        finally:
            db.close()

    def run_explore():
        global _running_session
        db = next(get_db())
        try:
            session = ExplorationSession(
                db=db, code=code, u1_config=u1_cfg,
                api_key=req.api_key, api_base=req.api_base, model=req.model, time_limit=600,
                progress_callback=progress_handler
            )
            _running_session = session
            result = session.run()
            final_status = session.status
            _exploration_state["status"] = final_status
            save_report(session, final_status)
            if result or session.best_candidate:
                cand = result or session.best_candidate
                _exploration_state["best_candidate"] = {
                    "formula_expr": cand.formula_expr,
                    "logic_desc": cand.logic_desc,
                    "precision": cand.precision,
                    "coverage_count": cand.coverage_count,
                }
        finally:
            _running_session = None
            db.close()

    thread = threading.Thread(target=run_explore, daemon=True)
    thread.start()

    return {"status": "started", "code": code}


# ============================================================================
# 探索历史报告
# ============================================================================

@app.get("/api/explore/reports")
def list_explore_reports(code: Optional[str] = None, db: Session = Depends(get_db)):
    """查询探索历史报告列表，可按股票代码过滤"""
    from sqlalchemy import text
    if code:
        sql = "SELECT id, code, status, total_seconds, candidates_total, best_formula, best_precision, best_coverage, iterations, final_message, created_at FROM exploration_reports WHERE code = :code ORDER BY created_at DESC LIMIT 50"
        rows = db.execute(text(sql), {"code": code}).fetchall()
    else:
        sql = "SELECT id, code, status, total_seconds, candidates_total, best_formula, best_precision, best_coverage, iterations, final_message, created_at FROM exploration_reports ORDER BY created_at DESC LIMIT 50"
        rows = db.execute(text(sql)).fetchall()
    return [
        {
            "id": r[0], "code": r[1], "status": r[2], "total_seconds": r[3],
            "candidates_total": r[4], "best_formula": r[5],
            "best_precision": r[6], "best_coverage": r[7],
            "iterations": r[8], "final_message": r[9], "created_at": r[10]
        }
        for r in rows
    ]


@app.get("/api/explore/reports/{report_id}")
def get_explore_report(report_id: int, db: Session = Depends(get_db)):
    """获取单条探索报告详情（含各段U1数量）"""
    row = db.execute(text(
        """SELECT id, session_id, code, status, total_seconds, candidates_total,
                  segments_data, best_formula, best_precision, best_coverage,
                  iterations, final_message, created_at
           FROM exploration_reports WHERE id = :id"""
    ), {"id": report_id}).fetchone()
    if not row:
        raise HTTPException(404, "报告不存在")
    import json
    return {
        "id": row[0], "session_id": row[1], "code": row[2], "status": row[3],
        "total_seconds": row[4], "candidates_total": row[5],
        "segments_data": json.loads(row[6]) if row[6] else {},
        "best_formula": row[7], "best_precision": row[8], "best_coverage": row[9],
        "iterations": row[10], "final_message": row[11], "created_at": row[12]
    }


# ============================================================================
# 用户手动配置最优公式
# ============================================================================

@app.post("/api/formulas/{code}/override")
def override_formula(code: str, req: dict, db: Session = Depends(get_db)):
    """手动配置/覆盖某只股票的最优公式，替换系统记录"""
    formula_expr = req.get("formula_expr", "").strip()
    logic_desc = req.get("logic_desc", "").strip()
    if not formula_expr:
        raise HTTPException(400, "formula_expr 不能为空")
    from datetime import datetime
    # upsert into formula_overrides
    db.execute(text(
        """INSERT INTO formula_overrides (code, logic_desc, formula_expr, a1, a2, a3, source, created_at)
           VALUES (:code, :ld, :fe, NULL, NULL, NULL, 'manual', :at)
           ON CONFLICT(code) DO UPDATE SET
               logic_desc=excluded.logic_desc, formula_expr=excluded.formula_expr, created_at=excluded.created_at"""
    ), {"code": code, "ld": logic_desc, "fe": formula_expr, "at": datetime.now().isoformat()})
    # 同时更新 best_formulas 的 override 记录（优先读取 override）
    db.execute(text(
        """INSERT INTO best_formulas (code, u1_config_id, logic_desc, formula_expr, a1, a2, a3, explored_at, source)
           VALUES (:code, 1, :ld, :fe, NULL, NULL, NULL, :at, 'manual')
           ON CONFLICT(code) DO UPDATE SET
               logic_desc=excluded.logic_desc, formula_expr=excluded.formula_expr,
               a1=NULL, a2=NULL, a3=NULL, opportunity_dates=NULL,
               source='manual', explored_at=excluded.explored_at"""
    ), {"code": code, "ld": logic_desc, "fe": formula_expr, "at": datetime.now().isoformat()})
    db.commit()
    return {"ok": True, "code": code, "formula_expr": formula_expr}


@app.get("/api/formulas/{code}/override")
def get_formula_override(code: str, db: Session = Depends(get_db)):
    """查询某股票的手动覆盖公式"""
    row = db.execute(text(
        """SELECT logic_desc, formula_expr, source, created_at
           FROM formula_overrides WHERE code = :code"""
    ), {"code": code}).fetchone()
    if not row:
        return None
    return {
        "code": code, "logic_desc": row[0], "formula_expr": row[1],
        "source": row[2], "created_at": row[3]
    }


# ============================================================================
# 预置条件配置（指标参数库）
# ============================================================================

def _get_next_sequence(db, table: str) -> str:
    """自动生成下一个序号（I001, I002, ...）"""
    prefix = "I" if table == "indicator_params" else "F"
    rows = db.execute(text(
        f"SELECT sequence_number FROM {table} WHERE sequence_number LIKE :prefix ORDER BY sequence_number"
    ), {"prefix": f"{prefix}%"}).fetchall()
    if not rows:
        return f"{prefix}001"
    max_num = 0
    for r in rows:
        try:
            num = int(r[0][1:])  # strip prefix
            if num > max_num:
                max_num = num
        except (ValueError, IndexError):
            pass
    return f"{prefix}{max_num + 1:03d}"


@app.get("/api/logic/indicators")
def list_indicators(db: Session = Depends(get_db)):
    """列出所有预置条件（指标参数）"""
    rows = db.execute(text(
        """SELECT id, sequence_number, name, param_config, description, created_at, updated_at
           FROM indicator_params ORDER BY sequence_number ASC"""
    )).fetchall()
    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "sequence_number": r[1] or "",
            "name": r[2],
            "param_config": json.loads(r[3]) if r[3] else {},
            "description": r[4] or "",
            "created_at": r[5],
            "updated_at": r[6]
        })
    return result


class IndicatorParamRequest(BaseModel):
    sequence_number: Optional[str] = ""  # 可选，用户可指定
    name: str
    param_config: dict
    description: str = ""


@app.post("/api/logic/indicators")
def create_indicator(req: IndicatorParamRequest, db: Session = Depends(get_db)):
    """新增一条预置条件"""
    try:
        # 自动生成序号（如果未指定）
        seq = req.sequence_number.strip() if req.sequence_number else ""
        if not seq:
            seq = _get_next_sequence(db, "indicator_params")

        # 校验序号唯一性
        existing = db.execute(text(
            "SELECT id FROM indicator_params WHERE sequence_number=:seq"
        ), {"seq": seq}).fetchone()
        if existing:
            raise HTTPException(400, f"序号 {seq} 已存在，请使用其他序号")

        db.execute(text(
            """INSERT INTO indicator_params (sequence_number, name, param_config, description, created_at, updated_at)
               VALUES (:sequence_number, :name, :param_config, :description, :created_at, :updated_at)"""
        ), {
            "sequence_number": seq,
            "name": req.name,
            "param_config": json.dumps(req.param_config),
            "description": req.description,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        })
        db.commit()
        row = db.execute(text("SELECT last_insert_rowid()")).fetchone()
        return {"id": row[0], "sequence_number": seq, "name": req.name, "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(400, str(e))


@app.put("/api/logic/indicators/{id}")
def update_indicator(id: int, req: IndicatorParamRequest, db: Session = Depends(get_db)):
    """更新一条预置条件"""
    try:
        seq = req.sequence_number.strip() if req.sequence_number else ""

        # 校验序号唯一性（排除自己）
        if seq:
            existing = db.execute(text(
                "SELECT id FROM indicator_params WHERE sequence_number=:seq AND id!=:id"
            ), {"seq": seq, "id": id}).fetchone()
            if existing:
                raise HTTPException(400, f"序号 {seq} 已存在，请使用其他序号")
        else:
            seq = None

        db.execute(text(
            """UPDATE indicator_params
               SET sequence_number=:sequence_number, name=:name, param_config=:param_config,
                   description=:description, updated_at=:updated_at
               WHERE id=:id"""
        ), {
            "id": id,
            "sequence_number": seq,
            "name": req.name,
            "param_config": json.dumps(req.param_config),
            "description": req.description,
            "updated_at": datetime.now().isoformat()
        })
        db.commit()
        return {"id": id, "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(400, str(e))


@app.delete("/api/logic/indicators/{id}")
def delete_indicator(id: int, db: Session = Depends(get_db)):
    """删除一条预置条件"""
    db.execute(text("DELETE FROM indicator_params WHERE id=:id"), {"id": id})
    db.commit()
    return {"id": id, "ok": True}


# ============================================================================
# 公式组合配置
# ============================================================================

async def _call_llm_for_description(formula_expr: str, indicator_map: dict) -> str:
    """调用大模型解释公式表达式，生成中文描述"""
    import httpx

    # 获取LLM配置
    from db.database import SessionLocal as DBLib
    db = DBLib()
    try:
        api_key = db.execute(text("SELECT value FROM settings WHERE key='api_key'")).scalar()
        api_base = db.execute(text("SELECT value FROM settings WHERE key='api_base'")).scalar()
        model = db.execute(text("SELECT value FROM settings WHERE key='model'")).scalar()
    finally:
        db.close()

    if not api_key or not api_base:
        return "（未配置大模型，无法生成描述）"

    # 构建指标说明
    ind_info = []
    for seq, ind_name in indicator_map.items():
        ind_info.append(f"{seq}: {ind_name}")
    ind_text = "\n".join(ind_info) if ind_info else "无"

    prompt = f"""你是一个股票交易策略专家。请解释以下公式表达式的含义，用简洁的中文描述。

公式表达式：{formula_expr}

指标对照表：
{ind_text}

请用一句话描述这个公式的选股逻辑，例如："RSI指标超买且成交量放大"。
只返回描述文字，不要其他内容。"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model or "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200
                }
            )
        if response.status_code == 200:
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return ""


@app.get("/api/logic/formulas")
def list_formula_combinations(db: Session = Depends(get_db)):
    """列出所有已配置的公式组合"""
    rows = db.execute(text(
        """SELECT id, sequence_number, name, formula_expr, logic_desc, indicator_refs, created_at, updated_at
           FROM formula_combinations ORDER BY sequence_number ASC"""
    )).fetchall()
    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "sequence_number": r[1] or "",
            "name": r[2],
            "formula_expr": r[3],
            "logic_desc": r[4] or "",
            "indicator_refs": json.loads(r[5]) if r[5] else [],
            "created_at": r[6],
            "updated_at": r[7]
        })
    return result


class FormulaCombinationRequest(BaseModel):
    sequence_number: Optional[str] = ""
    name: str
    formula_expr: str
    logic_desc: Optional[str] = ""  # 可选，如果为空则自动调用LLM生成
    indicator_refs: List[int] = []
    auto_desc: bool = True  # 是否自动调用LLM生成描述


@app.post("/api/logic/formulas")
def create_formula_combination(req: FormulaCombinationRequest, db: Session = Depends(get_db)):
    """新增一条公式组合，自动生成序号，可调用LLM生成描述"""
    import asyncio
    try:
        # 自动生成序号
        seq = req.sequence_number.strip() if req.sequence_number else ""
        if not seq:
            seq = _get_next_sequence(db, "formula_combinations")

        # 校验序号唯一性
        existing = db.execute(text(
            "SELECT id FROM formula_combinations WHERE sequence_number=:seq"
        ), {"seq": seq}).fetchone()
        if existing:
            raise HTTPException(400, f"序号 {seq} 已存在，请使用其他序号")

        # 获取指标名称映射（用于LLM描述）
        indicator_map = {}
        if req.indicator_refs:
            ids = req.indicator_refs
            placeholders = ','.join([f':id{i}' for i in range(len(ids))])
            rows = db.execute(text(
                f"SELECT id, sequence_number, name FROM indicator_params WHERE id IN ({placeholders})"
            ), {f'id{i}': v for i, v in enumerate(ids)}).fetchall()
            for r in rows:
                indicator_map[r[1] or f"I{r[0]:03d}"] = r[2]

        # 自动调用LLM生成描述
        logic_desc = req.logic_desc
        if req.auto_desc and not logic_desc:
            # 在同步上下文中调用异步LLM
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已经在运行，创建一个新线程来执行
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, _call_llm_for_description(req.formula_expr, indicator_map))
                        logic_desc = future.result(timeout=35)
                else:
                    logic_desc = loop.run_until_complete(_call_llm_for_description(req.formula_expr, indicator_map))
            except Exception:
                logic_desc = ""

        db.execute(text(
            """INSERT INTO formula_combinations (sequence_number, name, formula_expr, logic_desc, indicator_refs, created_at, updated_at)
               VALUES (:sequence_number, :name, :formula_expr, :logic_desc, :indicator_refs, :created_at, :updated_at)"""
        ), {
            "sequence_number": seq,
            "name": req.name,
            "formula_expr": req.formula_expr,
            "logic_desc": logic_desc or "",
            "indicator_refs": json.dumps(req.indicator_refs),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        })
        db.commit()
        row = db.execute(text("SELECT last_insert_rowid()")).fetchone()
        return {"id": row[0], "sequence_number": seq, "name": req.name, "logic_desc": logic_desc, "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(400, str(e))


@app.put("/api/logic/formulas/{id}")
def update_formula_combination(id: int, req: FormulaCombinationRequest, db: Session = Depends(get_db)):
    """更新一条公式组合"""
    import asyncio
    try:
        seq = req.sequence_number.strip() if req.sequence_number else ""

        # 校验序号唯一性（排除自己）
        if seq:
            existing = db.execute(text(
                "SELECT id FROM formula_combinations WHERE sequence_number=:seq AND id!=:id"
            ), {"seq": seq, "id": id}).fetchone()
            if existing:
                raise HTTPException(400, f"序号 {seq} 已存在，请使用其他序号")
        else:
            seq = None

        # 获取指标名称映射
        indicator_map = {}
        if req.indicator_refs:
            ids = req.indicator_refs
            placeholders = ','.join([f':id{i}' for i in range(len(ids))])
            rows = db.execute(text(
                f"SELECT id, sequence_number, name FROM indicator_params WHERE id IN ({placeholders})"
            ), {f'id{i}': v for i, v in enumerate(ids)}).fetchall()
            for r in rows:
                indicator_map[r[1] or f"I{r[0]:03d}"] = r[2]

        # 如果需要重新生成描述
        logic_desc = req.logic_desc
        if req.auto_desc and not logic_desc:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, _call_llm_for_description(req.formula_expr, indicator_map))
                        logic_desc = future.result(timeout=35)
                else:
                    logic_desc = loop.run_until_complete(_call_llm_for_description(req.formula_expr, indicator_map))
            except Exception:
                logic_desc = ""

        db.execute(text(
            """UPDATE formula_combinations
               SET sequence_number=:sequence_number, name=:name, formula_expr=:formula_expr,
                   logic_desc=:logic_desc, indicator_refs=:indicator_refs, updated_at=:updated_at
               WHERE id=:id"""
        ), {
            "id": id,
            "sequence_number": seq,
            "name": req.name,
            "formula_expr": req.formula_expr,
            "logic_desc": logic_desc or "",
            "indicator_refs": json.dumps(req.indicator_refs),
            "updated_at": datetime.now().isoformat()
        })
        db.commit()
        return {"id": id, "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(400, str(e))


@app.delete("/api/logic/formulas/{id}")
def delete_formula_combination(id: int, db: Session = Depends(get_db)):
    """删除一条公式组合"""
    db.execute(text("DELETE FROM formula_combinations WHERE id=:id"), {"id": id})
    db.commit()
    return {"id": id, "ok": True}


# 手动触发LLM描述生成（供前端调用）
@app.post("/api/logic/formulas/{id}/regenerate-desc")
def regenerate_formula_desc(id: int, db: Session = Depends(get_db)):
    """手动重新生成公式描述"""
    import asyncio
    try:
        row = db.execute(text(
            "SELECT formula_expr, indicator_refs FROM formula_combinations WHERE id=:id"
        ), {"id": id}).fetchone()
        if not row:
            raise HTTPException(404, "公式不存在")

        formula_expr = row[0]
        indicator_refs = json.loads(row[1]) if row[1] else []

        # 获取指标名称映射
        indicator_map = {}
        if indicator_refs:
            ids = indicator_refs
            placeholders = ','.join([f':id{i}' for i in range(len(ids))])
            rows = db.execute(text(
                f"SELECT id, sequence_number, name FROM indicator_params WHERE id IN ({placeholders})"
            ), {f'id{i}': v for i, v in enumerate(ids)}).fetchall()
            for r in rows:
                indicator_map[r[1] or f"I{r[0]:03d}"] = r[2]

        # 调用LLM
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _call_llm_for_description(formula_expr, indicator_map))
                    logic_desc = future.result(timeout=35)
            else:
                logic_desc = loop.run_until_complete(_call_llm_for_description(formula_expr, indicator_map))
        except Exception:
            logic_desc = ""

        db.execute(text(
            "UPDATE formula_combinations SET logic_desc=:logic_desc, updated_at=:updated_at WHERE id=:id"
        ), {"id": id, "logic_desc": logic_desc, "updated_at": datetime.now().isoformat()})
        db.commit()
        return {"id": id, "logic_desc": logic_desc, "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(400, str(e))


# ============================================================================
# 内置指标定义（供前端下拉选择）
# ============================================================================

# 内置指标的详细元数据（描述、参数范围、值类型）
BUILTIN_META = {
    "MA5":         {"desc": "5日简单移动平均，常用短期趋势判断", "params": {"period": {"type": "int", "min": 1, "max": 250, "default": 5, "step": 1}}},
    "MA10":        {"desc": "10日简单移动平均，中短期趋势", "params": {"period": {"type": "int", "min": 1, "max": 250, "default": 10, "step": 1}}},
    "MA20":        {"desc": "20日简单移动平均，中期趋势", "params": {"period": {"type": "int", "min": 1, "max": 250, "default": 20, "step": 1}}},
    "MA30":        {"desc": "30日简单移动平均，中期趋势", "params": {"period": {"type": "int", "min": 1, "max": 250, "default": 30, "step": 1}}},
    "MA60":        {"desc": "60日简单移动平均，中长期趋势", "params": {"period": {"type": "int", "min": 1, "max": 250, "default": 60, "step": 1}}},
    "MA90":        {"desc": "90日简单移动平均，中长期趋势", "params": {"period": {"type": "int", "min": 1, "max": 250, "default": 90, "step": 1}}},
    "MA120":       {"desc": "120日简单移动平均，长期趋势", "params": {"period": {"type": "int", "min": 1, "max": 250, "default": 120, "step": 1}}},
    "MA250":       {"desc": "250日简单移动平均（年线），长期趋势", "params": {"period": {"type": "int", "min": 1, "max": 250, "default": 250, "step": 1}}},
    "RSI_6":       {"desc": "6日相对强弱指数，超短期超买超卖（>80超买，<20超卖）", "params": {"period": {"type": "int", "min": 2, "max": 24, "default": 6, "step": 1}}},
    "RSI_12":      {"desc": "12日相对强弱指数，短期超买超卖（>70超买，<30超卖）", "params": {"period": {"type": "int", "min": 2, "max": 24, "default": 12, "step": 1}}},
    "RSI_24":      {"desc": "24日相对强弱指数，中期超买超卖", "params": {"period": {"type": "int", "min": 2, "max": 24, "default": 24, "step": 1}}},
    "KDJ_K":       {"desc": "KDJ指标的K值（随机指标），>80超买，<20超卖", "params": {"period": {"type": "int", "min": 2, "max": 30, "default": 9, "step": 1}}},
    "KDJ_D":       {"desc": "KDJ指标的D值，K的移动平均，更平滑", "params": {"period": {"type": "int", "min": 2, "max": 30, "default": 3, "step": 1}}},
    "KDJ_J":       {"desc": "KDJ指标的J值，敏感度最高，可超过100或低于0", "params": {"period": {"type": "int", "min": 2, "max": 30, "default": 3, "step": 1}}},
    "MACD_DIF":    {"desc": "MACD快线（EMA快-慢差值），金叉/死叉判断趋势", "params": {"fast": {"type": "int", "min": 2, "max": 50, "default": 12, "step": 1}, "slow": {"type": "int", "min": 5, "max": 100, "default": 26, "step": 1}}},
    "MACD_DEA":    {"desc": "MACD信号线（DIF的EMA），与DIF交叉判断买卖点", "params": {"fast": {"type": "int", "min": 2, "max": 50, "default": 12, "step": 1}, "slow": {"type": "int", "min": 5, "max": 100, "default": 26, "step": 1}, "signal": {"type": "int", "min": 2, "max": 50, "default": 9, "step": 1}}},
    "MACD_HIST":   {"desc": "MACD柱状图（DIF-DEA×2），红柱多头，绿柱空头", "params": {"fast": {"type": "int", "min": 2, "max": 50, "default": 12, "step": 1}, "slow": {"type": "int", "min": 5, "max": 100, "default": 26, "step": 1}, "signal": {"type": "int", "min": 2, "max": 50, "default": 9, "step": 1}}},
    "BOLL_U":      {"desc": "布林带上轨（MA+2倍标准差），价格上穿可能回调", "params": {"period": {"type": "int", "min": 5, "max": 60, "default": 20, "step": 1}}},
    "BOLL_M":      {"desc": "布林带中轨（MA），作为中轴参考", "params": {"period": {"type": "int", "min": 5, "max": 60, "default": 20, "step": 1}}},
    "BOLL_L":      {"desc": "布林带下轨（MA-2倍标准差），价格下穿可能反弹", "params": {"period": {"type": "int", "min": 5, "max": 60, "default": 20, "step": 1}}},
    "ATR":         {"desc": "平均真实波幅，衡量价格波动剧烈程度", "params": {"period": {"type": "int", "min": 1, "max": 50, "default": 14, "step": 1}}},
    "ATR_7":       {"desc": "7日平均真实波幅，短期波动率", "params": {"period": {"type": "int", "min": 1, "max": 50, "default": 7, "step": 1}}},
    "ATR_21":      {"desc": "21日平均真实波幅，中期波动率", "params": {"period": {"type": "int", "min": 1, "max": 50, "default": 21, "step": 1}}},
    "VOL_RATIO":   {"desc": "量比（当日成交量/5日平均成交量），>1.5放量，<0.5缩量", "params": {"period": {"type": "int", "min": 1, "max": 20, "default": 5, "step": 1}}},
    "VOL_MA5":     {"desc": "5日均量，反映短期成交量平均水平", "params": {"period": {"type": "int", "min": 1, "max": 20, "default": 5, "step": 1}}},
    "VOL_MA10":    {"desc": "10日均量，反映中期成交量平均水平", "params": {"period": {"type": "int", "min": 1, "max": 60, "default": 10, "step": 1}}},
    "RETURN":      {"desc": "收益率（当日涨跌幅），正值为上涨，负值为下跌", "params": {"period": {"type": "int", "min": 1, "max": 20, "default": 1, "step": 1}}},
    "CLOSE_RATE_1":{"desc": "1日收益率，等同于RETURN", "params": {"period": {"type": "int", "min": 1, "max": 20, "default": 1, "step": 1}}},
    "CLOSE_RATE_3":{"desc": "3日收益率，短期趋势动量", "params": {"period": {"type": "int", "min": 1, "max": 20, "default": 3, "step": 1}}},
    "CLOSE_RATE_5":{"desc": "5日收益率，中短期动量", "params": {"period": {"type": "int", "min": 1, "max": 20, "default": 5, "step": 1}}},
    "MA20_DEVIATION":{"desc": "收盘价对20日均线的偏离度（正=在均线上方）", "params": {"ma_period": {"type": "int", "min": 5, "max": 250, "default": 20, "step": 1}}},
    "MA60_DEVIATION":{"desc": "收盘价对60日均线的偏离度", "params": {"ma_period": {"type": "int", "min": 5, "max": 250, "default": 60, "step": 1}}},
    "AMPLITUDE":   {"desc": "当日振幅（最高价-最低价）/最低价，反映日内波动", "params": {}},
    "MA5_GT_MA10":  {"desc": "布尔：MA5 > MA10（短期均线上穿中长期均线=多头信号）", "params": {}},
    "MA5_GT_MA20":  {"desc": "布尔：MA5 > MA20", "params": {}},
    "MA10_GT_MA20": {"desc": "布尔：MA10 > MA20", "params": {}},
    "MA5_GT_MA60":  {"desc": "布尔：MA5 > MA60", "params": {}},
    "MA20_GT_MA60": {"desc": "布尔：MA20 > MA60", "params": {}},
    "CLOSE_GT_MA5": {"desc": "布尔：收盘价 > MA5", "params": {}},
    "CLOSE_GT_MA10":{"desc": "布尔：收盘价 > MA10", "params": {}},
    "CLOSE_GT_MA20":{"desc": "布尔：收盘价 > MA20", "params": {}},
    "CLOSE_GT_MA60":{"desc": "布尔：收盘价 > MA60", "params": {}},
}


@app.get("/api/logic/builtin-indicators")
def list_builtin_indicators():
    """返回所有内置指标的元数据，供前端下拉选择"""
    return [
        {
            "name": name,
            "desc": BUILTIN_META.get(name, {}).get("desc", ""),
            "params": BUILTIN_META.get(name, {}).get("params", {}),
        }
        for name, *_ in BUILTIN_INDICATORS
    ]


# ============================================================================
# 回测功能
# ============================================================================

class BacktestRunRequest(BaseModel):
    formula_id: int
    stock_code: str
    start_date: str
    end_date: str
    initial_capital: float = 100000
    position_type: str = "percent_capital"  # percent_capital | fixed_amount
    position_value: float = 10  # 10% of capital or fixed amount
    stop_loss_type: str = "percent"  # percent | fixed
    stop_loss_value: float = -5  # -5%
    take_profit_type: str = "percent"
    take_profit_value: float = 15  # +15%
    entry_price_type: str = "open"  # open | close | avg


@app.post("/api/backtest/run")
def run_backtest(req: BacktestRunRequest, db: Session = Depends(get_db)):
    """运行回测"""
    from backtest_engine import run_backtest as engine_run_backtest
    import time
    start_time = time.time()

    result = engine_run_backtest(
        db=db,
        stock_code=req.stock_code,
        formula_id=req.formula_id,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        position_type=req.position_type,
        position_value=req.position_value,
        stop_loss_type=req.stop_loss_type,
        stop_loss_value=req.stop_loss_value,
        take_profit_type=req.take_profit_type,
        take_profit_value=req.take_profit_value,
        entry_price_type=req.entry_price_type
    )

    elapsed = time.time() - start_time

    if "error" in result:
        raise HTTPException(400, result["error"])

    # 保存结果到数据库
    result_json = {
        "config_id": req.formula_id,
        "stock_code": req.stock_code,
        "total_trades": result.get("total_trades", 0),
        "win_trades": result.get("win_trades", 0),
        "loss_trades": result.get("loss_trades", 0),
        "total_return": result.get("total_return", 0),
        "max_drawdown": result.get("max_drawdown", 0),
        "sharpe_ratio": result.get("sharpe_ratio", 0),
        "profit_factor": result.get("profit_factor", 0),
        "equity_curve": json.dumps(result.get("equity_curve", [])),
        "trade_log": json.dumps(result.get("trade_log", [])),
        "created_at": datetime.now().isoformat()
    }

    db.execute(text(
        """INSERT INTO backtest_results
           (config_id, stock_code, total_trades, win_trades, loss_trades,
            total_return, max_drawdown, sharpe_ratio, profit_factor,
            equity_curve, trade_log, created_at)
           VALUES (:config_id, :stock_code, :total_trades, :win_trades, :loss_trades,
                   :total_return, :max_drawdown, :sharpe_ratio, :profit_factor,
                   :equity_curve, :trade_log, :created_at)"""
    ), result_json)
    db.commit()

    result_id = db.execute(text("SELECT last_insert_rowid()")).fetchone()[0]

    return {
        "result_id": result_id,
        "elapsed_seconds": round(elapsed, 2),
        **result
    }


@app.get("/api/backtest/results/{result_id}")
def get_backtest_result(result_id: int, db: Session = Depends(get_db)):
    """获取回测结果"""
    row = db.execute(text(
        """SELECT id, config_id, stock_code, total_trades, win_trades, loss_trades,
                  total_return, max_drawdown, sharpe_ratio, profit_factor,
                  equity_curve, trade_log, created_at
           FROM backtest_results WHERE id=:id"""
    ), {"id": result_id}).fetchone()

    if not row:
        raise HTTPException(404, "Result not found")

    return {
        "id": row[0],
        "config_id": row[1],
        "stock_code": row[2],
        "total_trades": row[3],
        "win_trades": row[4],
        "loss_trades": row[5],
        "total_return": row[6],
        "max_drawdown": row[7],
        "sharpe_ratio": row[8],
        "profit_factor": row[9],
        "equity_curve": json.loads(row[10]) if row[10] else [],
        "trade_log": json.loads(row[11]) if row[11] else [],
        "created_at": row[12]
    }


@app.get("/api/backtest/recent")
def list_recent_backtest_results(db: Session = Depends(get_db), limit: int = 10):
    """列出最近的回测结果"""
    rows = db.execute(text(
        """SELECT id, config_id, stock_code, total_trades, total_return,
                  max_drawdown, win_trades, loss_trades, created_at
           FROM backtest_results ORDER BY created_at DESC LIMIT :limit"""
    ), {"limit": limit}).fetchall()

    return [
        {
            "id": r[0],
            "config_id": r[1],
            "stock_code": r[2],
            "total_trades": r[3],
            "total_return": r[4],
            "max_drawdown": r[5],
            "win_trades": r[6],
            "loss_trades": r[7],
            "created_at": r[8]
        }
        for r in rows
    ]


# ============================================================================
# 设置（test-connection 必须放在 {key} 之前）
# ============================================================================

@app.post("/api/settings/test-connection")
async def test_connection(req: TestConnectionRequest):
    """测试API连接是否可用"""
    import httpx
    try:
        headers = {"Authorization": f"Bearer {req.api_key}"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{req.api_base}/chat/completions",
                headers=headers,
                json={"model": req.model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            )
        if response.status_code == 200:
            return {"ok": True, "message": "连接成功 ✓"}
        else:
            return {"ok": False, "message": f"错误码: {response.status_code}"}
    except httpx.TimeoutException:
        return {"ok": False, "message": "连接超时：请检查网络或 API 地址"}
    except Exception as e:
        return {"ok": False, "message": f"连接失败: {str(e)}"}


@app.get("/api/settings")
def list_settings(db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text("SELECT key, value FROM settings")).fetchall()
    return {r[0]: r[1] for r in rows}


@app.get("/api/settings/{key}")
def get_setting(key: str, db: Session = Depends(get_db)):
    from sqlalchemy import text
    val = db.execute(text("SELECT value FROM settings WHERE key = :key"), {"key": key}).scalar()
    return {"key": key, "value": val}


@app.post("/api/settings/{key}")
def set_setting(key: str, req: SetSettingRequest, db: Session = Depends(get_db)):
    from sqlalchemy import text
    db.execute(text("INSERT OR REPLACE INTO settings (key, value) VALUES (:key, :value)"), {"key": key, "value": req.value})
    db.commit()
    return {"key": key, "value": req.value}


from starlette.responses import FileResponse, StreamingResponse
import os

# 挂载静态文件目录（必须在 SPA fallback 之前）
dist_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
if os.path.exists(dist_path):
    app.mount("/assets", StaticFiles(directory=dist_path + "/assets"), name="assets")

# SPA 路由兜底（必须放在所有 API 路由之后）

@app.get('/{path:path}')
async def spa_fallback(path: str):
    """"所有非 API 路径都返回 index.html，支持 Vue Router SPA 路由"""
    if path.startswith('api/') or path == 'api':
        raise HTTPException(404, "Not Found")
    dist_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
    index_path = os.path.join(dist_path, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(404, "index.html not found")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18080)