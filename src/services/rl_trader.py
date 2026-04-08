"""
Main Reinforcement Learning Trading System
Integrates RL agent, environment, and training
"""

import asyncio
import torch
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
import json
import os

from src.services.rl_agent import DQNAgent
from src.services.rl_environment import TradingEnvironment
from src.services.rl_memory import ExperienceReplay
from src.services.rl_rewards import RewardCalculator, MultiObjectiveRewardCalculator
from src.services.mt5_service import mt5_manager

logger = logging.getLogger(__name__)

class ReinforcementLearningTrader:
    """Main RL Trading System"""
    
    def __init__(
        self,
        symbol: str = "XAUUSD",
        timeframe: str = "H1",
        model_path: Optional[str] = None,
        training_mode: bool = True,
        save_interval: int = 100,
        evaluation_interval: int = 50
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.model_path = model_path
        self.training_mode = training_mode
        self.save_interval = save_interval
        self.evaluation_interval = evaluation_interval
        
        # Initialize components
        self.environment = TradingEnvironment(symbol=symbol, timeframe=timeframe)
        self.agent = DQNAgent(
            state_size=self.environment.state_size,
            action_size=self.environment.action_size,
            learning_rate=0.001,
            gamma=0.95,
            epsilon=1.0 if training_mode else 0.01,
            epsilon_min=0.01 if training_mode else 0.001,
            epsilon_decay=0.995 if training_mode else 1.0
        )
        self.memory = ExperienceReplay(
            capacity=10000,
            batch_size=32,
            min_experiences=1000
        )
        self.reward_calculator = RewardCalculator()
        
        # Training state
        self.current_episode = 0
        self.total_episodes = 1000
        self.max_steps_per_episode = 1000
        self.training_step = 0
        
        # Performance tracking
        self.episode_rewards = []
        self.episode_lengths = []
        self.evaluation_scores = []
        self.best_evaluation_score = -999999.0
        
        # Live trading state
        self.is_running = False
        self.last_decision_time = None
        self.decision_interval = timedelta(minutes=5)  # Make decision every 5 minutes
        
        # Statistics
        self.training_stats = {
            'total_steps': 0,
            'total_rewards': 0.0,
            'avg_reward': 0.0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0
        }
        
        logger.info(f"RL Trader initialized for {symbol} {timeframe}")
        logger.info(f"Training mode: {training_mode}")
        
        # Load model if available
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
    
    async def train(self, num_episodes: int = 1000) -> Dict[str, Any]:
        """Train the RL agent"""
        
        logger.info(f"Starting RL training for {num_episodes} episodes")
        self.total_episodes = num_episodes
        
        training_start = datetime.now()
        
        for episode in range(num_episodes):
            self.current_episode = episode
            
            # Reset environment
            state = self.environment.reset()
            episode_reward = 0.0
            episode_steps = 0
            
            logger.info(f"Episode {episode + 1}/{num_episodes} started")
            
            # Episode loop
            while episode_steps < self.max_steps_per_episode:
                # Choose action
                action = self.agent.act(state, training=True)
                
                # Execute action
                next_state, reward, done, info = self.environment.step(action)
                
                # Store experience
                self.memory.add_experience(
                    state=state,
                    action=action,
                    reward=reward,
                    next_state=next_state,
                    done=done
                )
                
                # Update state and reward
                state = next_state
                episode_reward += reward
                episode_steps += 1
                self.training_step += 1
                
                # Train agent if memory is ready
                if self.memory.is_ready():
                    experiences = self.memory.sample()
                    loss = self.agent.replay(experiences)
                    
                    # Update priorities based on TD errors
                    if hasattr(self.agent, 'last_td_errors'):
                        indices = [self.memory.buffer.index(exp) for exp in experiences]
                        self.memory.update_priorities(indices, self.agent.last_td_errors)
                
                # Episode done
                if done:
                    break
            
            # Episode completed
            self.episode_rewards.append(episode_reward)
            self.episode_lengths.append(episode_steps)
            
            # Decay epsilon
            self.agent.decay_epsilon()
            
            # Log progress
            if (episode + 1) % 10 == 0:
                avg_reward = np.mean(self.episode_rewards[-10:])
                logger.info(f"Episode {episode + 1}: Avg reward (last 10): {avg_reward:.4f}")
                logger.info(f"Epsilon: {self.agent.epsilon:.4f}")
            
            # Save model periodically
            if (episode + 1) % self.save_interval == 0:
                self.save_model()
            
            # Evaluate agent
            if (episode + 1) % self.evaluation_interval == 0:
                evaluation_score = await self.evaluate_agent(num_episodes=5)
                self.evaluation_scores.append(evaluation_score)
                
                if evaluation_score > self.best_evaluation_score:
                    self.best_evaluation_score = evaluation_score
                    logger.info(f"New best evaluation score: {evaluation_score:.4f}")
                    self.save_model(f"best_model_{self.symbol}_{self.timeframe}.pth")
        
        training_end = datetime.now()
        training_duration = training_end - training_start
        
        # Final model save
        self.save_model()
        
        # Training summary
        summary = self._get_training_summary(training_duration)
        logger.info(f"Training completed in {training_duration}")
        logger.info(f"Final evaluation score: {self.evaluation_scores[-1] if self.evaluation_scores else 0:.4f}")
        
        return summary
    
    async def evaluate_agent(self, num_episodes: int = 10) -> float:
        """Evaluate agent performance"""
        
        logger.info(f"Evaluating agent for {num_episodes} episodes")
        
        # Set agent to evaluation mode (no exploration)
        original_epsilon = self.agent.epsilon
        self.agent.epsilon = 0.0
        
        evaluation_rewards = []
        evaluation_steps = []
        
        for episode in range(num_episodes):
            state = self.environment.reset()
            episode_reward = 0.0
            episode_steps = 0
            
            while episode_steps < self.max_steps_per_episode:
                # Choose action (no exploration)
                action = self.agent.act(state, training=False)
                
                # Execute action
                next_state, reward, done, info = self.environment.step(action)
                
                state = next_state
                episode_reward += reward
                episode_steps += 1
                
                if done:
                    break
            
            evaluation_rewards.append(episode_reward)
            evaluation_steps.append(episode_steps)
        
        # Restore original epsilon
        self.agent.epsilon = original_epsilon
        
        # Calculate evaluation score
        avg_reward = np.mean(evaluation_rewards)
        std_reward = np.std(evaluation_rewards)
        
        # Composite score (average reward with penalty for high variance)
        evaluation_score = avg_reward - 0.1 * std_reward
        
        logger.info(f"Evaluation completed: Avg reward = {avg_reward:.4f}, Std = {std_reward:.4f}")
        
        return evaluation_score
    
    async def start_live_trading(self):
        """Start live trading with RL agent"""
        
        if not self.training_mode:
            logger.info("Starting live trading with RL agent")
        
        self.is_running = True
        self.last_decision_time = datetime.now()
        
        try:
            while self.is_running:
                current_time = datetime.now()
                
                # Check if it's time to make a decision
                if current_time - self.last_decision_time >= self.decision_interval:
                    await self._make_trading_decision()
                    self.last_decision_time = current_time
                
                # Small delay to prevent excessive CPU usage
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in live trading loop: {e}")
        finally:
            self.is_running = False
            logger.info("Live trading stopped")
    
    async def _make_trading_decision(self):
        """Make trading decision using RL agent"""
        
        try:
            # Get current state
            state = self.environment._get_current_state()
            
            # Get action from agent
            action = self.agent.act(state, training=False)
            
            # Get action confidence
            confidence = self.agent.get_action_confidence(state)[1]
            
            # Only execute if confidence is high enough
            if confidence > 0.7:
                action_name = self.environment.action_map[action]
                
                logger.info(f"RL Decision: {action_name} (confidence: {confidence:.3f})")
                
                # Execute action through environment
                next_state, reward, done, info = self.environment.step(action)
                
                # Store experience for continuous learning
                self.memory.add_experience(
                    state=state,
                    action=action,
                    reward=reward,
                    next_state=next_state,
                    done=done
                )
                
                # Log result
                logger.info(f"Action result: reward={reward:.4f}, done={done}")
                
                # Continuous learning (fine-tuning)
                if self.memory.is_ready() and self.training_step % 10 == 0:
                    experiences = self.memory.sample(batch_size=16)
                    self.agent.replay(experiences)
                
                self.training_step += 1
            else:
                logger.debug(f"RL Decision: HOLD (confidence too low: {confidence:.3f})")
                
        except Exception as e:
            logger.error(f"Error making trading decision: {e}")
    
    def stop_live_trading(self):
        """Stop live trading"""
        self.is_running = False
        logger.info("Live trading stop requested")
    
    def save_model(self, filepath: Optional[str] = None):
        """Save RL model and training state"""
        
        if not filepath:
            filepath = f"rl_model_{self.symbol}_{self.timeframe}.pth"
        
        try:
            # Save agent model
            self.agent.save_model(filepath)
            
            # Save training data
            training_data = {
                'episode_rewards': self.episode_rewards,
                'episode_lengths': self.episode_lengths,
                'evaluation_scores': self.evaluation_scores,
                'best_evaluation_score': self.best_evaluation_score,
                'training_stats': self.training_stats,
                'current_episode': self.current_episode,
                'total_episodes': self.total_episodes,
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'timestamp': datetime.now().isoformat()
            }
            
            training_filepath = filepath.replace('.pth', '_training.json')
            with open(training_filepath, 'w') as f:
                json.dump(training_data, f, indent=2)
            
            # Save experience replay buffer
            if self.memory.save_path:
                self.memory.save_buffer()
            
            logger.info(f"Model and training data saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
    
    def load_model(self, filepath: str):
        """Load RL model and training state"""
        
        try:
            # Load agent model
            self.agent.load_model(filepath)
            
            # Load training data
            training_filepath = filepath.replace('.pth', '_training.json')
            if os.path.exists(training_filepath):
                with open(training_filepath, 'r') as f:
                    training_data = json.load(f)
                
                self.episode_rewards = training_data.get('episode_rewards', [])
                self.episode_lengths = training_data.get('episode_lengths', [])
                self.evaluation_scores = training_data.get('evaluation_scores', [])
                self.best_evaluation_score = training_data.get('best_evaluation_score', float('-inf'))
                self.training_stats = training_data.get('training_stats', {})
                self.current_episode = training_data.get('current_episode', 0)
                
                logger.info(f"Training data loaded from {training_filepath}")
            
            # Load experience replay buffer
            if self.memory.save_path:
                buffer_filepath = filepath.replace('.pth', '_buffer.pkl')
                if os.path.exists(buffer_filepath):
                    self.memory.load_buffer(buffer_filepath)
            
            logger.info(f"Model loaded from {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        
        # Environment stats
        env_stats = self.environment.get_stats()
        
        # Agent stats
        agent_stats = self.agent.get_training_stats()
        
        # Memory stats
        memory_stats = self.memory.get_stats()
        
        # Reward stats
        reward_stats = self.reward_calculator.get_reward_statistics()
        
        # Combined stats
        combined_stats = {
            'environment': env_stats,
            'agent': agent_stats,
            'memory': memory_stats,
            'rewards': reward_stats,
            'training': {
                'current_episode': self.current_episode,
                'total_episodes': self.total_episodes,
                'episode_rewards': self.episode_rewards,
                'episode_lengths': self.episode_lengths,
                'evaluation_scores': self.evaluation_scores,
                'best_evaluation_score': self.best_evaluation_score,
                'avg_episode_reward': np.mean(self.episode_rewards) if self.episode_rewards else 0.0,
                'avg_episode_length': np.mean(self.episode_lengths) if self.episode_lengths else 0.0,
                'recent_performance': self.episode_rewards[-10:] if len(self.episode_rewards) >= 10 else self.episode_rewards
            },
            'live_trading': {
                'is_running': self.is_running,
                'last_decision_time': self.last_decision_time.isoformat() if self.last_decision_time else None,
                'decision_interval_minutes': self.decision_interval.total_seconds() / 60
            }
        }
        
        return combined_stats
    
    def _get_training_summary(self, training_duration: timedelta) -> Dict[str, Any]:
        """Get training summary"""
        
        if not self.episode_rewards:
            return {'status': 'no_training_data'}
        
        # Calculate statistics
        total_reward = sum(self.episode_rewards)
        avg_reward = np.mean(self.episode_rewards)
        std_reward = np.std(self.episode_rewards)
        max_reward = np.max(self.episode_rewards)
        min_reward = np.min(self.episode_rewards)
        
        # Performance trend
        if len(self.episode_rewards) >= 100:
            early_avg = np.mean(self.episode_rewards[:50])
            late_avg = np.mean(self.episode_rewards[-50:])
            performance_trend = (late_avg - early_avg) / abs(early_avg) if early_avg != 0 else 0
        else:
            performance_trend = 0
        
        # Evaluation performance
        if self.evaluation_scores:
            best_eval = max(self.evaluation_scores)
            final_eval = self.evaluation_scores[-1]
            eval_improvement = (final_eval - self.evaluation_scores[0]) / abs(self.evaluation_scores[0]) if self.evaluation_scores[0] != 0 else 0
        else:
            best_eval = 0
            final_eval = 0
            eval_improvement = 0
        
        return {
            'status': 'completed',
            'training_duration': str(training_duration),
            'total_episodes': len(self.episode_rewards),
            'total_reward': total_reward,
            'avg_reward': avg_reward,
            'std_reward': std_reward,
            'max_reward': max_reward,
            'min_reward': min_reward,
            'performance_trend': performance_trend,
            'best_evaluation_score': best_eval,
            'final_evaluation_score': final_eval,
            'evaluation_improvement': eval_improvement,
            'final_epsilon': self.agent.epsilon,
            'total_training_steps': self.training_step,
            'model_saved': True
        }


# Global RL trader instance
rl_trader = None

def get_rl_trader(symbol: str = "XAUUSD", timeframe: str = "H1") -> ReinforcementLearningTrader:
    """Get or create RL trader instance"""
    global rl_trader
    
    if rl_trader is None:
        rl_trader = ReinforcementLearningTrader(
            symbol=symbol,
            timeframe=timeframe,
            model_path=f"models/rl_model_{symbol}_{timeframe}.pth",
            training_mode=False  # Start in live mode
        )
    
    return rl_trader


async def start_rl_training(symbol: str = "XAUUSD", timeframe: str = "H1", episodes: int = 100):
    """Start RL training"""
    trader = ReinforcementLearningTrader(
        symbol=symbol,
        timeframe=timeframe,
        training_mode=True
    )
    
    logger.info(f"Starting RL training for {symbol} {timeframe}")
    results = await trader.train(num_episodes=episodes)
    
    return results


async def start_rl_live_trading(symbol: str = "XAUUSD", timeframe: str = "H1"):
    """Start RL live trading"""
    trader = get_rl_trader(symbol, timeframe)
    
    if not trader.is_running:
        await trader.start_live_trading()
    
    return trader


def stop_rl_live_trading():
    """Stop RL live trading"""
    global rl_trader
    
    if rl_trader and rl_trader.is_running:
        rl_trader.stop_live_trading()
