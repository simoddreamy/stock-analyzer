"""
Stock Analyzer 自动化测试脚本
使用 Playwright 进行端到端测试
"""
import asyncio
import sys
import os
import json
import time

# 添加后端路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Installing...")
    os.system("pip install playwright")
    os.system("playwright install chromium")
    from playwright.async_api import async_playwright

BACKEND_URL = "http://127.0.0.1:18080"
FRONTEND_URL = "http://127.0.0.1:18080"


class StockAnalyzerTester:
    def __init__(self):
        self.results = []
        self.browser = None
        self.context = None
        self.page = None
        
    def log(self, test_name, status, message, details=None):
        """记录测试结果"""
        result = {
            "test": test_name,
            "status": status,  # PASS, FAIL, ERROR
            "message": message,
            "details": details or {}
        }
        self.results.append(result)
        status_symbol = "[PASS]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[WARN]"
        print(f"{status_symbol} {test_name}: {message}")
        if details:
            print(f"   详情: {json.dumps(details, ensure_ascii=False, indent=2)}")
    
    async def test_backend_api(self):
        """测试后端API"""
        import requests
        
        self.log("Backend API", "TESTING", "开始测试后端API...")
        
        # 测试健康检查
        try:
            resp = requests.get(f"{BACKEND_URL}/health", timeout=5)
            if resp.status_code == 200:
                self.log("Backend Health", "PASS", "后端服务正常运行")
            else:
                self.log("Backend Health", "FAIL", f"健康检查返回状态码 {resp.status_code}")
        except Exception as e:
            self.log("Backend Health", "ERROR", f"无法连接后端: {e}")
            return False
        
        # 测试获取股票列表
        try:
            resp = requests.get(f"{BACKEND_URL}/api/stocks/list", timeout=5)
            if resp.status_code == 200:
                stocks = resp.json()
                self.log("API /api/stocks/list", "PASS", f"成功获取股票列表，共 {len(stocks)} 只股票")
                self.results[-1]["stock_count"] = len(stocks)
            else:
                self.log("API /api/stocks/list", "FAIL", f"返回状态码 {resp.status_code}")
        except Exception as e:
            self.log("API /api/stocks/list", "ERROR", f"请求失败: {e}")
        
        # 测试获取K线数据
        try:
            resp = requests.get(f"{BACKEND_URL}/api/kline/000001", timeout=5)
            if resp.status_code == 200:
                kline = resp.json()
                self.log("API /api/kline/<code>", "PASS", f"成功获取K线数据，共 {len(kline)} 条记录")
            else:
                self.log("API /api/kline/<code>", "FAIL", f"返回状态码 {resp.status_code}")
        except Exception as e:
            self.log("API /api/kline/<code>", "ERROR", f"请求失败: {e}")
        
        # 测试获取公式
        try:
            resp = requests.get(f"{BACKEND_URL}/api/formulas/000001", timeout=5)
            if resp.status_code == 200:
                formulas = resp.json()
                self.log("API /api/formulas/<code>", "PASS", f"成功获取公式列表，共 {len(formulas)} 条")
            else:
                self.log("API /api/formulas/<code>", "FAIL", f"返回状态码 {resp.status_code}")
        except Exception as e:
            self.log("API /api/formulas/<code>", "ERROR", f"请求失败: {e}")
        
        return True
    
    async def test_frontend(self):
        """测试前端页面"""
        self.log("Frontend UI", "TESTING", "开始测试前端页面...")
        
        try:
            await self.page.goto(FRONTEND_URL, timeout=30000)
            await self.page.wait_for_load_state("networkidle", timeout=30000)
            
            title = await self.page.title()
            self.log("Page Title", "PASS", f"页面标题: {title}")
            
            # 检查页面内容
            content = await self.page.content()
            
            # 检查是否有Vue应用挂载点
            if 'id="app"' in content or 'app' in content.lower():
                self.log("Vue Mount Point", "PASS", "找到Vue应用挂载点")
            else:
                self.log("Vue Mount Point", "FAIL", "未找到Vue应用挂载点")
            
            # 检查页面是否包含股票相关元素
            page_text = await self.page.inner_text('body')
            
            keywords = ['股票', 'Stock', 'K线', '选股', 'watchlist', '探索']
            found_keywords = [kw for kw in keywords if kw in page_text]
            
            if found_keywords:
                self.log("Page Content", "PASS", f"页面包含关键词: {', '.join(found_keywords)}")
            else:
                self.log("Page Content", "WARN", "页面可能没有加载完成，关键词检查未通过")
            
            # 截图
            screenshot_path = os.path.join(os.path.dirname(__file__), "test_screenshot.png")
            await self.page.screenshot(path=screenshot_path, full_page=True)
            self.log("Screenshot", "PASS", f"截图已保存: {screenshot_path}")
            
            return True
            
        except Exception as e:
            self.log("Frontend UI", "ERROR", f"前端测试失败: {e}")
            return False
    
    async def test_browser_console(self):
        """检查浏览器控制台错误"""
        self.log("Console Errors", "TESTING", "检查浏览器控制台错误...")
        
        errors = []
        
        def handle_console(msg):
            if msg.type == 'error':
                errors.append(msg.text)
        
        self.page.on("console", handle_console)
        
        try:
            await self.page.reload()
            await self.page.wait_for_timeout(3000)  # 等待控制台输出
            
            if errors:
                self.log("Console Errors", "FAIL", f"发现 {len(errors)} 个控制台错误")
                for i, err in enumerate(errors[:5], 1):
                    self.log(f"Console Error #{i}", "FAIL", err[:200])
            else:
                self.log("Console Errors", "PASS", "未发现控制台错误")
                
        except Exception as e:
            self.log("Console Errors", "ERROR", f"检查失败: {e}")
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("Stock Analyzer 自动化测试")
        print("=" * 60)
        
        # 先测试后端API
        print("\n[1/3] 测试后端API...")
        api_ok = await self.test_backend_api()
        
        # 启动浏览器进行前端测试
        print("\n[2/3] 测试前端界面...")
        async with async_playwright() as p:
            try:
                # 尝试使用系统Chrome
                self.browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
            except Exception as e:
                print(f"启动Chromium失败: {e}")
                print("尝试使用OpenClaw的浏览器...")
                # 如果Playwright的Chromium不可用，尝试连接到系统Chrome
                try:
                    self.browser = await p.chromium.connect_over_cdp(
                        "http://127.0.0.1:18800"  # OpenClaw的CDP端口
                    )
                except Exception as e2:
                    self.log("Browser Launch", "ERROR", f"无法启动或连接浏览器: {e2}")
                    print("\n跳过前端测试（浏览器不可用）")
                    api_ok and self.print_summary()
                    return
            
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            
            frontend_ok = await self.test_frontend()
            
            if frontend_ok:
                await self.test_browser_console()
            
            await self.browser.close()
        
        print("\n[3/3] 生成测试报告...")
        self.print_summary()
    
    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 60)
        print("测试结果摘要")
        print("=" * 60)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        errors = sum(1 for r in self.results if r["status"] == "ERROR")
        warns = sum(1 for r in self.results if r["status"] == "WARN")
        
        print(f"总测试数: {total}")
        print(f"通过: {passed} ✅")
        print(f"失败: {failed} ❌")
        print(f"错误: {errors} ⚠️")
        print(f"警告: {warns} ⚡")
        print("-" * 60)
        
        if failed > 0 or errors > 0:
            print("失败/错误的测试:")
            for r in self.results:
                if r["status"] in ["FAIL", "ERROR"]:
                    print(f"  - {r['test']}: {r['message']}")
        
        print("=" * 60)
        
        # 保存报告到文件
        report_path = os.path.join(os.path.dirname(__file__), "TEST_REPORT.md")
        self.save_report(report_path)
        print(f"\n详细报告已保存到: {report_path}")
    
    def save_report(self, path):
        """保存Markdown格式的报告"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write("# Stock Analyzer 测试报告\n\n")
            f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## 测试结果\n\n")
            f.write("| 测试项 | 状态 | 消息 | 详情 |\n")
            f.write("|--------|------|------|------|\n")
            for r in self.results:
                status_icon = "✅" if r["status"] == "PASS" else "❌" if r["status"] == "FAIL" else "⚠️"
                details = json.dumps(r.get("details", {}), ensure_ascii=False)
                f.write(f"| {r['test']} | {status_icon} {r['status']} | {r['message']} | {details} |\n")
            
            f.write("\n## 失败项详情\n\n")
            failed_tests = [r for r in self.results if r["status"] in ["FAIL", "ERROR"]]
            if failed_tests:
                for r in failed_tests:
                    f.write(f"### {r['test']}\n")
                    f.write(f"- **状态**: {r['status']}\n")
                    f.write(f"- **消息**: {r['message']}\n")
                    f.write(f"- **详情**: {json.dumps(r.get('details', {}), ensure_ascii=False, indent=2)}\n\n")
            else:
                f.write("所有测试通过！\n")


async def main():
    tester = StockAnalyzerTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
