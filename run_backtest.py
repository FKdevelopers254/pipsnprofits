#!/usr/bin/env python3
"""
MT5 Backtesting Demo
Run backtests using real MT5 historical data
"""

import sys
import os
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.services.backtesting_engine import run_mt5_backtest, run_sample_backtest


def main():
    print("MT5 Quantum Trader - Backtesting with Real Data")
    print("=" * 60)
    
    # Test 1: Recent 3 months on H1
    print("\nTest 1: XAUUSD H1 - Last 3 Months")
    print("-" * 40)
    
    try:
        results1 = run_mt5_backtest(
            symbol="XAUUSD",
            timeframe="H1",
            start_date=datetime.now() - timedelta(days=90),
            end_date=datetime.now(),
            initial_balance=10000.0
        )
        
        print(f"Backtest completed successfully!")
        print(f"   Total Trades: {results1.total_trades}")
        print(f"   Win Rate: {results1.win_rate:.1f}%")
        print(f"   Net Profit: ${results1.net_profit:.2f}")
        print(f"   Data Source: {results1.data_source}")
        
    except Exception as e:
        print(f"Error in backtest 1: {e}")
    
    # Test 2: Recent 1 month on M15
    print("\nTest 2: XAUUSD M15 - Last Month")
    print("-" * 40)
    
    try:
        results2 = run_mt5_backtest(
            symbol="XAUUSD", 
            timeframe="M15",
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now(),
            initial_balance=5000.0
        )
        
        print(f"Backtest completed successfully!")
        print(f"   Total Trades: {results2.total_trades}")
        print(f"   Win Rate: {results2.win_rate:.1f}%")
        print(f"   Net Profit: ${results2.net_profit:.2f}")
        print(f"   Data Source: {results2.data_source}")
        
    except Exception as e:
        print(f"Error in backtest 2: {e}")
    
    # Test 3: Sample backtest (fallback)
    print("\nTest 3: Sample Backtest (Fallback)")
    print("-" * 40)
    
    try:
        results3 = run_sample_backtest()
        print(f"Sample backtest completed!")
        
    except Exception as e:
        print(f"Error in sample backtest: {e}")
    
    print("\nBacktesting Demo Complete!")
    print("Check 'backtest_results' folder for detailed JSON reports")


if __name__ == "__main__":
    main()
