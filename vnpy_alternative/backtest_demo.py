"""
Backtrader 快速回测示例 (简化版)
基于买点公式思路：MA5 MA10 MA20 金叉/死叉策略
"""
import backtrader as bt
import pandas as pd
import numpy as np
import datetime

# ========== 策略定义 ==========
class MA5MA10MA20CrossStrategy(bt.Strategy):
    """MA5 MA10 MA20 交叉策略"""
    
    params = (
        ('ma5_period', 5),
        ('ma10_period', 10),
        ('ma20_period', 20),
        ('printlog', False),  # 减少日志输出
    )
    
    def __init__(self):
        # 添加移动平均线指标
        self.ma5 = bt.indicators.SMA(self.data.close, period=self.params.ma5_period)
        self.ma10 = bt.indicators.SMA(self.data.close, period=self.params.ma10_period)
        self.ma20 = bt.indicators.SMA(self.data.close, period=self.params.ma20_period)
        
        # 交叉信号
        self.crossover = bt.indicators.CrossOver(self.ma5, self.ma10)
        
        # 追踪订单
        self.order = None
        
    def log(self, txt, dt=None, doprint=True):
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()} {txt}')
    
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'买入, 价格: {order.executed.price:.2f}')
            elif order.issell():
                self.log(f'卖出, 价格: {order.executed.price:.2f}')
        
        self.order = None
    
    def next(self):
        if self.order:
            return
        
        if not self.position:
            # 没有持仓: MA5上穿MA10 且 价格站上MA20 -> 买入
            if self.crossover > 0 and self.data.close[0] > self.ma20[0]:
                self.log(f'买入信号! 收盘:{self.data.close[0]:.2f} MA5:{self.ma5[0]:.2f} MA10:{self.ma10[0]:.2f}')
                self.order = self.buy()
        else:
            # 有持仓: MA5下穿MA10 -> 卖出
            if self.crossover < 0:
                self.log(f'卖出信号! 收盘:{self.data.close[0]:.2f} MA5:{self.ma5[0]:.2f} MA10:{self.ma10[0]:.2f}')
                self.order = self.sell()


def create_sample_data():
    """创建模拟股价数据"""
    dates = pd.date_range(start='2020-01-01', end='2024-12-31', freq='B')
    np.random.seed(42)
    
    price = 100
    prices = []
    for _ in range(len(dates)):
        price *= (1 + np.random.randn() * 0.015)
        prices.append(price)
    
    df = pd.DataFrame({
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': [np.random.randint(1000000, 10000000) for _ in prices]
    }, index=dates)
    
    return df


def run_backtest(initial_cash=100000):
    """运行回测"""
    
    # 创建Cerebro引擎
    cerebro = bt.Cerebro()
    
    # 使用模拟数据
    data = create_sample_data()
    data_feed = bt.feeds.PandasData(dataname=data)
    cerebro.adddata(data_feed)
    
    # 设置初始资金
    cerebro.broker.setcash(initial_cash)
    
    # 设置交易佣金 0.1%
    cerebro.broker.setcommission(commission=0.001)
    
    # 添加策略
    cerebro.addstrategy(MA5MA10MA20CrossStrategy, printlog=False)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    
    # 设置仓位（使用90%仓位）
    cerebro.addsizer(bt.sizers.PercentSizer, percents=90)
    
    print('=' * 50)
    print('Backtrader 回测演示')
    print('=' * 50)
    print(f'初始资金: {initial_cash:,.2f}')
    print(f'数据范围: 2020-01-01 至 2024-12-31')
    print(f'策略: MA5/MA10/MA20 金叉买入，死叉卖出')
    print(f'买入条件: MA5上穿MA10 且 价格>MA20')
    print(f'卖出条件: MA5下穿MA10')
    print('-' * 50)
    
    # 运行回测
    initial_value = cerebro.broker.getvalue()
    print(f'初始账户价值: {initial_value:,.2f}')
    
    results = cerebro.run()
    strat = results[0]
    
    final_value = cerebro.broker.getvalue()
    print(f'最终账户价值: {final_value:,.2f}')
    print(f'总收益: {((final_value - initial_cash) / initial_cash * 100):.2f}%')
    
    # 分析结果
    print('\n' + '=' * 50)
    print('回测分析报告')
    print('=' * 50)
    
    try:
        sharpe = strat.analyzers.sharpe.get_analysis()
        sharpe_ratio = sharpe.get('sharperatio')
        if sharpe_ratio is not None and not np.isnan(sharpe_ratio):
            print(f'夏普比率: {sharpe_ratio:.3f}')
        else:
            print('夏普比率: N/A')
    except:
        print('夏普比率: N/A')
    
    try:
        returns = strat.analyzers.returns.get_analysis()
        print(f'总收益率: {returns.get("rtot", 0) * 100:.2f}%')
        print(f'年化收益率: {returns.get("rnorm100", 0):.2f}%')
    except:
        pass
    
    try:
        drawdown = strat.analyzers.drawdown.get_analysis()
        max_dd = drawdown.get('max', {}).get('drawdown', 0)
        print(f'最大回撤: {max_dd:.2f}%')
    except:
        print('最大回撤: N/A')
    
    try:
        trades = strat.analyzers.trades.get_analysis()
        total_trades = trades.total.total if 'total' in trades.total else 0
        won_trades = trades.won.total if 'won' in trades.won else 0
        lost_trades = trades.lost.total if 'lost' in trades.lost else 0
        print(f'总交易次数: {total_trades}')
        if total_trades > 0:
            print(f'盈利交易: {won_trades}')
            print(f'亏损交易: {lost_trades}')
            print(f'胜率: {won_trades/total_trades*100:.1f}%')
    except:
        pass
    
    print('\n' + '=' * 50)
    print('回测完成!')
    print('=' * 50)
    
    return cerebro, final_value


if __name__ == '__main__':
    run_backtest()
