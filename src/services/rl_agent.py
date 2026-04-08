"""
Reinforcement Learning Trading Agent - Deep Q-Network (DQN)
Implements a DQN agent for trading decision making
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from collections import deque
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class DQNetwork(nn.Module):
    """Deep Q-Network for trading decisions"""
    
    def __init__(self, state_size: int = 50, action_size: int = 5, hidden_size: int = 128):
        super(DQNetwork, self).__init__()
        
        # Input layer
        self.fc1 = nn.Linear(state_size, hidden_size)
        self.bn1 = nn.BatchNorm1d(hidden_size)
        self.dropout1 = nn.Dropout(0.2)
        
        # Hidden layers
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.bn2 = nn.BatchNorm1d(hidden_size)
        self.dropout2 = nn.Dropout(0.2)
        
        self.fc3 = nn.Linear(hidden_size, hidden_size // 2)
        self.bn3 = nn.BatchNorm1d(hidden_size // 2)
        self.dropout3 = nn.Dropout(0.2)
        
        # Output layer
        self.fc4 = nn.Linear(hidden_size // 2, action_size)
        
        # Activation functions
        self.relu = nn.ReLU()
        self.tanh = nn.Tanh()
        
    def forward(self, x):
        """Forward pass through network"""
        # Input layer
        x = self.fc1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.dropout1(x)
        
        # Hidden layer 1
        x = self.fc2(x)
        x = self.bn2(x)
        x = self.relu(x)
        x = self.dropout2(x)
        
        # Hidden layer 2
        x = self.fc3(x)
        x = self.bn3(x)
        x = self.relu(x)
        x = self.dropout3(x)
        
        # Output layer
        x = self.fc4(x)
        
        return x

class DQNAgent:
    """Deep Q-Network Trading Agent"""
    
    def __init__(
        self,
        state_size: int = 50,
        action_size: int = 5,
        learning_rate: float = 0.001,
        gamma: float = 0.95,
        epsilon: float = 1.0,
        epsilon_min: float = 0.01,
        epsilon_decay: float = 0.995,
        memory_size: int = 10000,
        batch_size: int = 32,
        target_update_freq: int = 1000
    ):
        self.state_size = state_size
        self.action_size = action_size
        self.learning_rate = learning_rate
        self.gamma = gamma  # Discount factor for future rewards
        self.epsilon = epsilon  # Exploration rate
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        
        # Device configuration
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"RL Agent using device: {self.device}")
        
        # Neural networks
        self.q_network = DQNetwork(state_size, action_size).to(self.device)
        self.target_network = DQNetwork(state_size, action_size).to(self.device)
        
        # Initialize target network weights
        self.update_target_network()
        
        # Optimizer
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=learning_rate)
        
        # Training metrics
        self.training_step = 0
        self.losses = deque(maxlen=1000)
        self.rewards = deque(maxlen=1000)
        
        # Action mapping
        self.action_map = {
            0: 'HOLD',
            1: 'BUY',
            2: 'SELL', 
            3: 'CLOSE_LONG',
            4: 'CLOSE_SHORT'
        }
        
        logger.info(f"DQN Agent initialized with {state_size} states and {action_size} actions")
    
    def act(self, state: np.ndarray, training: bool = True) -> int:
        """Choose action using epsilon-greedy policy"""
        
        # Convert state to tensor
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        
        if training and random.random() < self.epsilon:
            # Explore: random action
            action = random.randrange(self.action_size)
            logger.debug(f"Random action chosen: {self.action_map[action]} (epsilon={self.epsilon:.3f})")
        else:
            # Exploit: best action from Q-network
            with torch.no_grad():
                q_values = self.q_network(state_tensor)
                action = q_values.argmax().item()
            logger.debug(f"Best action chosen: {self.action_map[action]}")
        
        return action
    
    def remember(self, state: np.ndarray, action: int, reward: float, 
                next_state: np.ndarray, done: bool):
        """Store experience in memory"""
        # This will be handled by ExperienceReplay buffer
        pass
    
    def replay(self, experiences: List[Tuple]) -> float:
        """Train the model on a batch of experiences"""
        if len(experiences) < self.batch_size:
            return 0.0
        
        # Unpack experiences
        states = torch.FloatTensor([e[0] for e in experiences]).to(self.device)
        actions = torch.LongTensor([e[1] for e in experiences]).to(self.device)
        rewards = torch.FloatTensor([e[2] for e in experiences]).to(self.device)
        next_states = torch.FloatTensor([e[3] for e in experiences]).to(self.device)
        dones = torch.BoolTensor([e[4] for e in experiences]).to(self.device)
        
        # Get current Q values
        current_q_values = self.q_network(states).gather(1, actions.unsqueeze(1))
        
        # Get next Q values from target network
        with torch.no_grad():
            next_q_values = self.target_network(next_states).max(1)[0]
            target_q_values = rewards + (self.gamma * next_q_values * ~dones)
        
        # Compute loss
        loss = nn.MSELoss()(current_q_values.squeeze(), target_q_values)
        
        # Optimize the model
        self.optimizer.zero_grad()
        loss.backward()
        
        # Gradient clipping to prevent exploding gradients
        torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), max_norm=1.0)
        
        self.optimizer.step()
        
        # Update training metrics
        self.losses.append(loss.item())
        self.training_step += 1
        
        # Update target network
        if self.training_step % self.target_update_freq == 0:
            self.update_target_network()
            logger.info(f"Target network updated at step {self.training_step}")
        
        return loss.item()
    
    def update_target_network(self):
        """Copy weights from main network to target network"""
        self.target_network.load_state_dict(self.q_network.state_dict())
    
    def decay_epsilon(self):
        """Decay exploration rate"""
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
            logger.debug(f"Epsilon decayed to {self.epsilon:.4f}")
    
    def get_q_values(self, state: np.ndarray) -> np.ndarray:
        """Get Q-values for a state"""
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q_values = self.q_network(state_tensor)
        return q_values.cpu().numpy().flatten()
    
    def get_action_confidence(self, state: np.ndarray) -> Tuple[int, float]:
        """Get action and confidence score"""
        q_values = self.get_q_values(state)
        action = np.argmax(q_values)
        confidence = float(np.max(q_values) / np.sum(np.abs(q_values)) + 1e-8)
        return action, confidence
    
    def save_model(self, filepath: str):
        """Save model weights"""
        torch.save({
            'q_network_state_dict': self.q_network.state_dict(),
            'target_network_state_dict': self.target_network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'training_step': self.training_step,
            'losses': list(self.losses),
            'rewards': list(self.rewards)
        }, filepath)
        logger.info(f"Model saved to {filepath}")
    
    def load_model(self, filepath: str):
        """Load model weights"""
        checkpoint = torch.load(filepath, map_location=self.device)
        self.q_network.load_state_dict(checkpoint['q_network_state_dict'])
        self.target_network.load_state_dict(checkpoint['target_network_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.epsilon = checkpoint.get('epsilon', self.epsilon)
        self.training_step = checkpoint.get('training_step', 0)
        self.losses = deque(checkpoint.get('losses', []), maxlen=1000)
        self.rewards = deque(checkpoint.get('rewards', []), maxlen=1000)
        logger.info(f"Model loaded from {filepath}")
    
    def get_training_stats(self) -> dict:
        """Get training statistics"""
        return {
            'training_step': self.training_step,
            'epsilon': self.epsilon,
            'avg_loss': np.mean(self.losses) if self.losses else 0.0,
            'avg_reward': np.mean(self.rewards) if self.rewards else 0.0,
            'recent_loss': list(self.losses)[-10:] if len(self.losses) >= 10 else list(self.losses),
            'recent_reward': list(self.rewards)[-10:] if len(self.rewards) >= 10 else list(self.rewards)
        }
