# 🧠 Reinforcement Learning Trading System

## Overview

This Reinforcement Learning (RL) system transforms your MT5 trading bot from rule-based to intelligence-based trading. The system uses Deep Q-Networks (DQN) to learn optimal trading strategies through experience.

## 🚀 Features

### **Core RL Components**
- **Deep Q-Network (DQN)**: Neural network for trading decisions
- **Experience Replay**: Memory buffer for efficient learning
- **Trading Environment**: Simulated trading environment
- **Reward System**: Sophisticated reward calculation
- **State Representation**: Comprehensive market state vectors

### **Advanced Capabilities**
- **Self-Improving**: Bot learns from every trade
- **Adaptive Strategy**: Adjusts to market conditions
- **Risk-Aware**: Considers drawdown and volatility
- **Multi-Objective**: Optimizes profit, risk, and consistency
- **Real-Time Learning**: Continuous fine-tuning during live trading

## 📁 File Structure

```
src/services/
├── rl_trader.py          # Main RL trading system
├── rl_agent.py           # Deep Q-Network agent
├── rl_environment.py     # Trading environment
├── rl_memory.py          # Experience replay buffer
├── rl_rewards.py         # Reward calculation system
└── rl_state.py          # State representation

src/routers/
└── rl_router.py         # RL API endpoints

src/static/js/
└── rl-dashboard.js      # RL dashboard UI

models/                 # Saved RL models
```

## 🎯 How It Works

### **1. State Representation**
The RL agent observes:
- **Price Action**: OHLCV data with multiple lookback periods
- **Technical Indicators**: RSI, MACD, Bollinger Bands, Moving Averages
- **Portfolio Status**: Positions, P&L, drawdown, win rate
- **Market Conditions**: Volatility, spread, trading session
- **Time Features**: Hour, day, month (cyclical encoding)

### **2. Action Space**
The agent can take 5 actions:
- **HOLD**: Do nothing
- **BUY**: Open long position
- **SELL**: Open short position
- **CLOSE_LONG**: Close long position
- **CLOSE_SHORT**: Close short position

### **3. Reward System**
Multi-component reward calculation:
- **Base P&L**: Profit/loss scaled by account size
- **Risk Adjustment**: Penalty for high drawdown
- **Transaction Costs**: Spread and commission penalties
- **Time Bonus**: Optimal trade duration rewards
- **Streak Bonus**: Consecutive wins/losses
- **Volatility Adjustment**: Risk-adjusted returns

### **4. Learning Process**
1. **Exploration**: Agent tries random actions (epsilon-greedy)
2. **Experience Storage**: State-action-reward transitions stored
3. **Neural Network Training**: Batch training on stored experiences
4. **Target Network Updates**: Stabilizes learning
5. **Policy Improvement**: Agent becomes smarter over time

## 🛠️ Installation

### **1. Install Dependencies**
```bash
pip install -r requirements.txt
```

### **2. Install PyTorch (if not installed)**
```bash
# For CPU
pip install torch torchvision

# For GPU (CUDA)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### **3. Verify Installation**
```bash
python -c "import torch; print('PyTorch version:', torch.__version__)"
```

## 🎮 Usage

### **1. Start the Server**
```bash
cd src
python main.py
```

### **2. Access RL Dashboard**
Open: `http://127.0.0.1:5100`

Scroll down to the **🧠 Reinforcement Learning Trading** section.

### **3. Initialize RL System**
1. Select Symbol (XAUUSD, EURUSD, GBPUSD)
2. Select Timeframe (M1, M5, M15, H1, H4, D1)
3. Click **Initialize RL System**

### **4. Train the Agent**
1. Set Training Episodes (default: 100)
2. Adjust Learning Rate (default: 0.001)
3. Set Epsilon (default: 1.0)
4. Click **Start Training**

### **5. Live Trading**
1. Set Decision Interval (default: 5 minutes)
2. Set Confidence Threshold (default: 0.7)
3. Click **Start Live**

## 📊 Training Process

### **Phase 1: Exploration (High Epsilon)**
- Agent takes random actions
- Learns basic market dynamics
- Builds experience buffer

### **Phase 2: Exploitation (Low Epsilon)**
- Agent uses learned knowledge
- Refines trading strategy
- Improves decision quality

### **Phase 3: Fine-Tuning**
- Minimal exploration
- Policy optimization
- Performance stabilization

## 🎯 Performance Metrics

### **Training Metrics**
- **Episode Rewards**: Learning progress
- **Average Loss**: Network convergence
- **Epsilon Decay**: Exploration rate
- **Training Steps**: Total iterations

### **Trading Metrics**
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross wins / gross losses
- **Sharpe Ratio**: Risk-adjusted returns
- **Max Drawdown**: Largest loss peak
- **Consecutive Wins/Losses**: Streak tracking

### **Evaluation Metrics**
- **Evaluation Score**: Composite performance measure
- **Sample Efficiency**: Learning speed
- **Stability**: Consistency across episodes

## 🔧 Configuration

### **Hyperparameters**
```python
# Agent Configuration
learning_rate = 0.001      # Learning rate
gamma = 0.95               # Future reward discount
epsilon = 1.0              # Initial exploration rate
epsilon_min = 0.01         # Minimum exploration rate
epsilon_decay = 0.995      # Exploration decay

# Network Architecture
state_size = 50             # Input features
action_size = 5             # Possible actions
hidden_size = 128           # Hidden layer size

# Training Parameters
batch_size = 32             # Training batch size
memory_size = 10000         # Experience buffer size
target_update_freq = 1000   # Target network update frequency
```

### **Reward Weights**
```python
# Reward Components
profit_weight = 0.4         # Profit maximization
risk_weight = 0.3           # Risk minimization
consistency_weight = 0.2     # Consistency preference
efficiency_weight = 0.1      # Trading efficiency
```

## 🚀 Advanced Features

### **1. Multi-Agent System**
- Multiple specialized agents
- Ensemble decision making
- Strategy diversification

### **2. Transfer Learning**
- Apply learned patterns to new symbols
- Faster adaptation
- Knowledge sharing

### **3. Explainable AI**
- Feature importance analysis
- Decision interpretation
- Transparency tools

### **4. Continuous Learning**
- Real-time fine-tuning
- Market adaptation
- Performance optimization

## 📈 Expected Results

### **Short Term (1-2 weeks)**
- Basic market understanding
- Improved decision consistency
- Reduced random trading

### **Medium Term (1-2 months)**
- Developed trading patterns
- Risk-aware decisions
- Stable performance

### **Long Term (3-6 months)**
- Self-optimizing strategies
- Market regime adaptation
- Competitive edge

## ⚠️ Risk Management

### **Built-in Safety**
- **Position Limits**: Maximum open positions
- **Drawdown Protection**: Automatic stop at high drawdown
- **Confidence Threshold**: Only high-confidence trades
- **Risk-Adjusted Rewards**: Penalizes risky behavior

### **Recommended Settings**
- **Start Small**: Low position sizes
- **Paper Trading**: Test before live trading
- **Monitor Performance**: Regular evaluation
- **Adjust Parameters**: Optimize for your style

## 🔍 Troubleshooting

### **Common Issues**

#### **1. Training Not Converging**
- Lower learning rate
- Increase network size
- Check reward function
- Verify state representation

#### **2. Overfitting**
- Add dropout layers
- Increase regularization
- Use early stopping
- Expand training data

#### **3. Poor Live Performance**
- Increase confidence threshold
- Check market regime
- Verify transaction costs
- Update reward weights

#### **4. Memory Issues**
- Reduce buffer size
- Decrease batch size
- Use gradient checkpointing
- Clear GPU cache

### **Debug Tools**
```python
# Get training statistics
stats = rl_trader.get_performance_stats()
print(stats)

# Analyze decisions
decisions = await get_recent_decisions()
print(decisions)

# Evaluate model
score = await evaluate_model(episodes=10)
print(f"Evaluation Score: {score}")
```

## 📚 Resources

### **Papers**
- [Deep Q-Networks](https://arxiv.org/abs/1312.5602)
- [Double DQN](https://arxiv.org/abs/1509.06461)
- [Prioritized Experience Replay](https://arxiv.org/abs/1511.05952)

### **Libraries**
- [Stable Baselines3](https://stable-baselines3.readthedocs.io/)
- [Gymnasium](https://gymnasium.farama.org/)
- [PyTorch](https://pytorch.org/)

### **Communities**
- [RL Discord](https://discord.gg/reinforcement-learning)
- [Reddit r/reinforcementlearning](https://reddit.com/r/reinforcementlearning)

## 🤝 Contributing

### **Development Setup**
```bash
git clone <repository>
cd mt5bot
pip install -r requirements.txt
python src/main.py
```

### **Code Style**
```bash
black src/
flake8 src/
mypy src/
```

### **Testing**
```bash
pytest tests/
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs
3. Create an issue with details
4. Join the community Discord

---

**🚀 Ready to transform your trading with AI? Start training your RL agent today!**
