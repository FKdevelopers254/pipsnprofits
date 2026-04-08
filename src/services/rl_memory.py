"""
Experience Replay Buffer for Reinforcement Learning
Stores and samples trading experiences for training
"""

import random
import numpy as np
from collections import deque
from typing import List, Tuple, Optional
import logging
import pickle
import os

logger = logging.getLogger(__name__)

class ExperienceReplay:
    """Experience Replay Buffer for DQN training"""
    
    def __init__(
        self,
        capacity: int = 10000,
        batch_size: int = 32,
        min_experiences: int = 1000,
        save_path: Optional[str] = None
    ):
        self.capacity = capacity
        self.batch_size = batch_size
        self.min_experiences = min_experiences
        self.save_path = save_path
        
        # Main experience buffer
        self.buffer = deque(maxlen=capacity)
        
        # Priority buffer (for prioritized experience replay)
        self.priorities = deque(maxlen=capacity)
        self.alpha = 0.6  # Priority exponent
        self.beta = 0.4   # Importance sampling weight
        
        # Statistics
        self.total_experiences = 0
        self.samples_taken = 0
        
        logger.info(f"Experience Replay initialized with capacity {capacity}")
    
    def add_experience(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        priority: Optional[float] = None
    ):
        """Add experience to buffer with optional priority"""
        
        experience = (state, action, reward, next_state, done)
        
        # Calculate priority if not provided
        if priority is None:
            priority = self._calculate_priority(reward, done)
        
        self.buffer.append(experience)
        self.priorities.append(priority)
        self.total_experiences += 1
        
        logger.debug(f"Added experience: action={action}, reward={reward:.4f}, priority={priority:.4f}")
    
    def _calculate_priority(self, reward: float, done: bool) -> float:
        """Calculate priority for experience"""
        # Higher priority for:
        # 1. Large rewards (positive or negative)
        # 2. Terminal states (done=True)
        # 3. Recent experiences
        
        base_priority = abs(reward)
        if done:
            base_priority *= 2.0  # Boost terminal experiences
        
        # Add small randomization to prevent same priority for all
        priority = base_priority + random.random() * 0.001
        
        return priority
    
    def sample(self, batch_size: Optional[int] = None) -> List[Tuple]:
        """Sample batch of experiences using prioritized replay"""
        
        if len(self.buffer) < self.min_experiences:
            logger.warning(f"Not enough experiences to sample: {len(self.buffer)}/{self.min_experiences}")
            return []
        
        batch_size = batch_size or self.batch_size
        
        # Use prioritized sampling
        if len(self.buffer) > batch_size:
            indices = self._prioritized_sample(batch_size)
            experiences = [self.buffer[i] for i in indices]
        else:
            # Fallback to random sampling
            experiences = random.sample(list(self.buffer), min(batch_size, len(self.buffer)))
        
        self.samples_taken += 1
        logger.debug(f"Sampled {len(experiences)} experiences (total samples: {self.samples_taken})")
        
        return experiences
    
    def _prioritized_sample(self, batch_size: int) -> List[int]:
        """Sample indices based on priorities"""
        
        # Convert priorities to probabilities
        priorities = np.array(self.priorities)
        priorities = priorities ** self.alpha
        probabilities = priorities / np.sum(priorities)
        
        # Sample based on probabilities
        indices = np.random.choice(
            len(self.buffer),
            size=batch_size,
            replace=False,
            p=probabilities
        )
        
        return indices.tolist()
    
    def get_importance_weights(self, indices: List[int]) -> np.ndarray:
        """Calculate importance sampling weights"""
        if len(self.buffer) == 0:
            return np.ones(len(indices))
        
        # Calculate sampling probabilities
        priorities = np.array([self.priorities[i] for i in indices])
        sampling_probs = priorities ** self.alpha
        sampling_probs = sampling_probs / np.sum(sampling_probs)
        
        # Calculate importance weights
        importance_weights = (len(self.buffer) * sampling_probs) ** (-self.beta)
        
        # Normalize weights
        importance_weights = importance_weights / np.max(importance_weights)
        
        return importance_weights
    
    def update_priorities(self, indices: List[int], td_errors: List[float]):
        """Update priorities based on TD errors"""
        for idx, td_error in zip(indices, td_errors):
            if 0 <= idx < len(self.priorities):
                # New priority based on TD error
                new_priority = abs(td_error) + 1e-6  # Small epsilon to prevent zero priority
                self.priorities[idx] = new_priority
        
        logger.debug(f"Updated priorities for {len(indices)} experiences")
    
    def is_ready(self) -> bool:
        """Check if buffer is ready for training"""
        return len(self.buffer) >= self.min_experiences
    
    def get_stats(self) -> dict:
        """Get buffer statistics"""
        if not self.buffer:
            return {
                'size': 0,
                'capacity': self.capacity,
                'ready': False,
                'avg_reward': 0.0,
                'avg_priority': 0.0
            }
        
        rewards = [exp[2] for exp in self.buffer]
        priorities = list(self.priorities)
        
        return {
            'size': len(self.buffer),
            'capacity': self.capacity,
            'ready': self.is_ready(),
            'avg_reward': np.mean(rewards),
            'std_reward': np.std(rewards),
            'min_reward': np.min(rewards),
            'max_reward': np.max(rewards),
            'avg_priority': np.mean(priorities),
            'total_experiences': self.total_experiences,
            'samples_taken': self.samples_taken,
            'utilization': len(self.buffer) / self.capacity
        }
    
    def save_buffer(self, filepath: Optional[str] = None):
        """Save experience buffer to file"""
        if not filepath:
            filepath = self.save_path
        
        if not filepath:
            logger.warning("No save path provided for experience buffer")
            return
        
        try:
            data = {
                'buffer': list(self.buffer),
                'priorities': list(self.priorities),
                'total_experiences': self.total_experiences,
                'samples_taken': self.samples_taken,
                'capacity': self.capacity,
                'batch_size': self.batch_size,
                'min_experiences': self.min_experiences
            }
            
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
            
            logger.info(f"Experience buffer saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save experience buffer: {e}")
    
    def load_buffer(self, filepath: str):
        """Load experience buffer from file"""
        if not os.path.exists(filepath):
            logger.warning(f"Experience buffer file not found: {filepath}")
            return
        
        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
            
            self.buffer = deque(data['buffer'], maxlen=self.capacity)
            self.priorities = deque(data['priorities'], maxlen=self.capacity)
            self.total_experiences = data.get('total_experiences', 0)
            self.samples_taken = data.get('samples_taken', 0)
            
            logger.info(f"Experience buffer loaded from {filepath}")
            logger.info(f"Loaded {len(self.buffer)} experiences")
            
        except Exception as e:
            logger.error(f"Failed to load experience buffer: {e}")
    
    def clear_buffer(self):
        """Clear all experiences"""
        self.buffer.clear()
        self.priorities.clear()
        self.total_experiences = 0
        self.samples_taken = 0
        logger.info("Experience buffer cleared")
    
    def get_recent_experiences(self, count: int = 100) -> List[Tuple]:
        """Get most recent experiences"""
        recent_count = min(count, len(self.buffer))
        return list(self.buffer)[-recent_count:]
    
    def get_best_experiences(self, count: int = 10) -> List[Tuple]:
        """Get experiences with highest rewards"""
        if not self.buffer:
            return []
        
        # Sort by reward
        sorted_experiences = sorted(self.buffer, key=lambda x: x[2], reverse=True)
        return sorted_experiences[:count]
    
    def __len__(self) -> int:
        """Get buffer size"""
        return len(self.buffer)
    
    def __bool__(self) -> bool:
        """Check if buffer has experiences"""
        return len(self.buffer) > 0
