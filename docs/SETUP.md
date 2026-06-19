# Stock Analyzer - 环境安装与打包指南

## 目录

1. [环境要求](#环境要求)
2. [开发环境安装](#开发环境安装)
3. [生产构建](#生产构建)
4. [打包为安装包](#打包为安装包)
5. [安装与运行](#安装与运行)

---

## 环境要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Node.js | 18.x | 前端构建 |
| Python | 3.10+ | 后端服务 |
| Rust | 1.70+ | Tauri编译 |
| Git | 2.x | 版本控制 |

---

## 开发环境安装

### 1. 检查环境

```powershell
node --version    # >= 18
python --version  # >= 3.10
rustc --version   # >= 1.70
cargo --version   # >= 1.70
```

### 2. 安装 Python 依赖

```powershell
cd stock_analyzer/backend
pip install -r requirements.txt
```

主要依赖：
- `akshare` - 股票数据获取（主数据源）
- `baostock` - 股票数据获取（备用数据源）
- `fastapi` - 后端API框架
- `uvicorn` - ASGI服务器
- `sqlalchemy` - ORM
- `pandas` - 数据处理
- `numpy` - 数值计算

### 3. 初始化数据库

```powershell
cd stock_analyzer/backend
python -c "from db.database import create_tables; create_tables()"
python -c "from indicators.calculator import register_builtin_indicators; from db.database import SessionLocal; db = SessionLocal(); register_builtin_indicators(db); db.close()"
```

### 4. 安装 Node.js 依赖

```powershell
cd stock_analyzer/frontend
npm install
```

### 5. 配置 Python 后端服务地址

前端默认连接 `http://127.0.0.1:18080`。开发时需要先启动后端：

```powershell
cd stock_analyzer/backend
uvicorn main:app --host 127.0.0.1 --port 18080 --reload
```

### 6. 启动开发模式

```powershell
cd stock_analyzer/frontend
npm run tauri dev
```

---

## 生产构建

### 方式一：一键构建（推荐）

Windows PowerShell：

```powershell
cd stock_analyzer
.\build.ps1
```

### 方式二：手动分步构建

**Step 1: 构建前端**

```powershell
cd stock_analyzer/frontend
npm run build
```

**Step 2: 打包Tauri应用**

```powershell
cd stock_analyzer/frontend
npm run tauri build
```

构建产物在 `frontend/src-tauri/target/release/` 目录下。

---

## 打包为安装包

Tauri默认使用NSIS生成Windows安装包（`.exe`）。

### 安装包内容

- `StockAnalyzer_x.x.x_x64-setup.exe` - NSIS安装包
- `StockAnalyzer_x.x.x_x64.msi` - MSI安装包（如已配置）

### 自定义安装包

编辑 `src-tauri/tauri.conf.json` 中的 `bundle.windows.nsis` 部分：

```json
{
  "bundle": {
    "windows": {
      "nsis": {
        "languages": ["SimpChinese", "English"],
        "displayLanguageSelector": true,
        "installerIcon": "icons/icon.ico",
        "installMode": "currentUser"
      }
    }
  }
}
```

| 配置项 | 说明 |
|--------|------|
| `languages` | 安装界面语言 |
| `displayLanguageSelector` | 允许用户选择语言 |
| `installerIcon` | 安装包图标 |
| `installMode` | `currentUser`（当前用户）或`perMachine`（所有用户） |

### 安装包签名

如需代码签名，在 `tauri.conf.json` 配置：

```json
{
  "bundle": {
    "windows": {
      "certificateThumbprint": "你的证书指纹",
      "timestampUrl": "http://timestamp.digicert.com"
    }
  }
}
```

---

## 安装与运行

### 安装

1. 双击 `StockAnalyzer_x.x.x_x64-setup.exe`
2. 选择安装语言（简体中文/English）
3. 选择安装位置（默认 `C:\Users\<用户名>\AppData\Local\Programs\StockAnalyzer`）
4. 选择开始菜单文件夹
5. 点击"安装"

### 首次运行

1. 启动应用后，前往**设置**页面
2. 填入你的AI模型API Key和API地址
3. 选择数据源
4. 在**股票窗口**添加自选股
5. 点击底部**数据同步**按钮拉取K线数据
6. 在**探索配置**页面设置U1参数并开始探索

### 卸载

- 通过Windows设置 → 应用和功能 → Stock Analyzer → 卸载
- 或在安装目录下运行 `uninstall.exe`

---

## 目录结构（安装后）

```
StockAnalyzer/
├── StockAnalyzer.exe      # 主程序
├── resources/
│   └── data/
│       └── stock_analyzer.db  # SQLite数据库
├── logs/                  # 日志文件（如有）
└── uninstall.exe          # 卸载程序
```

---

## 常见问题

### Q: Rust编译报错 "linker `link.exe` not found"

需要安装Visual Studio Build Tools，包含Windows SDK和C++编译工具链。

### Q: AKShare获取数据失败

可能是网络问题或API限流，程序会自动切换到Baostock备源。

### Q: 打包后运行时数据库路径错误

确保数据库路径使用 `Path::new(env::current_exe()).parent()` 而非硬编码路径。

### Q: 安装包被Windows SmartScreen拦截

这是正常现象，个人开发的应用未签名。点击"仍要运行"即可，或配置代码签名证书。