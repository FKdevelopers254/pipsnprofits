/**
 * RL Trading Dashboard JavaScript
 * Provides UI for Reinforcement Learning trading system management
 */

class RLDashboard {
    constructor() {
        this.isInitialized = false;
        this.isTraining = false;
        this.isLiveTrading = false;
        this.currentSymbol = 'XAUUSD';
        this.currentTimeframe = 'H1';
        this.updateInterval = null;
        
        this.initializeEventListeners();
        this.startStatusUpdates();
    }

    initializeEventListeners() {
        // Initialize button
        document.getElementById('rl-init-btn')?.addEventListener('click', () => {
            this.initializeRLSystem();
        });

        // Training buttons
        document.getElementById('rl-training-start-btn')?.addEventListener('click', () => {
            this.startTraining();
        });

        document.getElementById('rl-training-stop-btn')?.addEventListener('click', () => {
            this.stopTraining();
        });

        // Live trading buttons
        document.getElementById('rl-live-start-btn')?.addEventListener('click', () => {
            this.startLiveTrading();
        });

        document.getElementById('rl-live-stop-btn')?.addEventListener('click', () => {
            this.stopLiveTrading();
        });

        // Model management buttons
        document.getElementById('rl-model-save-btn')?.addEventListener('click', () => {
            this.saveModel();
        });

        document.getElementById('rl-model-load-btn')?.addEventListener('click', () => {
            this.loadModel();
        });

        // Evaluation button
        document.getElementById('rl-evaluate-btn')?.addEventListener('click', () => {
            this.evaluateModel();
        });

        // Configuration changes
        document.getElementById('rl-symbol-select')?.addEventListener('change', (e) => {
            this.currentSymbol = e.target.value;
        });

        document.getElementById('rl-timeframe-select')?.addEventListener('change', (e) => {
            this.currentTimeframe = e.target.value;
        });
    }

    async initializeRLSystem() {
        try {
            this.showLoading('rl-status', 'Initializing RL system...');
            
            const response = await fetch('/api/v1/rl/initialize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    symbol: this.currentSymbol,
                    timeframe: this.currentTimeframe,
                    training_mode: true
                })
            });

            const result = await response.json();
            
            if (response.ok) {
                this.isInitialized = true;
                this.updateStatus('rl-status', 'success', 'RL System Initialized');
                this.showNotification('RL system initialized successfully', 'success');
                await this.updateRLStatus();
            } else {
                throw new Error(result.detail || 'Initialization failed');
            }
        } catch (error) {
            this.updateStatus('rl-status', 'error', `Initialization failed: ${error.message}`);
            this.showNotification(`Initialization failed: ${error.message}`, 'error');
        }
    }

    async startTraining() {
        try {
            const episodes = parseInt(document.getElementById('rl-training-episodes')?.value || 100);
            const learningRate = parseFloat(document.getElementById('rl-learning-rate')?.value);
            const epsilon = parseFloat(document.getElementById('rl-epsilon')?.value);

            this.showLoading('rl-training-status', 'Starting training...');

            const requestBody = {
                symbol: this.currentSymbol,
                timeframe: this.currentTimeframe,
                episodes: episodes
            };

            if (!isNaN(learningRate)) requestBody.learning_rate = learningRate;
            if (!isNaN(epsilon)) requestBody.epsilon = epsilon;

            const response = await fetch('/api/v1/rl/training/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody)
            });

            const result = await response.json();
            
            if (response.ok) {
                this.isTraining = true;
                this.updateStatus('rl-training-status', 'success', `Training started: ${episodes} episodes`);
                this.showNotification(`Training started for ${episodes} episodes`, 'success');
                this.updateButtonStates();
                await this.updateRLStatus();
            } else {
                throw new Error(result.detail || 'Training start failed');
            }
        } catch (error) {
            this.updateStatus('rl-training-status', 'error', `Training failed: ${error.message}`);
            this.showNotification(`Training failed: ${error.message}`, 'error');
        }
    }

    async stopTraining() {
        try {
            this.showLoading('rl-training-status', 'Stopping training...');

            const response = await fetch('/api/v1/rl/training/stop', {
                method: 'POST'
            });

            const result = await response.json();
            
            if (response.ok) {
                this.isTraining = false;
                this.updateStatus('rl-training-status', 'warning', 'Training stopped');
                this.showNotification('Training stopped', 'warning');
                this.updateButtonStates();
                await this.updateRLStatus();
            } else {
                throw new Error(result.detail || 'Training stop failed');
            }
        } catch (error) {
            this.updateStatus('rl-training-status', 'error', `Stop failed: ${error.message}`);
            this.showNotification(`Training stop failed: ${error.message}`, 'error');
        }
    }

    async startLiveTrading() {
        try {
            const decisionInterval = parseInt(document.getElementById('rl-decision-interval')?.value || 5);
            const confidenceThreshold = parseFloat(document.getElementById('rl-confidence-threshold')?.value || 0.7);

            this.showLoading('rl-live-status', 'Starting live trading...');

            const response = await fetch('/api/v1/rl/live/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    symbol: this.currentSymbol,
                    timeframe: this.currentTimeframe,
                    decision_interval_minutes: decisionInterval,
                    confidence_threshold: confidenceThreshold
                })
            });

            const result = await response.json();
            
            if (response.ok) {
                this.isLiveTrading = true;
                this.updateStatus('rl-live-status', 'success', 'Live trading active');
                this.showNotification('Live trading started', 'success');
                this.updateButtonStates();
                await this.updateRLStatus();
            } else {
                throw new Error(result.detail || 'Live trading start failed');
            }
        } catch (error) {
            this.updateStatus('rl-live-status', 'error', `Live trading failed: ${error.message}`);
            this.showNotification(`Live trading failed: ${error.message}`, 'error');
        }
    }

    async stopLiveTrading() {
        try {
            this.showLoading('rl-live-status', 'Stopping live trading...');

            const response = await fetch('/api/v1/rl/live/stop', {
                method: 'POST'
            });

            const result = await response.json();
            
            if (response.ok) {
                this.isLiveTrading = false;
                this.updateStatus('rl-live-status', 'warning', 'Live trading stopped');
                this.showNotification('Live trading stopped', 'warning');
                this.updateButtonStates();
                await this.updateRLStatus();
            } else {
                throw new Error(result.detail || 'Live trading stop failed');
            }
        } catch (error) {
            this.updateStatus('rl-live-status', 'error', `Stop failed: ${error.message}`);
            this.showNotification(`Live trading stop failed: ${error.message}`, 'error');
        }
    }

    async saveModel() {
        try {
            const filepath = prompt('Enter model filepath (leave empty for auto-generated):');
            
            this.showLoading('rl-model-status', 'Saving model...');

            const response = await fetch('/api/v1/rl/model/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    filepath: filepath || null
                })
            });

            const result = await response.json();
            
            if (response.ok) {
                this.updateStatus('rl-model-status', 'success', `Model saved: ${result.filepath}`);
                this.showNotification(`Model saved to ${result.filepath}`, 'success');
            } else {
                throw new Error(result.detail || 'Model save failed');
            }
        } catch (error) {
            this.updateStatus('rl-model-status', 'error', `Save failed: ${error.message}`);
            this.showNotification(`Model save failed: ${error.message}`, 'error');
        }
    }

    async loadModel() {
        try {
            const filepath = prompt('Enter model filepath:');
            if (!filepath) return;

            this.showLoading('rl-model-status', 'Loading model...');

            const response = await fetch('/api/v1/rl/model/load', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    filepath: filepath
                })
            });

            const result = await response.json();
            
            if (response.ok) {
                this.updateStatus('rl-model-status', 'success', `Model loaded: ${result.filepath}`);
                this.showNotification(`Model loaded from ${result.filepath}`, 'success');
                await this.updateRLStatus();
            } else {
                throw new Error(result.detail || 'Model load failed');
            }
        } catch (error) {
            this.updateStatus('rl-model-status', 'error', `Load failed: ${error.message}`);
            this.showNotification(`Model load failed: ${error.message}`, 'error');
        }
    }

    async evaluateModel() {
        try {
            const episodes = parseInt(prompt('Enter number of evaluation episodes:', '10')) || 10;

            this.showLoading('rl-evaluation-status', 'Evaluating model...');

            const response = await fetch('/api/v1/rl/evaluate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    episodes: episodes
                })
            });

            const result = await response.json();
            
            if (response.ok) {
                this.updateStatus('rl-evaluation-status', 'success', 
                    `Evaluation score: ${result.evaluation_score.toFixed(4)} (${result.episodes} episodes)`);
                this.showNotification(`Evaluation completed: ${result.evaluation_score.toFixed(4)}`, 'success');
            } else {
                throw new Error(result.detail || 'Evaluation failed');
            }
        } catch (error) {
            this.updateStatus('rl-evaluation-status', 'error', `Evaluation failed: ${error.message}`);
            this.showNotification(`Evaluation failed: ${error.message}`, 'error');
        }
    }

    async updateRLStatus() {
        try {
            const response = await fetch('/api/v1/rl/status');
            const status = await response.json();

            if (response.ok) {
                this.isInitialized = status.status !== 'not_initialized';
                this.isTraining = status.is_training;
                this.isLiveTrading = status.is_live_trading;

                // Update status displays
                this.updateStatus('rl-status', 
                    this.isInitialized ? 'success' : 'warning',
                    this.isInitialized ? 'RL System Active' : 'RL System Not Initialized'
                );

                if (status.performance) {
                    this.updatePerformanceMetrics(status.performance);
                }

                this.updateButtonStates();
            }
        } catch (error) {
            console.error('Error updating RL status:', error);
        }
    }

    updatePerformanceMetrics(performance) {
        // Update training metrics
        if (performance.training) {
            const training = performance.training;
            document.getElementById('rl-current-episode')?.textContent = training.current_episode || 0;
            document.getElementById('rl-total-episodes')?.textContent = training.total_episodes || 0;
            document.getElementById('rl-avg-reward')?.textContent = 
                (training.avg_episode_reward || 0).toFixed(4);
            document.getElementById('rl-best-eval-score')?.textContent = 
                (training.best_evaluation_score || 0).toFixed(4);
        }

        // Update environment metrics
        if (performance.environment) {
            const env = performance.environment;
            document.getElementById('rl-balance')?.textContent = 
                (env.current_balance || 0).toFixed(2);
            document.getElementById('rl-total-pnl')?.textContent = 
                (env.total_pnl || 0).toFixed(2);
            document.getElementById('rl-win-rate')?.textContent = 
                ((env.win_rate || 0) * 100).toFixed(1) + '%';
            document.getElementById('rl-max-drawdown')?.textContent = 
                ((env.max_drawdown || 0) * 100).toFixed(2) + '%';
            document.getElementById('rl-open-positions')?.textContent = 
                env.open_positions || 0;
        }

        // Update agent metrics
        if (performance.agent) {
            const agent = performance.agent;
            document.getElementById('rl-epsilon')?.textContent = 
                (agent.epsilon || 0).toFixed(4);
            document.getElementById('rl-training-steps')?.textContent = 
                agent.training_step || 0;
            document.getElementById('rl-avg-loss')?.textContent = 
                (agent.avg_loss || 0).toFixed(6);
        }
    }

    updateButtonStates() {
        // Initialize button
        const initBtn = document.getElementById('rl-init-btn');
        if (initBtn) {
            initBtn.disabled = this.isInitialized;
            initBtn.textContent = this.isInitialized ? 'Initialized' : 'Initialize RL System';
        }

        // Training buttons
        const trainingStartBtn = document.getElementById('rl-training-start-btn');
        const trainingStopBtn = document.getElementById('rl-training-stop-btn');
        
        if (trainingStartBtn) {
            trainingStartBtn.disabled = !this.isInitialized || this.isTraining || this.isLiveTrading;
        }
        if (trainingStopBtn) {
            trainingStopBtn.disabled = !this.isTraining;
        }

        // Live trading buttons
        const liveStartBtn = document.getElementById('rl-live-start-btn');
        const liveStopBtn = document.getElementById('rl-live-stop-btn');
        
        if (liveStartBtn) {
            liveStartBtn.disabled = !this.isInitialized || this.isLiveTrading || this.isTraining;
        }
        if (liveStopBtn) {
            liveStopBtn.disabled = !this.isLiveTrading;
        }

        // Model management buttons
        const modelSaveBtn = document.getElementById('rl-model-save-btn');
        const modelLoadBtn = document.getElementById('rl-model-load-btn');
        
        if (modelSaveBtn) {
            modelSaveBtn.disabled = !this.isInitialized;
        }
        if (modelLoadBtn) {
            modelLoadBtn.disabled = false; // Always allow loading
        }
    }

    updateStatus(elementId, status, message) {
        const element = document.getElementById(elementId);
        if (!element) return;

        element.className = `status-${status}`;
        element.textContent = message;
    }

    showLoading(elementId, message) {
        this.updateStatus(elementId, 'loading', message);
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        // Add to page
        document.body.appendChild(notification);
        
        // Remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    startStatusUpdates() {
        // Update status every 5 seconds
        this.updateInterval = setInterval(() => {
            if (this.isInitialized) {
                this.updateRLStatus();
            }
        }, 5000);

        // Initial update
        this.updateRLStatus();
        this.updateButtonStates();
    }

    destroy() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }
    }
}

// Initialize RL dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.rlDashboard = new RLDashboard();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.rlDashboard) {
        window.rlDashboard.destroy();
    }
});
