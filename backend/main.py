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
from indicators.calculator import register_builtin_indicators, precompute_indicators_for_stock
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