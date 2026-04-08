/**
 * Real-time WebSocket client for sub-second trading updates
 * Provides instant price streaming, chart updates, and trade notifications
 */
class RealtimeClient {
    constructor() {
        this.ws = null;
        this.clientId = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000; // Start with 1 second
        this.isConnecting = false;
        this.isConnected = false;
        
        // Subscription callbacks
        this.callbacks = {
            price_update: [],
            chart_update: [],
            trade_update: [],
            analytics_update: [],
            trade_notification: [],
            alert: [],
            status_update: [],
            connection_status: []
        };
        
        // Performance tracking
        this.lastUpdateTimes = {};
        this.updateIntervals = {};
        this.performanceStats = {
            totalUpdates: 0,
            latency: [],
            messageRate: 0
        };
        
        // Start connection
        this.connect();
    }
    
    /**
     * Connect to WebSocket server
     */
    async connect() {
        if (this.isConnecting || this.isConnected) {
            return;
        }
        
        this.isConnecting = true;
        const wsUrl = `ws://${window.location.host}/ws/realtime`;
        
        try {
            console.log('🚀 Connecting to real-time WebSocket:', wsUrl);
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => this.handleOpen();
            this.ws.onmessage = (event) => this.handleMessage(event);
            this.ws.onclose = (event) => this.handleClose(event);
            this.ws.onerror = (error) => this.handleError(error);
            
        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.isConnecting = false;
            this.scheduleReconnect();
        }
    }
    
    /**
     * Handle WebSocket connection open
     */
    handleOpen() {
        console.log('✅ WebSocket connected successfully');
        this.isConnecting = false;
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        
        // Notify listeners
        this.emit('connection_status', {
            connected: true,
            timestamp: new Date().toISOString()
        });
        
        // Start heartbeat
        this.startHeartbeat();
        
        // Subscribe to default data streams
        this.subscribeToDefaults();
    }
    
    /**
     * Handle incoming WebSocket messages
     */
    handleMessage(event) {
        try {
            const message = JSON.parse(event.data);
            const startTime = performance.now();
            
            // Track performance
            this.updatePerformanceStats(message.type, startTime);
            
            // Route message to appropriate handler
            this.routeMessage(message);
            
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }
    
    /**
     * Route message to appropriate handler
     */
    routeMessage(message) {
        const { type, data, timestamp } = message;
        
        switch (type) {
            case 'price_update':
                this.handlePriceUpdate(data, timestamp);
                break;
            case 'chart_update':
                this.handleChartUpdate(data, timestamp);
                break;
            case 'trade_update':
                this.handleTradeUpdate(data, timestamp);
                break;
            case 'analytics_update':
                this.handleAnalyticsUpdate(data, timestamp);
                break;
            case 'trade_notification':
                this.handleTradeNotification(data, timestamp);
                break;
            case 'alert':
                this.handleAlert(message.alert_type, message.message, data, timestamp);
                break;
            case 'status_update':
                this.handleStatusUpdate(data, timestamp);
                break;
            case 'initial_chart_data':
                this.handleInitialChartData(data, timestamp);
                break;
            case 'initial_performance_data':
                this.handleInitialPerformanceData(data, timestamp);
                break;
            case 'initial_positions':
                this.handleInitialPositions(data, timestamp);
                break;
            case 'subscription_confirmed':
                console.log(`✅ Subscribed to ${message.data_type}`);
                break;
            case 'unsubscription_confirmed':
                console.log(`📴 Unsubscribed from ${message.data_type}`);
                break;
            case 'ping':
                // Respond to ping
                this.send({ type: 'pong' });
                break;
            case 'pong':
                // Update latency
                this.updateLatency(timestamp);
                break;
            case 'error':
                console.error('🚨 WebSocket error:', message.message);
                this.showNotification(message.message, 'error');
                break;
            default:
                console.log('📩 Unknown message type:', type, message);
        }
    }
    
    /**
     * Handle price updates
     */
    handlePriceUpdate(data, timestamp) {
        this.emit('price_update', {
            data: data,
            timestamp: timestamp,
            latency: this.calculateLatency(timestamp)
        });
        
        // Update UI elements
        this.updatePriceDisplay(data);
    }
    
    /**
     * Handle chart updates
     */
    handleChartUpdate(data, timestamp) {
        this.emit('chart_update', {
            data: data,
            timestamp: timestamp,
            latency: this.calculateLatency(timestamp)
        });
        
        // Update trading chart if available
        if (window.tradingChart && data.latest_candle) {
            this.updateChartWithNewData(data);
        }
    }
    
    /**
     * Handle trade updates
     */
    handleTradeUpdate(data, timestamp) {
        this.emit('trade_update', {
            data: data,
            timestamp: timestamp,
            latency: this.calculateLatency(timestamp)
        });
        
        // Update positions display
        this.updatePositionsDisplay(data);
    }
    
    /**
     * Handle analytics updates
     */
    handleAnalyticsUpdate(data, timestamp) {
        this.emit('analytics_update', {
            data: data,
            timestamp: timestamp,
            latency: this.calculateLatency(timestamp)
        });
        
        // Update analytics display
        this.updateAnalyticsDisplay(data);
    }
    
    /**
     * Handle trade notifications
     */
    handleTradeNotification(data, timestamp) {
        this.emit('trade_notification', {
            data: data,
            timestamp: timestamp,
            latency: this.calculateLatency(timestamp)
        });
        
        // Show trade notification
        this.showTradeNotification(data);
    }
    
    /**
     * Handle alerts
     */
    handleAlert(alertType, message, data, timestamp) {
        this.emit('alert', {
            alertType: alertType,
            message: message,
            data: data,
            timestamp: timestamp,
            latency: this.calculateLatency(timestamp)
        });
        
        // Show alert notification
        this.showNotification(message, alertType, data);
    }
    
    /**
     * Handle status updates
     */
    handleStatusUpdate(data, timestamp) {
        this.emit('status_update', {
            data: data,
            timestamp: timestamp,
            latency: this.calculateLatency(timestamp)
        });
    }
    
    /**
     * Handle initial chart data
     */
    handleInitialChartData(data, timestamp) {
        console.log('📊 Received initial chart data:', data);
        this.emit('initial_chart_data', { data, timestamp });
        
        // Initialize chart with data
        if (window.tradingChart) {
            window.tradingChart.setData(data);
        }
    }
    
    /**
     * Handle initial performance data
     */
    handleInitialPerformanceData(data, timestamp) {
        console.log('📈 Received initial performance data:', data);
        this.emit('initial_performance_data', { data, timestamp });
    }
    
    /**
     * Handle initial positions
     */
    handleInitialPositions(data, timestamp) {
        console.log('💼 Received initial positions:', data);
        this.emit('initial_positions', { data, timestamp });
    }
    
    /**
     * Update trading chart with new data
     */
    updateChartWithNewData(data) {
        try {
            if (data.latest_candle && window.tradingChart) {
                // Add new candle to chart
                window.tradingChart.addRealtimeCandle(data.latest_candle);
                
                // Update indicators if provided
                if (data.indicators) {
                    window.tradingChart.updateIndicators(data.indicators);
                }
            }
        } catch (error) {
            console.error('Error updating chart:', error);
        }
    }
    
    /**
     * Update price display elements
     */
    updatePriceDisplay(priceData) {
        for (const [symbol, data] of Object.entries(priceData)) {
            // Update price displays
            const priceElements = document.querySelectorAll(`[data-symbol="${symbol}"] .price`);
            priceElements.forEach(el => {
                el.textContent = data.bid.toFixed(2);
            });
            
            // Update spread displays
            const spreadElements = document.querySelectorAll(`[data-symbol="${symbol}"] .spread`);
            spreadElements.forEach(el => {
                el.textContent = (data.spread * 10000).toFixed(1); // Convert to pips
            });
            
            // Update change indicators
            const changeElements = document.querySelectorAll(`[data-symbol="${symbol}"] .change`);
            changeElements.forEach(el => {
                const changeClass = data.change >= 0 ? 'positive' : 'negative';
                el.className = `change ${changeClass}`;
                el.textContent = `${data.change >= 0 ? '+' : ''}${data.change.toFixed(2)}`;
            });
        }
    }
    
    /**
     * Update positions display
     */
    updatePositionsDisplay(data) {
        const positionsContainer = document.getElementById('open-positions');
        if (positionsContainer) {
            // Update positions count
            const countElement = document.getElementById('positions-count');
            if (countElement) {
                countElement.textContent = data.position_count;
            }
            
            // Update total P&L
            const pnlElement = document.getElementById('total-pnl');
            if (pnlElement) {
                const pnl = data.total_pnl;
                pnlElement.textContent = `$${pnl.toFixed(2)}`;
                pnlElement.className = pnl >= 0 ? 'positive' : 'negative';
            }
        }
    }
    
    /**
     * Update analytics display
     */
    updateAnalyticsDisplay(data) {
        // Update performance metrics
        if (data.win_rate !== undefined) {
            const winRateEl = document.getElementById('win-rate');
            if (winRateEl) {
                winRateEl.textContent = `${(data.win_rate * 100).toFixed(1)}%`;
            }
        }
        
        if (data.total_trades !== undefined) {
            const tradesEl = document.getElementById('total-trades');
            if (tradesEl) {
                tradesEl.textContent = data.total_trades;
            }
        }
        
        if (data.profit_factor !== undefined) {
            const profitFactorEl = document.getElementById('profit-factor');
            if (profitFactorEl) {
                profitFactorEl.textContent = data.profit_factor.toFixed(2);
            }
        }
    }
    
    /**
     * Show trade notification
     */
    showTradeNotification(tradeData) {
        const message = `Trade ${tradeData.action.toUpperCase()} ${tradeData.symbol} ${tradeData.volume}`;
        this.showNotification(message, 'success', tradeData);
        
        // Play sound if enabled
        this.playNotificationSound('trade');
    }
    
    /**
     * Show notification
     */
    showNotification(message, type = 'info', data = null) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-message">${message}</span>
                <button class="notification-close">&times;</button>
            </div>
        `;
        
        // Add to notifications container
        const container = document.getElementById('notifications') || this.createNotificationsContainer();
        container.appendChild(notification);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
        
        // Handle close button
        notification.querySelector('.notification-close').addEventListener('click', () => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        });
    }
    
    /**
     * Create notifications container
     */
    createNotificationsContainer() {
        const container = document.createElement('div');
        container.id = 'notifications';
        container.className = 'notifications-container';
        document.body.appendChild(container);
        return container;
    }
    
    /**
     * Play notification sound
     */
    playNotificationSound(type) {
        try {
            const audio = new Audio(`/static/sounds/${type}.mp3`);
            audio.volume = 0.3;
            audio.play().catch(e => console.log('Could not play sound:', e));
        } catch (error) {
            console.log('Sound not available:', error);
        }
    }
    
    /**
     * Handle WebSocket close
     */
    handleClose(event) {
        console.log('🔌 WebSocket disconnected:', event.code, event.reason);
        this.isConnected = false;
        this.isConnecting = false;
        
        // Notify listeners
        this.emit('connection_status', {
            connected: false,
            code: event.code,
            reason: event.reason,
            timestamp: new Date().toISOString()
        });
        
        // Schedule reconnection
        if (event.code !== 1000) { // Not a normal closure
            this.scheduleReconnect();
        }
    }
    
    /**
     * Handle WebSocket error
     */
    handleError(error) {
        console.error('🚨 WebSocket error:', error);
        this.isConnecting = false;
        
        this.showNotification('Connection error. Attempting to reconnect...', 'error');
    }
    
    /**
     * Schedule reconnection attempt
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('❌ Max reconnection attempts reached');
            this.showNotification('Unable to reconnect to server. Please refresh the page.', 'error');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff
        
        console.log(`🔄 Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        
        setTimeout(() => {
            this.connect();
        }, delay);
    }
    
    /**
     * Start heartbeat to keep connection alive
     */
    startHeartbeat() {
        setInterval(() => {
            if (this.isConnected && this.ws) {
                this.send({ type: 'ping', timestamp: new Date().toISOString() });
            }
        }, 30000); // Every 30 seconds
    }
    
    /**
     * Subscribe to default data streams
     */
    subscribeToDefaults() {
        this.subscribe('prices');
        this.subscribe('chart');
        this.subscribe('trades');
        this.subscribe('analytics');
    }
    
    /**
     * Subscribe to data stream
     */
    subscribe(dataType) {
        if (this.isConnected && this.ws) {
            this.send({
                type: 'subscribe',
                data_type: dataType
            });
        }
    }
    
    /**
     * Unsubscribe from data stream
     */
    unsubscribe(dataType) {
        if (this.isConnected && this.ws) {
            this.send({
                type: 'unsubscribe',
                data_type: dataType
            });
        }
    }
    
    /**
     * Send message to WebSocket server
     */
    send(message) {
        if (this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
            return true;
        }
        return false;
    }
    
    /**
     * Execute trade via WebSocket
     */
    executeTrade(action, symbol = 'XAUUSD', volume = 0.01) {
        return this.send({
            type: 'execute_trade',
            action: action,
            symbol: symbol,
            volume: volume
        });
    }
    
    /**
     * Get current status
     */
    getStatus() {
        if (this.isConnected) {
            this.send({ type: 'get_status' });
        }
    }
    
    /**
     * Register callback for event
     */
    on(eventType, callback) {
        if (!this.callbacks[eventType]) {
            this.callbacks[eventType] = [];
        }
        this.callbacks[eventType].push(callback);
    }
    
    /**
     * Remove callback for event
     */
    off(eventType, callback) {
        if (this.callbacks[eventType]) {
            const index = this.callbacks[eventType].indexOf(callback);
            if (index > -1) {
                this.callbacks[eventType].splice(index, 1);
            }
        }
    }
    
    /**
     * Emit event to all callbacks
     */
    emit(eventType, data) {
        if (this.callbacks[eventType]) {
            this.callbacks[eventType].forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error('Error in callback:', error);
                }
            });
        }
    }
    
    /**
     * Update performance statistics
     */
    updatePerformanceStats(messageType, startTime) {
        const processingTime = performance.now() - startTime;
        this.performanceStats.totalUpdates++;
        
        if (!this.lastUpdateTimes[messageType]) {
            this.lastUpdateTimes[messageType] = [];
        }
        
        this.lastUpdateTimes[messageType].push(startTime);
        
        // Keep only last 10 timestamps for each message type
        if (this.lastUpdateTimes[messageType].length > 10) {
            this.lastUpdateTimes[messageType].shift();
        }
        
        // Calculate message rate
        const now = performance.now();
        const recentMessages = Object.values(this.lastUpdateTimes)
            .flat()
            .filter(time => now - time < 5000); // Last 5 seconds
        
        this.performanceStats.messageRate = recentMessages.length / 5;
    }
    
    /**
     * Calculate latency
     */
    calculateLatency(timestamp) {
        if (timestamp) {
            const serverTime = new Date(timestamp).getTime();
            const clientTime = Date.now();
            return clientTime - serverTime;
        }
        return 0;
    }
    
    /**
     * Update latency tracking
     */
    updateLatency(timestamp) {
        const latency = this.calculateLatency(timestamp);
        if (latency > 0) {
            this.performanceStats.latency.push(latency);
            
            // Keep only last 100 latency measurements
            if (this.performanceStats.latency.length > 100) {
                this.performanceStats.latency.shift();
            }
        }
    }
    
    /**
     * Get performance statistics
     */
    getPerformanceStats() {
        const latency = this.performanceStats.latency;
        const avgLatency = latency.length > 0 ? 
            latency.reduce((a, b) => a + b, 0) / latency.length : 0;
        
        return {
            totalUpdates: this.performanceStats.totalUpdates,
            messageRate: this.performanceStats.messageRate,
            averageLatency: Math.round(avgLatency),
            isConnected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts
        };
    }
    
    /**
     * Disconnect from WebSocket
     */
    disconnect() {
        if (this.ws) {
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }
        this.isConnected = false;
        this.isConnecting = false;
    }
}

// Initialize global realtime client
window.realtimeClient = new RealtimeClient();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RealtimeClient;
}
