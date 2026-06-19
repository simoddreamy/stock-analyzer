"""
Stock Analyzer Playwright 自动化测试
使用 Python Playwright 直接测试前端界面
"""
import asyncio
import json
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Installing playwright...")
    import subprocess
    subprocess.run(["pip", "install", "playwright"], check=True)
    subprocess.run(["playwright", "install", "chromium"], check=False)  # Try anyway
    from playwright.async_api import async_playwright


class StockAnalyzerPlaywrightTest:
    def __init__(self):
        self.results = []
        self.browser = None
        self.context = None
        self.page = None
        
    def log(self, name, status, msg, details=None):
        self.results.append({
            "name": name,
            "status": status,
            "message": msg,
            "details": details
        })
        icon = "[PASS]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[WARN]" if status == "WARN" else "[ERROR]"
        print(f"{icon} {name}: {msg}")
        
    async def run(self):
        print("=" * 60)
        print("Stock Analyzer Playwright 自动化测试")
        print("=" * 60)
        
        async with async_playwright() as p:
            # 启动浏览器
            print("\n[1] 启动浏览器...")
            try:
                self.browser = await p.chromium.launch(headless=True)
                self.log("Browser Launch", "PASS", "浏览器启动成功")
            except Exception as e:
                self.log("Browser Launch", "FAIL", f"启动失败: {e}")
                return
            
            # 创建上下文和页面
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            
            # 监听控制台消息
            console_errors = []
            self.page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            
            # 访问应用
            print("\n[2] 访问 Stock Analyzer...")
            try:
                response = await self.page.goto("http://127.0.0.1:18080", timeout=30000)
                if response and response.ok:
                    self.log("Page Load", "PASS", f"页面加载成功 (状态码: {response.status})}")
                else:
                    self.log("Page Load", "FAIL", f"页面加载失败")
            except Exception as e:
                self.log("Page Load", "ERROR", f"加载异常: {e}")
                return
            
            # 等待页面加载完成
            print("\n[3] 等待页面渲染...")
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
                self.log("Page Wait", "PASS", "页面渲染完成")
            except Exception as e:
                self.log("Page Wait", "WARN", f"等待超时: {e}")
            
            # 获取页面信息
            print("\n[4] 获取页面信息...")
            try:
                title = await self.page.title()
                self.log("Page Title", "PASS", f"标题: {title}")
            except Exception as e:
                self.log("Page Title", "FAIL", f"获取失败: {e}")
            
            # 检查页面内容
            try:
                content = await self.page.content()
                if 'stock' in content.lower() or '股票' in content:
                    self.log("Page Content", "PASS", "页面包含股票相关内容")
                else:
                    self.log("Page Content", "WARN", "页面内容可能不完整")
            except Exception as e:
                self.log("Page Content", "FAIL", f"检查失败: {e}")
            
            # 检查导航元素
            print("\n[5] 检查界面元素...")
            try:
                nav_items = await self.page.query_selector_all("nav, .nav, [role=navigation]")
                self.log("Navigation", "PASS", f"找到 {len(nav_items)} 个导航元素")
            except Exception as e:
                self.log("Navigation", "FAIL", f"导航检查失败: {e}")
            
            # 检查股票列表
            try:
                stock_items = await self.page.query_selector_all("[class*=stock], [class*=item], tr, li")
                self.log("Stock List", "PASS", f"找到 {len(stock_items)} 个列表项")
            except Exception as e:
                self.log("Stock List", "FAIL", f"股票列表检查失败: {e}")
            
            # 截图
            print("\n[6] 截图...")
            try:
                screenshot_path = Path(__file__).parent / "playwright_screenshot.png"
                await self.page.screenshot(path=str(screenshot_path), full_page=True)
                self.log("Screenshot", "PASS", f"截图已保存: {screenshot_path}")
            except Exception as e:
                self.log("Screenshot", "FAIL", f"截图失败: {e}")
            
            # 检查控制台错误
            print("\n[7] 检查控制台错误...")
            if console_errors:
                self.log("Console Errors", "FAIL", f"发现 {len(console_errors)} 个错误")
                for i, err in enumerate(console_errors[:3], 1):
                    print(f"   Error {i}: {err[:100]}")
            else:
                self.log("Console Errors", "PASS", "无控制台错误")
            
            # 尝试交互
            print("\n[8] 测试交互...")
            try:
                # 尝试点击第一个股票
                first_stock = await self.page.query_selector("[class*=stock], tr, li")
                if first_stock:
                    await first_stock.click(timeout=5000)
                    self.log("Click Interaction", "PASS", "点击成功")
                else:
                    self.log("Click Interaction", "WARN", "未找到可点击元素")
            except Exception as e:
                self.log("Click Interaction", "WARN", f"点击失败: {e}")
            
            # 关闭浏览器
            await self.browser.close()
            
            # 打印结果
            self.print_summary()
            
    def print_summary(self):
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        warnings = sum(1 for r in self.results if r["status"] == "WARN")
        
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"警告: {warnings}")
        print("-" * 60)
        
        # 保存报告
        report_path = Path(__file__).parent / "playwright_test_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Stock Analyzer Playwright 测试报告\n\n")
            f.write("## 测试结果\n\n")
            f.write("| 测试项 | 状态 | 说明 |\n")
            f.write("|--------|------|------|\n")
            for r in self.results:
                f.write(f"| {r['name']} | {r['status']} | {r['message']} |\n")
            
            f.write("\n## 失败项详情\n\n")
            for r in self.results:
                if r["status"] in ["FAIL", "ERROR"]:
                    f.write(f"### {r['name']}\n")
                    f.write(f"- 状态: {r['status']}\n")
                    f.write(f"- 消息: {r['message']}\n")
                    if r['details']:
                        f.write(f"- 详情: {r['details']}\n")
                    f.write("\n")
        
        print(f"\n详细报告已保存到: {report_path}")
        print("=" * 60)


if __name__ == "__main__":
    test = StockAnalyzerPlaywrightTest()
    asyncio.run(test.run())
