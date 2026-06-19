# Stock Analyzer - 股票买点公式探索工具

> **开发日期**: 2026-05-24 — 今日新增：K线悬停MA5显示、探索历史报告系统、手动公式覆盖

## 技术栈

- **前端**: Vue3 + Tauri (Windows)
- **后端**: Python FastAPI
- **数据库**: SQLite
- **图表**: ECharts
- **AI**: 第三方LLM API（用户配置）

## 项目结构

```
stock_analyzer/
├── backend/
│   ├── main.py              # FastAPI主入口
│   ├── db/
│   │   └── database.py      # 数据库连接与Schema
│   ├── data_fetcher/
│   │   └── fetcher.py       # AKShare/Baostock数据获取
│   ├── indicators/
│   │   └── calculator.py    # 技术指标计算
│   └── explorer/
│       └── engine.py         # AI探索引擎
├── frontend/
│   ├── src/
│   │   ├── App.vue          # 根组件 + 导航
│   │   ├── views/
│   │   │   ├── StocksView.vue   # 股票窗口
│   │   │   ├── ExploreView.vue  # 探索配置
│   │   │   └── SettingsView.vue # 设置页
│   │   └── router.js
│   └── package.json
└── README.md
```

## 快速开始

### 1. 环境要求

- Node.js 18+
- Python 3.10+
- Rust（用于Tauri构建）

### 2. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

### 4. 初始化数据库

```bash
cd backend
python -c "from db.database import create_tables; create_tables()"
python -c "from indicators.calculator import register_builtin_indicators; from db.database import SessionLocal; db = SessionLocal(); register_builtin_indicators(db); db.close()"
```

### 5. 开发模式运行

```bash
# 终端1: 启动后端
cd backend
uvicorn main:app --reload --port 18080

# 终端2: 启动前端(Tauri开发模式)
cd frontend
npm run tauri dev
```

### 6. 生产构建

```bash
cd frontend
npm run tauri build
```

## 核心功能

1. **股票管理**: 添加/导入/删除自选股
2. **数据同步**: 一键将所有股票数据同步到最近交易日（增量拉取）
3. **U1买点定义**: 用户配置买点条件（买入价/持有天数/盈利目标）
4. **AI公式探索**: 三段验证法探索优选公式（10分钟/股）
5. **K线图标注**: 在K线图上同时标注U1合格买点和公式候选买点
6. **批量探索**: 多只股票批量探索
7. **K线悬停MA5**: 鼠标移到K线柱上时，详细信息显示当天5日均线价格（金色）
8. **探索历史报告**: 探索完成后自动保存报告到数据库；股票窗口可查看该股所有历史探索记录
9. **手动公式覆盖**: 可在股票窗口手动设置公式，Override AI探索结果

## 数据库表

| 表名 | 说明 |
|------|------|
| `watchlist` | 自选股列表 |
| `daily_kline` | 日K线数据 |
| `best_formulas` | 各股最优公式 |
| `formula_overrides` | 用户手动覆盖的公式（优先级高于best_formulas）|
| `exploration_reports` | 探索历史报告（探索时自动写入）|

## 2026-05-24 今日进展

### Bug Fixes
- 静态文件挂载路径错误导致资源404
- API路径不匹配（前端vs后端）
- `set_setting`接口422参数错误
- Baostock日期格式（YYYYMMDD vs YYYY-MM-DD）
- `rs.logout()`在读取数据前被调用导致数据为空
- while循环位运算符`&`误用为逻辑`and`
- Tauri invoke混用（应走HTTP API）
- 探索状态轮询API返回即时报错被静默吞掉
- `let`声明提升问题导致timer启动失败
- 双重`.json()`解析导致轮询全部失败
- K线图空白（旧进程占用端口）
- 买点/机会点MarkPoint坐标重叠

### 新功能
- **MA5悬停**: tooltip显示5日均线（金色）
- **探索历史报告**: 探索完成后写入`exploration_reports`表；股票窗口点击"历史报告"查看该股历史
- **手动公式覆盖**: 股票窗口"设置公式"按钮，支持手动配置公式覆盖AI结果

### 数据库变更
```sql
-- 新增表
CREATE TABLE exploration_reports (
  id INTEGER PRIMARY KEY,
  session_id INTEGER, code TEXT, status TEXT,
  total_seconds INTEGER, candidates_total INTEGER,
  segments_data TEXT, best_formula TEXT,
  best_precision REAL, best_coverage INTEGER,
  iterations INTEGER, final_message TEXT,
  created_at TEXT
);

CREATE TABLE formula_overrides (
  code TEXT PRIMARY KEY, formula_expr TEXT,
  logic_desc TEXT, a1 REAL, a2 REAL, a3 REAL,
  updated_at TEXT
);

-- exploration_reports表支持按股票代码过滤查询
```

### API变更（新增）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/explore/reports?code=` | 查询探索历史（支持按股票过滤）|
| GET | `/api/explore/reports/{id}` | 单条报告详情 |
| PUT | `/api/formulas/{code}/override` | 保存手动公式覆盖 |
| GET | `/api/formulas/{code}/override` | 获取手动公式覆盖 |

## 界面说明

- **股票窗口**: 左侧股票列表 + 右侧K线图和优选公式
- **探索配置**: 选择股票，配置U1参数，启动探索
- **设置**: API Key配置，数据源配置
- **底部状态栏**: 数据同步按钮

## 数据说明

- 仅支持深圳主板（000/001/002/003开头）
- K线周期：日K
- 数据来源：AKShare（主）+ Baostock（备）