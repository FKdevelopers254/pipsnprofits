class TradingChart {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) {
            throw new Error(`Canvas element with id '${canvasId}' not found`);
        }
        
        this.ctx = this.canvas.getContext('2d');
        this.options = {
            width: options.width || 800,
            height: options.height || 400,
            backgroundColor: options.backgroundColor || '#0a0a0f',
            gridColor: options.gridColor || 'rgba(255, 255, 255, 0.1)',
            textColor: options.textColor || '#e2e8f0',
            upColor: options.upColor || '#22c55e',
            downColor: options.downColor || '#ef4444',
            volumeColor: options.volumeColor || 'rgba(34, 197, 94, 0.6)',
            maColors: options.maColors || ['#06b6d4', '#f59e0b', '#a855f7'],
            ...options
        };
        
        this.data = {
            candles: [],
            volume: [],
            indicators: {
                ma20: [],
                ma50: [],
                ma200: [],
                rsi: [],
                macd: { line: [], signal: [], histogram: [] },
                bb: { upper: [], middle: [], lower: [] }
            },
            trades: [],
            levels: [],
            priceAction: {
                fvgs: [],
                zones: [],
                bos: [],
                orderBlocks: [],
                liquiditySweeps: [],
                tradeSuggestions: [],
                swingPoints: [],
                summary: {}
            }
        };
        
        this.viewport = {
            startIndex: 0,
            endIndex: 150,  // Increased from 100 to show more candles
            candleWidth: 6,  // Slightly smaller for more visibility
            candleSpacing: 1,
            priceRange: { min: 0, max: 0 },
            volumeRange: { min: 0, max: 0 }
        };
        
        this.mouse = { x: 0, y: 0, isDown: false };
        this.crosshair = { visible: false, x: 0, y: 0 };
        this.selectedTimeframe = 'H1';
        this.indicators = {
            ma: true,
            rsi: false,
            macd: false,
            bollinger: false,
            volume: true,
            choch: true,
            bos: true,
            fvg: true,
            fibonacci: false,
            volumeProfile: false,
            multiTimeframe: false
        };
        
        // Initialize prediction tracker with active predictions array
        this.predictionTracker = { 
            wins: 0, 
            losses: 0, 
            total: 0, 
            history: [],
            activePredictions: []  // Track ongoing CHoCH predictions
        };
        
        this.setupCanvas();
        this.bindEvents();
    }
    
    setupCanvas() {
        // Set canvas size
        this.canvas.width = this.options.width;
        this.canvas.height = this.options.height;
        
        // Set up device pixel ratio for sharp rendering
        const dpr = window.devicePixelRatio || 1;
        const rect = this.canvas.getBoundingClientRect();
        
        this.canvas.width = rect.width * dpr;
        this.canvas.height = rect.height * dpr;
        this.ctx.scale(dpr, dpr);
        
        this.canvas.style.width = rect.width + 'px';
        this.canvas.style.height = rect.height + 'px';
    }
    
    bindEvents() {
        // Mouse events
        this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
        this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.canvas.addEventListener('mouseup', (e) => this.onMouseUp(e));
        this.canvas.addEventListener('mouseleave', (e) => this.onMouseLeave(e));
        
        // Touch events for mobile
        this.canvas.addEventListener('touchmove', (e) => this.onTouchMove(e));
        this.canvas.addEventListener('touchstart', (e) => this.onTouchStart(e));
        this.canvas.addEventListener('touchend', (e) => this.onTouchEnd(e));
        
        // Wheel event for zooming
        this.canvas.addEventListener('wheel', (e) => this.onWheel(e));
        
        // Window resize
        window.addEventListener('resize', () => this.setupCanvas());
    }
    
    onMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        this.mouse.x = e.clientX - rect.left;
        this.mouse.y = e.clientY - rect.top;
        this.crosshair.visible = true;
        this.crosshair.x = this.mouse.x;
        this.crosshair.y = this.mouse.y;
        this.draw();
    }
    
    onMouseDown(e) {
        this.mouse.isDown = true;
    }
    
    onMouseUp(e) {
        this.mouse.isDown = false;
    }
    
    onMouseLeave(e) {
        this.crosshair.visible = false;
        this.draw();
    }
    
    onTouchMove(e) {
        e.preventDefault();
        const touch = e.touches[0];
        const rect = this.canvas.getBoundingClientRect();
        this.mouse.x = touch.clientX - rect.left;
        this.mouse.y = touch.clientY - rect.top;
        this.crosshair.visible = true;
        this.crosshair.x = this.mouse.x;
        this.crosshair.y = this.mouse.y;
        this.draw();
    }
    
    onTouchStart(e) {
        e.preventDefault();
        this.mouse.isDown = true;
    }
    
    onTouchEnd(e) {
        e.preventDefault();
        this.mouse.isDown = false;
    }
    
    onWheel(e) {
        e.preventDefault();
        // Zoom functionality
        const delta = e.deltaY > 0 ? 1 : -1;
        this.zoom(delta);
    }
    
    zoom(direction) {
        const zoomSpeed = 0.1;
        const newWidth = this.viewport.candleWidth * (1 + direction * zoomSpeed);
        
        if (newWidth >= 4 && newWidth <= 20) {
            this.viewport.candleWidth = newWidth;
            this.draw();
        }
    }
    
    updateData(newData) {
        if (!newData || !newData.candles) return;
        
        // Update candles
        this.data.candles = newData.candles;
        
        // Update volume
        if (newData.volume) {
            this.data.volume = newData.volume;
        }
        
        // Update indicators
        if (newData.indicators) {
            this.data.indicators = { ...this.data.indicators, ...newData.indicators };
        }
        
        // Update trades
        if (newData.trades) {
            this.data.trades = newData.trades;
        }
        
        // Update levels (SL/TP)
        if (newData.levels) {
            this.data.levels = newData.levels;
        }
        
        // Update price action patterns
        if (newData.priceAction) {
            this.data.priceAction = {
                fvgs: newData.priceAction.fvgs || [],
                zones: newData.priceAction.zones || [],
                bos: newData.priceAction.bos || [],
                orderBlocks: newData.priceAction.orderBlocks || [],
                liquiditySweeps: newData.priceAction.liquiditySweeps || [],
                tradeSuggestions: newData.priceAction.tradeSuggestions || [],
                swingPoints: newData.priceAction.swingPoints || [],
                summary: newData.priceAction.summary || {}
            };
            
            // Check for high-urgency trade alerts
            this.checkTradeAlerts();
        }
        
        this.calculateViewport();
        this.draw();
    }
    
    addCandle(candle) {
        this.data.candles.push(candle);
        
        // Keep only last 500 candles for performance
        if (this.data.candles.length > 500) {
            this.data.candles.shift();
        }
        
        this.calculateViewport();
        this.draw();
    }
    
    calculateViewport() {
        if (this.data.candles.length === 0) return;
        
        const visibleCandles = this.data.candles.slice(
            this.viewport.startIndex,
            this.viewport.endIndex
        );
        
        if (visibleCandles.length === 0) return;
        
        // Calculate price range
        const prices = visibleCandles.flatMap(c => [c.high, c.low]);
        this.viewport.priceRange.min = Math.min(...prices);
        this.viewport.priceRange.max = Math.max(...prices);
        
        // Calculate volume range
        if (this.data.volume.length > 0) {
            const visibleVolume = this.data.volume.slice(
                this.viewport.startIndex,
                this.viewport.endIndex
            );
            this.viewport.volumeRange.max = Math.max(...visibleVolume);
        }
    }
    
    draw() {
        const { width, height } = this.canvas;
        
        // Clear canvas
        this.ctx.fillStyle = this.options.backgroundColor;
        this.ctx.fillRect(0, 0, width, height);
        
        if (this.data.candles.length === 0) {
            this.drawNoDataMessage();
            return;
        }
        
        // Draw grid
        this.drawGrid();
        
        // Draw volume
        if (this.indicators.volume) {
            this.drawVolume();
        }
        
        // Draw candlesticks
        this.drawCandlesticks();
        
        // Draw indicators
        if (this.indicators.ma) {
            this.drawMovingAverages();
        }
        
        if (this.indicators.bollinger) {
            this.drawBollingerBands();
        }
        
        // Draw trades
        this.drawTrades();
        
        // Draw levels (SL/TP)
        this.drawLevels();
        
        // Draw price action patterns (FVGs, Supply/Demand, BOS)
        this.drawPriceAction();
        
        // Draw prediction outcome markers (✓/✗) for resolved predictions
        this.drawPredictionOutcomeMarkers();
        
        // Draw Fibonacci (independent of priceAction toggle)
        this.drawFibonacci();
        
        // Draw Volume Profile
        this.drawVolumeProfile();
        
        // Draw Multi-Timeframe Alignment
        this.drawMultiTimeframeAlignment();
        
        // Draw crosshair
        if (this.crosshair.visible) {
            this.drawCrosshair();
        }
        
        // Draw time and price labels
        this.drawLabels();
    }
    
    drawGrid() {
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7; // 70% for price, 30% for volume
        
        this.ctx.strokeStyle = this.options.gridColor;
        this.ctx.lineWidth = 1;
        
        // Horizontal grid lines
        const horizontalLines = 10;
        for (let i = 0; i <= horizontalLines; i++) {
            const y = (chartHeight / horizontalLines) * i;
            this.ctx.beginPath();
            this.ctx.moveTo(0, y);
            this.ctx.lineTo(width, y);
            this.ctx.stroke();
        }
        
        // Vertical grid lines
        const verticalLines = 20;
        for (let i = 0; i <= verticalLines; i++) {
            const x = (width / verticalLines) * i;
            this.ctx.beginPath();
            this.ctx.moveTo(x, 0);
            this.ctx.lineTo(x, chartHeight);
            this.ctx.stroke();
        }
    }
    
    drawCandlesticks() {
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const chartWidth = width - 60; // Leave space for labels
        
        const visibleCandles = this.data.candles.slice(
            this.viewport.startIndex,
            this.viewport.endIndex
        );
        
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        const candleWidth = this.viewport.candleWidth;
        const candleSpacing = this.viewport.candleSpacing;
        
        visibleCandles.forEach((candle, index) => {
            const x = 60 + index * (candleWidth + candleSpacing);
            
            const yHigh = chartHeight - ((candle.high - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yLow = chartHeight - ((candle.low - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yOpen = chartHeight - ((candle.open - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yClose = chartHeight - ((candle.close - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            const isUp = candle.close >= candle.open;
            const color = isUp ? this.options.upColor : this.options.downColor;
            
            // Draw candle body with enhanced visibility
            this.ctx.fillStyle = color;
            const bodyTop = Math.min(yOpen, yClose);
            const bodyHeight = Math.abs(yClose - yOpen);
            const enhancedCandleWidth = Math.max(candleWidth * 1.2, 6); // Make candles 20% wider, minimum 6px
            
            if (bodyHeight > 0) {
                // Draw main body
                this.ctx.fillRect(x - enhancedCandleWidth/2, bodyTop, enhancedCandleWidth, bodyHeight);
                
                // Add subtle border for better definition
                this.ctx.strokeStyle = isUp ? '#16a34a' : '#dc2626';
                this.ctx.lineWidth = 1;
                this.ctx.strokeRect(x - enhancedCandleWidth/2, bodyTop, enhancedCandleWidth, bodyHeight);
            } else {
                // Doji candle - make it more visible
                this.ctx.strokeStyle = color;
                this.ctx.lineWidth = 2;
                this.ctx.beginPath();
                this.ctx.moveTo(x - enhancedCandleWidth/2, bodyTop);
                this.ctx.lineTo(x + enhancedCandleWidth/2, bodyTop);
                this.ctx.stroke();
            }
            
            // Draw wicks with enhanced thickness
            this.ctx.strokeStyle = color;
            this.ctx.lineWidth = 2; // Thicker wicks
            this.ctx.beginPath();
            this.ctx.moveTo(x, yHigh);
            this.ctx.lineTo(x, yLow);
            this.ctx.stroke();
        });
    }
    
    drawMovingAverages() {
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const chartWidth = width - 60;
        
        const maTypes = ['ma20', 'ma50', 'ma200'];
        const colors = this.options.maColors;
        
        maTypes.forEach((maType, index) => {
            const maData = this.data.indicators[maType];
            if (!maData || maData.length === 0) return;
            
            const visibleMA = maData.slice(
                this.viewport.startIndex,
                this.viewport.endIndex
            );
            
            // Enhanced moving average styling
            this.ctx.strokeStyle = colors[index];
            this.ctx.lineWidth = maType === 'ma20' ? 3 : (maType === 'ma50' ? 2.5 : 2); // Thicker lines for shorter periods
            this.ctx.lineCap = 'round';
            this.ctx.lineJoin = 'round';
            this.ctx.beginPath();
            
            visibleMA.forEach((value, maIndex) => {
                if (value === null || value === undefined) return;
                
                const x = 60 + maIndex * (this.viewport.candleWidth + this.viewport.candleSpacing);
                const y = chartHeight - ((value - this.viewport.priceRange.min) / 
                    (this.viewport.priceRange.max - this.viewport.priceRange.min)) * chartHeight;
                
                if (maIndex === 0) {
                    this.ctx.moveTo(x, y);
                } else {
                    this.ctx.lineTo(x, y);
                }
            });
            
            this.ctx.stroke();
        });
    }
    
    drawBollingerBands() {
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const bb = this.data.indicators.bb;
        
        if (!bb.upper || !bb.middle || !bb.lower) return;
        
        const visibleBB = {
            upper: bb.upper.slice(this.viewport.startIndex, this.viewport.endIndex),
            middle: bb.middle.slice(this.viewport.startIndex, this.viewport.endIndex),
            lower: bb.lower.slice(this.viewport.startIndex, this.viewport.endIndex)
        };
        
        // Draw upper band
        this.drawLine(visibleBB.upper, '#7c3aed', chartHeight);
        
        // Draw middle band
        this.drawLine(visibleBB.middle, '#00d4ff', chartHeight);
        
        // Draw lower band
        this.drawLine(visibleBB.lower, '#7c3aed', chartHeight);
        
        // Fill between bands
        this.ctx.fillStyle = 'rgba(124, 58, 237, 0.1)';
        this.ctx.beginPath();
        
        visibleBB.upper.forEach((value, index) => {
            if (value === null || value === undefined) return;
            
            const x = 60 + index * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((value - this.viewport.priceRange.min) / 
                (this.viewport.priceRange.max - this.viewport.priceRange.min)) * chartHeight;
            
            if (index === 0) {
                this.ctx.moveTo(x, y);
            } else {
                this.ctx.lineTo(x, y);
            }
        });
        
        // Draw lower band to close the fill
        for (let i = visibleBB.lower.length - 1; i >= 0; i--) {
            const value = visibleBB.lower[i];
            if (value === null || value === undefined) continue;
            
            const x = 60 + i * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((value - this.viewport.priceRange.min) / 
                (this.viewport.priceRange.max - this.viewport.priceRange.min)) * chartHeight;
            
            this.ctx.lineTo(x, y);
        }
        
        this.ctx.closePath();
        this.ctx.fill();
    }
    
    drawLine(data, color, chartHeight) {
        if (!data || data.length === 0) return;
        
        this.ctx.strokeStyle = color;
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        
        data.forEach((value, index) => {
            if (value === null || value === undefined) return;
            
            const x = 60 + index * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((value - this.viewport.priceRange.min) / 
                (this.viewport.priceRange.max - this.viewport.priceRange.min)) * chartHeight;
            
            if (index === 0) {
                this.ctx.moveTo(x, y);
            } else {
                this.ctx.lineTo(x, y);
            }
        });
        
        this.ctx.stroke();
    }
    
    drawVolume() {
        const { width, height } = this.canvas;
        const volumeHeight = height * 0.25;
        const volumeTop = height * 0.75;
        
        const visibleVolume = this.data.volume.slice(
            this.viewport.startIndex,
            this.viewport.endIndex
        );
        
        const maxVolume = this.viewport.volumeRange.max;
        
        visibleVolume.forEach((volume, index) => {
            if (volume === null || volume === undefined) return;
            
            const x = 60 + index * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const barHeight = (volume / maxVolume) * volumeHeight;
            const y = volumeTop + (volumeHeight - barHeight);
            const enhancedBarWidth = Math.max(this.viewport.candleWidth * 1.2, 6); // Match candle width
            
            // Get corresponding candle for color
            const candle = this.data.candles[index + this.viewport.startIndex];
            const baseColor = candle && candle.close >= candle.open ? 
                this.options.upColor : this.options.downColor;
            
            // Enhanced volume bars with better visibility
            this.ctx.fillStyle = baseColor + '66'; // Increased opacity from 40% to 40% (66 in hex)
            this.ctx.fillRect(x - enhancedBarWidth/2, y, enhancedBarWidth, barHeight);
            
            // Add border for better definition
            this.ctx.strokeStyle = baseColor + '99'; // Even more opaque border
            this.ctx.lineWidth = 1;
            this.ctx.strokeRect(x - enhancedBarWidth/2, y, enhancedBarWidth, barHeight);
        });
    }
    
    drawTrades() {
        const { height } = this.canvas;
        const chartHeight = height * 0.7;
        
        this.data.trades.forEach(trade => {
            const x = 60 + trade.candleIndex * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((trade.price - this.viewport.priceRange.min) / 
                (this.viewport.priceRange.max - this.viewport.priceRange.min)) * chartHeight;
            
            // Draw trade marker
            this.ctx.fillStyle = trade.type === 'BUY' ? '#10b981' : '#ef4444';
            this.ctx.beginPath();
            this.ctx.arc(x, y, 6, 0, Math.PI * 2);
            this.ctx.fill();
            
            // Draw trade label
            this.ctx.fillStyle = '#ffffff';
            this.ctx.font = '10px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.fillText(trade.type, x, y - 10);
        });
    }
    
    drawLevels() {
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        
        this.data.levels.forEach(level => {
            const y = chartHeight - ((level.price - this.viewport.priceRange.min) / 
                (this.viewport.priceRange.max - this.viewport.priceRange.min)) * chartHeight;
            
            // Draw level line
            this.ctx.strokeStyle = level.color;
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([5, 5]);
            this.ctx.beginPath();
            this.ctx.moveTo(0, y);
            this.ctx.lineTo(width, y);
            this.ctx.stroke();
            this.ctx.setLineDash([]);
            
            // Draw level label
            this.ctx.fillStyle = level.color;
            this.ctx.font = '11px Arial';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(`${level.label}: ${level.price.toFixed(2)}`, 10, y - 5);
        });
    }
    
    drawPriceAction() {
        // Draw price action patterns based on individual toggles
        if (this.indicators.fvg) {
            this.drawFVGs();
        }
        if (this.indicators.bos || this.indicators.choch) {
            this.drawBOS();
        }
        if (this.indicators.choch) {
            this.drawCHoCHTrendLines();
            // Update HTML panel below chart
            this.updateCHoCHAnalysisPanel();
        }
        // Supporting elements
        if (this.indicators.choch || this.indicators.bos || this.indicators.fvg) {
            this.drawSupplyDemandZones();
            this.drawSwingPoints();
            this.drawLiquiditySweeps();
            this.drawOrderBlocks();
        }
    }
    
    drawFVGs() {
        // Draw Fair Value Gaps (FVG) on the chart
        const fvgs = this.data.priceAction?.fvgs || [];
        if (fvgs.length === 0) return;
        
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        
        fvgs.forEach(fvg => {
            // Check if FVG is visible in current viewport
            if (fvg.index < this.viewport.startIndex || fvg.index > this.viewport.endIndex) return;
            
            const x = 60 + (fvg.index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
            
            const yTop = chartHeight - ((fvg.top_price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yBottom = chartHeight - ((fvg.bottom_price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            // FVG styling - use distinct Slate/Dark colors (not green/red)
            const isBullish = fvg.type === 'bullish';
            const isInverse = fvg.is_inverse;
            
            // Color scheme: Dark Slate Blue for bullish FVG, Dark Slate Purple for bearish FVG
            const baseColor = isBullish ? 'rgba(15, 23, 42, ' : 'rgba(59, 7, 100, ';  // Slate / Dark Purple
            const opacity = isInverse ? '0.25)' : '0.45)';
            const borderOpacity = isInverse ? '0.5)' : '0.9)';
            const labelColor = isBullish ? '#475569' : '#7e22ce';  // Slate / Purple
            
            // Draw FVG rectangle
            this.ctx.fillStyle = baseColor + opacity;
            this.ctx.fillRect(x - 2, yTop, 4, yBottom - yTop);
            
            // Draw FVG borders
            this.ctx.strokeStyle = baseColor + borderOpacity;
            this.ctx.lineWidth = isInverse ? 1.5 : 2.5;
            this.ctx.setLineDash(isInverse ? [3, 2] : []);
            
            this.ctx.beginPath();
            this.ctx.moveTo(x - 2, yTop);
            this.ctx.lineTo(x + 2, yTop);
            this.ctx.moveTo(x - 2, yBottom);
            this.ctx.lineTo(x + 2, yBottom);
            this.ctx.stroke();
            
            // Reset line dash
            this.ctx.setLineDash([]);
            
            // Draw label for significant FVGs
            if (!fvg.is_filled && Math.abs(fvg.top_price - fvg.bottom_price) > priceRange * 0.01) {
                this.ctx.fillStyle = labelColor;
                this.ctx.font = 'bold 9px Arial';
                this.ctx.textAlign = 'center';
                this.ctx.fillText(
                    isInverse ? 'iFVG' : 'FVG',
                    x,
                    yTop - 5
                );
            }
        });
    }
    
    drawSupplyDemandZones() {
        // Draw Supply and Demand zones
        const zones = this.data.priceAction?.zones || [];
        if (zones.length === 0) return;
        
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        
        zones.forEach(zone => {
            // Only show active zones
            if (!zone.is_active) return;
            
            // Check if zone is in visible range
            if (zone.index < this.viewport.startIndex - 20 || zone.index > this.viewport.endIndex) return;
            
            const x = zone.index >= this.viewport.startIndex 
                ? 60 + (zone.index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing)
                : 60;
            
            const yTop = chartHeight - ((zone.top_price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yBottom = chartHeight - ((zone.bottom_price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yBase = chartHeight - ((zone.base_price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            const isSupply = zone.type === 'supply';
            
            // Zone colors: Red for supply, Green for demand
            const zoneColor = isSupply 
                ? 'rgba(239, 68, 68, 0.15)' 
                : 'rgba(34, 197, 94, 0.15)';
            const borderColor = isSupply 
                ? 'rgba(239, 68, 68, 0.6)' 
                : 'rgba(34, 197, 94, 0.6)';
            
            // Draw zone rectangle extending to the right edge
            const zoneWidth = width - x;
            this.ctx.fillStyle = zoneColor;
            this.ctx.fillRect(x, yTop, zoneWidth, yBottom - yTop);
            
            // Draw zone borders
            this.ctx.strokeStyle = borderColor;
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([5, 3]);
            
            this.ctx.beginPath();
            this.ctx.moveTo(x, yTop);
            this.ctx.lineTo(width, yTop);
            this.ctx.moveTo(x, yBottom);
            this.ctx.lineTo(width, yBottom);
            this.ctx.stroke();
            
            // Draw base line (solid)
            this.ctx.setLineDash([]);
            this.ctx.lineWidth = 2;
            this.ctx.beginPath();
            this.ctx.moveTo(x, yBase);
            this.ctx.lineTo(width, yBase);
            this.ctx.stroke();
            
            // Draw zone label
            this.ctx.fillStyle = isSupply ? '#ef4444' : '#22c55e';
            this.ctx.font = 'bold 10px Arial';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(
                `${isSupply ? 'SUPPLY' : 'DEMAND'} (${zone.touches} touches)`,
                x + 5,
                yTop - 8
            );
        });
    }
    
    drawBOS() {
        // Draw Break of Structure (BOS) and Change of Character (CHoCH)
        const bosPoints = this.data.priceAction?.bos || [];
        if (bosPoints.length === 0) return;
        
        // Use logical canvas dimensions
        const width = this.canvas.width / (window.devicePixelRatio || 1);
        const height = this.canvas.height / (window.devicePixelRatio || 1);
        const chartHeight = height * 0.7;
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        
        if (priceRange === 0) return;
        
        // Get current timestamp for recency calculation
        const currentTime = Date.now();
        const RECENT_THRESHOLD = 5 * 60 * 1000; // 5 minutes in ms
        
        // Group BOS points by direction for trend analysis
        const chochPoints = bosPoints.filter(b => b.type === 'choch');
        
        // Sort by index to process in order
        const sortedPoints = [...bosPoints].sort((a, b) => a.index - b.index);
        
        // Find the most recent BOS/CHoCH for highlighting
        const mostRecent = sortedPoints[sortedPoints.length - 1];
        const secondRecent = sortedPoints.length > 1 ? sortedPoints[sortedPoints.length - 2] : null;
        
        // PULSE ANIMATION: Calculate pulse radius based on time
        const pulsePhase = (currentTime % 2000) / 2000; // 2-second cycle
        const pulseRadius = 15 + pulsePhase * 10; // Expands from 15 to 25
        const pulseOpacity = 1 - pulsePhase; // Fades out
        
        sortedPoints.forEach(bos => {
            // Check if BOS point is visible
            if (bos.index < this.viewport.startIndex || bos.index > this.viewport.endIndex) return;
            
            const x = 60 + (bos.index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((bos.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            // ENHANCED: More vibrant colors for better visibility
            const isBOS = bos.type === 'bos';
            const isBullish = bos.direction === 'bullish';
            const strength = bos.strength || 50;
            const isMostRecent = bos.index === mostRecent.index;
            const isSecondRecent = secondRecent && bos.index === secondRecent.index;
            const isRecent = isMostRecent || isSecondRecent;
            
            // Calculate recency (how many candles ago)
            const candlesAgo = this.viewport.endIndex - bos.index;
            const isVeryRecent = candlesAgo <= 3;
            
            // Vibrant colors - Blue for bullish, Purple for bearish
            const bullColor = isMostRecent ? '#3b82f6' : (isSecondRecent ? '#60a5fa' : '#93c5fd');
            const bearColor = isMostRecent ? '#a855f7' : (isSecondRecent ? '#c084fc' : '#d8b4fe');
            const mainColor = isBullish ? bullColor : bearColor;
            
            // Calculate size - larger for recent and high strength
            const baseSize = isBOS ? 14 : 12;
            const recentMultiplier = isMostRecent ? 1.5 : (isSecondRecent ? 1.2 : 1.0);
            const strengthMultiplier = 0.6 + (strength / 100);
            const size = baseSize * recentMultiplier * strengthMultiplier;
            
            // PULSE ANIMATION: Draw expanding ring for most recent signal
            if (isMostRecent && isVeryRecent) {
                // Outer pulse ring
                this.ctx.strokeStyle = isBullish 
                    ? `rgba(59, 130, 246, ${pulseOpacity * 0.6})`
                    : `rgba(168, 85, 247, ${pulseOpacity * 0.6})`;
                this.ctx.lineWidth = 3;
                this.ctx.beginPath();
                this.ctx.arc(x, y, pulseRadius, 0, Math.PI * 2);
                this.ctx.stroke();
                
                // Inner pulse ring
                this.ctx.strokeStyle = isBullish 
                    ? `rgba(59, 130, 246, ${pulseOpacity * 0.3})`
                    : `rgba(168, 85, 247, ${pulseOpacity * 0.3})`;
                this.ctx.lineWidth = 2;
                this.ctx.beginPath();
                this.ctx.arc(x, y, pulseRadius * 0.7, 0, Math.PI * 2);
                this.ctx.stroke();
            }
            
            // Draw outer glow for recent signals
            if (isRecent) {
                const glowSize = size * 2;
                const glowGradient = this.ctx.createRadialGradient(x, y, 0, x, y, glowSize);
                glowGradient.addColorStop(0, isBullish 
                    ? `rgba(59, 130, 246, ${isMostRecent ? 0.5 : 0.3})` 
                    : `rgba(168, 85, 247, ${isMostRecent ? 0.5 : 0.3})`);
                glowGradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
                
                this.ctx.fillStyle = glowGradient;
                this.ctx.beginPath();
                this.ctx.arc(x, y, glowSize, 0, Math.PI * 2);
                this.ctx.fill();
            }
            
            // Draw connecting line to previous swing (for CHoCH)
            if (!isBOS && bos.previous_swing) {
                const prevSwingY = chartHeight - ((bos.previous_swing - this.viewport.priceRange.min) / priceRange) * chartHeight;
                const priceDiff = Math.abs(bos.price - bos.previous_swing);
                const pips = (priceDiff * 100).toFixed(1); // Assuming gold format
                
                // Draw trend line with price label
                this.ctx.strokeStyle = isBullish 
                    ? `rgba(59, 130, 246, ${isRecent ? 0.8 : 0.5})` 
                    : `rgba(168, 85, 247, ${isRecent ? 0.8 : 0.5})`;
                this.ctx.lineWidth = isRecent ? 3 : 2;
                this.ctx.setLineDash([5, 3]);
                this.ctx.beginPath();
                this.ctx.moveTo(x - 25, prevSwingY);
                this.ctx.lineTo(x, y);
                this.ctx.stroke();
                this.ctx.setLineDash([]);
                
                // Draw pips label at midpoint
                const midX = (x - 25 + x) / 2;
                const midY = (prevSwingY + y) / 2;
                this.ctx.fillStyle = isBullish ? '#3b82f6' : '#a855f7';
                this.ctx.font = 'bold 9px Arial';
                this.ctx.textAlign = 'center';
                this.ctx.fillText(`${pips}p`, midX, midY - 5);
                
                // Draw arrow at end
                const angle = Math.atan2(y - prevSwingY, x - (x - 25));
                const arrowLength = 8;
                this.ctx.fillStyle = mainColor;
                this.ctx.beginPath();
                this.ctx.moveTo(x, y);
                this.ctx.lineTo(
                    x - arrowLength * Math.cos(angle - Math.PI / 6),
                    y - arrowLength * Math.sin(angle - Math.PI / 6)
                );
                this.ctx.lineTo(
                    x - arrowLength * Math.cos(angle + Math.PI / 6),
                    y - arrowLength * Math.sin(angle + Math.PI / 6)
                );
                this.ctx.closePath();
                this.ctx.fill();
            }
            
            if (isBOS) {
                // BOS Circle with enhanced styling
                const gradient = this.ctx.createRadialGradient(x, y, 0, x, y, size);
                gradient.addColorStop(0, isBullish ? '#60a5fa' : '#c084fc');
                gradient.addColorStop(0.5, isBullish ? '#3b82f6' : '#a855f7');
                gradient.addColorStop(1, isBullish ? 'rgba(59, 130, 246, 0.3)' : 'rgba(168, 85, 247, 0.3)');
                
                this.ctx.fillStyle = gradient;
                this.ctx.beginPath();
                this.ctx.arc(x, y, size, 0, Math.PI * 2);
                this.ctx.fill();
                
                // Animated border for recent
                this.ctx.strokeStyle = mainColor;
                this.ctx.lineWidth = isMostRecent ? 4 : (isSecondRecent ? 3 : 2);
                this.ctx.stroke();
                
                // Inner dot
                this.ctx.fillStyle = '#ffffff';
                this.ctx.beginPath();
                this.ctx.arc(x, y, size * 0.3, 0, Math.PI * 2);
                this.ctx.fill();
            } else {
                // CHoCH Diamond with enhanced styling
                const gradient = this.ctx.createRadialGradient(x, y, 0, x, y, size);
                gradient.addColorStop(0, isBullish ? '#60a5fa' : '#c084fc');
                gradient.addColorStop(0.5, isBullish ? '#3b82f6' : '#a855f7');
                gradient.addColorStop(1, isBullish ? 'rgba(59, 130, 246, 0.2)' : 'rgba(168, 85, 247, 0.2)');
                
                this.ctx.fillStyle = gradient;
                this.ctx.beginPath();
                this.ctx.moveTo(x, y - size);
                this.ctx.lineTo(x + size, y);
                this.ctx.lineTo(x, y + size);
                this.ctx.lineTo(x - size, y);
                this.ctx.closePath();
                this.ctx.fill();
                
                // Animated border
                this.ctx.strokeStyle = mainColor;
                this.ctx.lineWidth = isMostRecent ? 4 : (isSecondRecent ? 3 : 2);
                this.ctx.stroke();
                
                // Inner dot
                this.ctx.fillStyle = '#ffffff';
                this.ctx.beginPath();
                this.ctx.arc(x, y, size * 0.25, 0, Math.PI * 2);
                this.ctx.fill();
            }
            
            // Draw label with enhanced background
            const labelText = isBOS ? 'BOS' : 'CHoCH';
            const labelY = y - size - 15;
            
            // Label background with glow for recent
            this.ctx.font = isMostRecent ? 'bold 13px Arial' : (isSecondRecent ? 'bold 12px Arial' : 'bold 11px Arial');
            const labelWidth = this.ctx.measureText(labelText).width;
            
            if (isRecent) {
                // Glow effect for background
                this.ctx.shadowColor = mainColor;
                this.ctx.shadowBlur = isMostRecent ? 15 : 10;
            }
            
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
            this.ctx.fillRect(x - labelWidth/2 - 6, labelY - 12, labelWidth + 12, 18);
            
            this.ctx.shadowBlur = 0;
            
            // Label text
            this.ctx.fillStyle = mainColor;
            this.ctx.textAlign = 'center';
            this.ctx.fillText(labelText, x, labelY);
            
            // Direction arrow above label
            const arrowY = labelY - 10;
            this.ctx.fillStyle = mainColor;
            this.ctx.font = isMostRecent ? '12px Arial' : '10px Arial';
            this.ctx.fillText(isBullish ? '▲' : '▼', x, arrowY);
            
            // NEW: Draw candles-ago indicator for recent signals
            if (candlesAgo <= 5) {
                const timeY = y + size + 20;
                this.ctx.font = 'bold 9px Arial';
                this.ctx.fillStyle = candlesAgo <= 2 ? '#fbbf24' : '#94a3b8';
                this.ctx.fillText(`${candlesAgo} bars`, x, timeY);
            }
            
            // Enhanced strength/confluence display
            if (strength > 60 || isRecent) {
                const strengthY = y + size + (candlesAgo <= 5 ? 32 : 20);
                this.ctx.font = isMostRecent ? 'bold 11px Arial' : 'bold 10px Arial';
                this.ctx.fillStyle = isMostRecent ? '#fbbf24' : mainColor;
                this.ctx.fillText(`${Math.round(strength)}%`, x, strengthY);
            }
            
            // NEW: Draw confluence indicators as small icons
            let confluenceX = x + size + 8;
            const confluenceY = y - 5;
            
            // FVG confluence
            if (bos.fvg_confluence) {
                this.ctx.fillStyle = '#f59e0b';
                this.ctx.font = 'bold 8px Arial';
                this.ctx.textAlign = 'left';
                this.ctx.fillText('F', confluenceX, confluenceY);
                confluenceX += 10;
            }
            
            // Volume confirmation
            if (bos.volume_confirmed) {
                this.ctx.fillStyle = '#22c55e';
                this.ctx.font = 'bold 8px Arial';
                this.ctx.textAlign = 'left';
                this.ctx.fillText('V', confluenceX, confluenceY);
                confluenceX += 10;
            }
            
            // High confluence star
            if (bos.confluence_score > 80) {
                this.ctx.fillStyle = '#ec4899';
                this.ctx.font = 'bold 10px Arial';
                this.ctx.textAlign = 'left';
                this.ctx.fillText('★', confluenceX, confluenceY);
            }
        });
        
        // Draw enhanced trend lines connecting consecutive CHoCH points
        this.drawCHoCHTrendLines(chochPoints, chartHeight, priceRange);
        
        // Draw CHoCH predictive analysis
        this.drawCHoCHPrediction(chochPoints, chartHeight, priceRange, width);
    }
    
    drawCHoCHPrediction(chochPoints, chartHeight, priceRange, canvasWidth) {
        // Analyze CHoCH patterns to predict market direction
        if (chochPoints.length === 0) return;
        
        // Sort by index
        const sorted = [...chochPoints].sort((a, b) => a.index - b.index);
        
        // Get recent CHoCH points (last 3-5)
        const recentChoCH = sorted.slice(-5);
        const mostRecent = sorted[sorted.length - 1];
        
        // Analyze CHoCH sequence pattern
        const bullishCount = recentChoCH.filter(c => c.direction === 'bullish').length;
        const bearishCount = recentChoCH.filter(c => c.direction === 'bearish').length;
        
        // Determine market structure phase
        let phase = 'NEUTRAL';
        let prediction = '';
        let targetDirection = '';
        let confidence = 50;
        
        if (recentChoCH.length >= 2) {
            const last = recentChoCH[recentChoCH.length - 1];
            const prev = recentChoCH[recentChoCH.length - 2];
            
            if (last.direction === prev.direction) {
                // Consecutive same direction = Strong trend continuation
                phase = last.direction === 'bullish' ? 'BULLISH TREND' : 'BEARISH TREND';
                prediction = last.direction === 'bullish' ? 'EXPECT HIGHER HIGH' : 'EXPECT LOWER LOW';
                targetDirection = last.direction;
                confidence = 70 + (bullishCount > bearishCount ? bullishCount : bearishCount) * 5;
            } else {
                // Direction changed = Potential reversal or correction
                phase = 'TRANSITION';
                if (last.price > prev.price) {
                    prediction = 'BULLISH REVERSAL';
                    targetDirection = 'bullish';
                } else {
                    prediction = 'BEARISH REVERSAL';
                    targetDirection = 'bearish';
                }
                confidence = 60;
            }
        }
        
        // Initialize prediction tracker if not exists
        if (!this.predictionTracker) {
            this.predictionTracker = { wins: 0, losses: 0, total: 0, history: [], activePredictions: [] };
        }
        
        // Track new prediction if this is a fresh CHoCH
        this.trackNewPrediction(mostRecent, targetDirection, prediction);
        
        // Evaluate active predictions against current price
        this.evaluateActivePredictions();
        
        // ENHANCED: Larger panel with better positioning (top left, not overlapping)
        const panelX = 70;  // Moved to left side
        const panelY = 25;
        const panelWidth = 220;  // Wider panel
        const panelHeight = 90;  // Taller panel
        
        // Panel background with higher contrast
        this.ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';  // Darker blue-tinted background
        this.ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
        
        // Panel border with glow effect
        const borderColor = targetDirection === 'bullish' ? 'rgba(59, 130, 246, 1)' : 
                           targetDirection === 'bearish' ? 'rgba(168, 85, 247, 1)' : 'rgba(148, 163, 184, 0.8)';
        this.ctx.strokeStyle = borderColor;
        this.ctx.lineWidth = 3;  // Thicker border
        this.ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);
        
        // Inner glow line
        this.ctx.strokeStyle = targetDirection === 'bullish' ? 'rgba(59, 130, 246, 0.3)' : 
                               targetDirection === 'bearish' ? 'rgba(168, 85, 247, 0.3)' : 'rgba(148, 163, 184, 0.2)';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(panelX + 2, panelY + 2, panelWidth - 4, panelHeight - 4);
        
        // ENHANCED: Title - LARGER and BOLDER
        this.ctx.fillStyle = '#fbbf24';
        this.ctx.font = 'bold 14px Arial';  // Increased from 11px
        this.ctx.textAlign = 'left';
        this.ctx.fillText('📊 CHoCH ANALYSIS', panelX + 10, panelY + 22);
        
        // ENHANCED: Phase - LARGER, BOLDER, with background highlight
        const phaseY = panelY + 45;
        this.ctx.fillStyle = targetDirection === 'bullish' ? 'rgba(59, 130, 246, 0.2)' : 
                            targetDirection === 'bearish' ? 'rgba(168, 85, 247, 0.2)' : 'rgba(148, 163, 184, 0.2)';
        this.ctx.fillRect(panelX + 8, phaseY - 16, panelWidth - 16, 22);
        
        this.ctx.fillStyle = targetDirection === 'bullish' ? '#3b82f6' : 
                            targetDirection === 'bearish' ? '#a855f7' : '#e2e8f0';
        this.ctx.font = 'bold 15px Arial';  // Increased from 12px
        this.ctx.fillText(phase, panelX + 12, phaseY);
        
        // ENHANCED: Prediction - BOLDER, more visible
        this.ctx.fillStyle = '#ffffff';
        this.ctx.font = 'bold 12px Arial';  // Increased from 10px, now bold
        this.ctx.fillText(prediction, panelX + 10, panelY + 68);
        
        // ENHANCED: Confidence bar - larger, more visible
        const barY = panelY + 78;
        const barWidth = 140;
        const barHeight = 8;  // Increased from 6px
        
        // Bar background
        this.ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
        this.ctx.fillRect(panelX + 10, barY, barWidth, barHeight);
        
        // Bar fill with gradient effect
        const barFill = Math.min(confidence, 100) / 100 * barWidth;
        const barGradient = this.ctx.createLinearGradient(panelX + 10, barY, panelX + 10 + barWidth, barY);
        if (targetDirection === 'bullish') {
            barGradient.addColorStop(0, '#1e40af');
            barGradient.addColorStop(1, '#3b82f6');
        } else if (targetDirection === 'bearish') {
            barGradient.addColorStop(0, '#7c3aed');
            barGradient.addColorStop(1, '#a855f7');
        } else {
            barGradient.addColorStop(0, '#475569');
            barGradient.addColorStop(1, '#94a3b8');
        }
        this.ctx.fillStyle = barGradient;
        this.ctx.fillRect(panelX + 10, barY, barFill, barHeight);
        
        // Bar border
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(panelX + 10, barY, barWidth, barHeight);
        
        // ENHANCED: Confidence % - BIGGER, BOLDER
        this.ctx.fillStyle = '#fbbf24';
        this.ctx.font = 'bold 13px Arial';  // Increased from 9px
        this.ctx.fillText(`${confidence}%`, panelX + 10 + barWidth + 8, barY + 7);
        
        // ENHANCED: Draw accuracy tracker below main panel
        this.drawPredictionTracker(panelX, panelY + panelHeight + 5, panelWidth);
        
        // Draw target projection from most recent CHoCH
        if (mostRecent && mostRecent.index >= this.viewport.startIndex && mostRecent.index <= this.viewport.endIndex) {
            const x = 60 + (mostRecent.index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((mostRecent.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            // Calculate projected target based on previous swing size
            const prevSwing = mostRecent.previous_swing;
            if (prevSwing) {
                const swingSize = Math.abs(mostRecent.price - prevSwing);
                const isBullish = mostRecent.direction === 'bullish';
                
                // 1.0x, 1.5x, 2.0x Fibonacci extension targets
                const targets = [1.0, 1.5, 2.0];
                const targetPrices = targets.map(t => 
                    isBullish ? mostRecent.price + (swingSize * t) : mostRecent.price - (swingSize * t)
                );
                
                // Draw target lines
                targetPrices.forEach((targetPrice, i) => {
                    const targetY = chartHeight - ((targetPrice - this.viewport.priceRange.min) / priceRange) * chartHeight;
                    
                    // Check if within view
                    if (targetY < 0 || targetY > chartHeight) return;
                    
                    // Target line
                    this.ctx.strokeStyle = isBullish 
                        ? `rgba(59, 130, 246, ${0.3 + i * 0.2})` 
                        : `rgba(168, 85, 247, ${0.3 + i * 0.2})`;
                    this.ctx.lineWidth = 1;
                    this.ctx.setLineDash([3, 6]);
                    this.ctx.beginPath();
                    this.ctx.moveTo(x, y);
                    this.ctx.lineTo(canvasWidth - 80, targetY);
                    this.ctx.stroke();
                    
                    // Target label
                    const labelMultiplier = targets[i];
                    this.ctx.fillStyle = isBullish ? '#60a5fa' : '#c084fc';
                    this.ctx.font = 'bold 9px Arial';
                    this.ctx.textAlign = 'left';
                    this.ctx.fillText(
                        `TP${i+1} ${labelMultiplier}x: ${targetPrice.toFixed(2)}`, 
                        canvasWidth - 75, 
                        targetY - 3
                    );
                    
                    // Draw horizontal dashed line across chart
                    this.ctx.strokeStyle = isBullish 
                        ? `rgba(59, 130, 246, 0.15)` 
                        : `rgba(168, 85, 247, 0.15)`;
                    this.ctx.lineWidth = 1;
                    this.ctx.setLineDash([8, 8]);
                    this.ctx.beginPath();
                    this.ctx.moveTo(x + 30, targetY);
                    this.ctx.lineTo(canvasWidth - 80, targetY);
                    this.ctx.stroke();
                });
                
                this.ctx.setLineDash([]);
                
                // Draw CHoCH to Target arrow
                const lastTargetY = chartHeight - ((targetPrices[0] - this.viewport.priceRange.min) / priceRange) * chartHeight;
                const arrowX = x + 20;
                const midY = (y + lastTargetY) / 2;
                
                this.ctx.strokeStyle = isBullish ? 'rgba(59, 130, 246, 0.6)' : 'rgba(168, 85, 247, 0.6)';
                this.ctx.lineWidth = 2;
                this.ctx.beginPath();
                this.ctx.moveTo(x + 5, y);
                this.ctx.lineTo(arrowX, midY);
                this.ctx.lineTo(x + 5, lastTargetY);
                this.ctx.stroke();
                
                // Draw arrow head
                this.ctx.fillStyle = isBullish ? '#3b82f6' : '#a855f7';
                this.ctx.beginPath();
                this.ctx.moveTo(arrowX, lastTargetY);
                this.ctx.lineTo(arrowX - 6, lastTargetY + (isBullish ? 8 : -8));
                this.ctx.lineTo(arrowX + 6, lastTargetY + (isBullish ? 8 : -8));
                this.ctx.closePath();
                this.ctx.fill();
                
                // ENHANCED: Auto-calculate position size based on CHoCH
                const stopDistance = Math.abs(mostRecent.price - prevSwing);
                const accountBalance = this.getAccountBalance(); // Get real balance from dashboard
                const riskPercent = 2; // 2% risk per trade
                const riskAmount = accountBalance * (riskPercent / 100);
                const pipValue = 10; // $10 per pip for standard lot
                const stopPips = (stopDistance * 100); // Convert to pips for gold
                const positionSize = (riskAmount / (stopPips * pipValue)).toFixed(2);
                const microLots = Math.max(0.01, Math.min(2.0, positionSize));
                
                // ENHANCED: Position panel - moved to right side to avoid overlap
                const posX = canvasWidth - 140;  // Right side of chart
                const posY = 25;
                const posWidth = 130;
                const posHeight = 80;
                
                this.ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
                this.ctx.fillRect(posX, posY, posWidth, posHeight);
                
                // Thicker border with glow
                this.ctx.strokeStyle = isBullish ? 'rgba(59, 130, 246, 1)' : 'rgba(168, 85, 247, 1)';
                this.ctx.lineWidth = 3;
                this.ctx.strokeRect(posX, posY, posWidth, posHeight);
                
                // Inner border
                this.ctx.strokeStyle = isBullish ? 'rgba(59, 130, 246, 0.3)' : 'rgba(168, 85, 247, 0.3)';
                this.ctx.lineWidth = 1;
                this.ctx.strokeRect(posX + 2, posY + 2, posWidth - 4, posHeight - 4);
                
                // Title - LARGER
                this.ctx.fillStyle = '#fbbf24';
                this.ctx.font = 'bold 12px Arial';
                this.ctx.textAlign = 'left';
                this.ctx.fillText('📐 POSITION', posX + 8, posY + 18);
                
                // Lot size - MUCH LARGER
                this.ctx.fillStyle = isBullish ? '#60a5fa' : '#c084fc';
                this.ctx.font = 'bold 22px Arial';
                this.ctx.fillText(`${microLots}`, posX + 8, posY + 45);
                this.ctx.font = 'bold 11px Arial';
                this.ctx.fillStyle = '#94a3b8';
                this.ctx.fillText('lots', posX + 65, posY + 45);
                
                // Stop distance - LARGER
                this.ctx.fillStyle = '#ffffff';
                this.ctx.font = 'bold 11px Arial';
                this.ctx.fillText(`SL: ${stopPips.toFixed(1)}p`, posX + 8, posY + 62);
                
                // Risk - LARGER
                this.ctx.fillText(`Risk: $${riskAmount.toFixed(0)}`, posX + 8, posY + 75);
                
                // ENHANCED: Check if price is following or rejecting projection
                const candles = this.data.candles || [];
                if (candles.length > 0) {
                    const currentCandle = candles[candles.length - 1];
                    const currentPrice = currentCandle.close;
                    const projectionLine = this.calculateProjectionLine(mostRecent, targetPrices[0], candles.length - 1, mostRecent.index);
                    const priceDiff = Math.abs(currentPrice - projectionLine);
                    const isFollowing = isBullish ? currentPrice >= mostRecent.price : currentPrice <= mostRecent.price;
                    const isOnTrack = priceDiff < (swingSize * 0.3); // Within 30% of swing
                    
                    // Status indicator - BIGGER, moved below position panel
                    const statusX = posX;
                    const statusY = posY + posHeight + 8;
                    const statusWidth = posWidth;
                    const statusHeight = 40;  // Taller
                    
                    this.ctx.fillStyle = isOnTrack ? 'rgba(34, 197, 94, 0.25)' : isFollowing ? 'rgba(251, 191, 36, 0.25)' : 'rgba(239, 68, 68, 0.25)';
                    this.ctx.fillRect(statusX, statusY, statusWidth, statusHeight);
                    
                    this.ctx.strokeStyle = isOnTrack ? 'rgba(34, 197, 94, 1)' : isFollowing ? 'rgba(251, 191, 36, 1)' : 'rgba(239, 68, 68, 1)';
                    this.ctx.lineWidth = 3;
                    this.ctx.strokeRect(statusX, statusY, statusWidth, statusHeight);
                    
                    // Status text - BIGGER
                    this.ctx.fillStyle = isOnTrack ? '#22c55e' : isFollowing ? '#fbbf24' : '#ef4444';
                    this.ctx.font = 'bold 14px Arial';
                    this.ctx.textAlign = 'center';
                    const statusText = isOnTrack ? '✓ ON TRACK' : isFollowing ? '⚠ FOLLOWING' : '✗ REJECTING';
                    this.ctx.fillText(statusText, statusX + statusWidth/2, statusY + 18);
                    
                    // Price vs projection - BIGGER
                    this.ctx.fillStyle = '#ffffff';
                    this.ctx.font = 'bold 11px Arial';
                    this.ctx.fillText(`Price: ${currentPrice.toFixed(2)}`, statusX + statusWidth/2, statusY + 33);
                    
                    // Draw projection status line on chart
                    const currentIdx = candles.length - 1;
                    if (currentIdx >= this.viewport.startIndex && currentIdx <= this.viewport.endIndex) {
                        const currentX = 60 + (currentIdx - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
                        const projectionY = chartHeight - ((projectionLine - this.viewport.priceRange.min) / priceRange) * chartHeight;
                        const actualY = chartHeight - ((currentPrice - this.viewport.priceRange.min) / priceRange) * chartHeight;
                        
                        // Draw deviation line - THICKER
                        this.ctx.strokeStyle = isOnTrack ? 'rgba(34, 197, 94, 0.8)' : isFollowing ? 'rgba(251, 191, 36, 0.8)' : 'rgba(239, 68, 68, 0.8)';
                        this.ctx.lineWidth = 3;
                        this.ctx.setLineDash([4, 4]);
                        this.ctx.beginPath();
                        this.ctx.moveTo(currentX, actualY);
                        this.ctx.lineTo(currentX, projectionY);
                        this.ctx.stroke();
                        this.ctx.setLineDash([]);
                        
                        // Draw deviation indicator - BIGGER
                        const deviation = ((currentPrice - projectionLine) / projectionLine * 100).toFixed(2);
                        this.ctx.fillStyle = isOnTrack ? '#22c55e' : isFollowing ? '#fbbf24' : '#ef4444';
                        this.ctx.font = 'bold 11px Arial';
                        this.ctx.textAlign = 'left';
                        this.ctx.fillText(`${deviation}%`, currentX + 10, actualY);
                    }
                }
            }
        }
        
        // Draw CHoCH sequence indicator at bottom
        const seqX = panelX;
        const seqY = panelY + panelHeight + 10;
        
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        this.ctx.fillRect(seqX, seqY, panelWidth, 35);
        
        this.ctx.fillStyle = '#fbbf24';
        this.ctx.font = 'bold 10px Arial';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('SEQUENCE:', seqX + 8, seqY + 15);
        
        // Draw sequence dots
        const dotStartX = seqX + 70;
        recentChoCH.slice(-4).forEach((choch, i) => {
            const dotX = dotStartX + i * 25;
            const isBull = choch.direction === 'bullish';
            
            // Dot
            this.ctx.fillStyle = isBull ? '#3b82f6' : '#a855f7';
            this.ctx.beginPath();
            this.ctx.arc(dotX, seqY + 22, 6, 0, Math.PI * 2);
            this.ctx.fill();
            
            // Arrow inside
            this.ctx.fillStyle = '#ffffff';
            this.ctx.font = 'bold 8px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.fillText(isBull ? '▲' : '▼', dotX, seqY + 25);
        });
        
        // Bull/Bear count
        this.ctx.fillStyle = '#3b82f6';
        this.ctx.font = 'bold 9px Arial';
        this.ctx.textAlign = 'left';
        this.ctx.fillText(`${bullishCount}B`, seqX + 8, seqY + 30);
        
        this.ctx.fillStyle = '#a855f7';
        this.ctx.fillText(`${bearishCount}S`, seqX + 35, seqY + 30);
    }
    
    drawCHoCHTrendLines(chochPoints, chartHeight, priceRange) {
        // Draw trend channel with enhanced shading between consecutive CHoCH points
        if (chochPoints.length < 2) return;
        
        // Sort by index
        const sorted = [...chochPoints].sort((a, b) => a.index - b.index);
        
        // Get canvas width for projections
        const rect = this.canvas.getBoundingClientRect();
        const canvasWidth = rect.width;
        
        // Build trend channels from consecutive CHoCH pairs
        for (let i = 1; i < sorted.length; i++) {
            const prev = sorted[i - 1];
            const curr = sorted[i];
            const next = sorted[i + 1]; // For channel width calculation
            
            // Only draw if both are visible
            if (prev.index < this.viewport.startIndex || curr.index > this.viewport.endIndex) continue;
            
            const x1 = 60 + (prev.index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y1 = chartHeight - ((prev.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const x2 = 60 + (curr.index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y2 = chartHeight - ((curr.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            // Determine trend direction
            const isUptrend = curr.price > prev.price;
            const priceDiff = Math.abs(curr.price - prev.price);
            const indexDiff = curr.index - prev.index;
            const slope = (y2 - y1) / (x2 - x1 || 1);
            
            // Calculate channel width based on volatility (use next point or average swing)
            let channelWidth = Math.abs(y2 - y1) * 0.3; // 30% of the move as default channel
            if (next) {
                const y3 = chartHeight - ((next.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
                const nextSlope = (y3 - y2) / (60 + (next.index - curr.index) * (this.viewport.candleWidth + this.viewport.candleSpacing) || 1);
                channelWidth = Math.abs(slope - nextSlope) * (x2 - x1) * 0.5;
            }
            channelWidth = Math.max(channelWidth, 20); // Minimum 20px channel
            
            // ENHANCED: Draw trend channel shading with gradient
            const gradient = this.ctx.createLinearGradient(0, Math.min(y1, y2) - channelWidth, 0, Math.max(y1, y2) + channelWidth);
            if (isUptrend) {
                gradient.addColorStop(0, 'rgba(59, 130, 246, 0.15)');   // Top - lighter blue
                gradient.addColorStop(0.5, 'rgba(59, 130, 246, 0.05)'); // Center - very light
                gradient.addColorStop(1, 'rgba(59, 130, 246, 0.15)');   // Bottom - lighter blue
            } else {
                gradient.addColorStop(0, 'rgba(168, 85, 247, 0.15)');  // Top - lighter purple
                gradient.addColorStop(0.5, 'rgba(168, 85, 247, 0.05)');  // Center - very light
                gradient.addColorStop(1, 'rgba(168, 85, 247, 0.15)');  // Bottom - lighter purple
            }
            
            // Draw channel fill
            this.ctx.fillStyle = gradient;
            this.ctx.beginPath();
            this.ctx.moveTo(x1, y1 - channelWidth/2);
            this.ctx.lineTo(x2, y2 - channelWidth/2);
            this.ctx.lineTo(x2, y2 + channelWidth/2);
            this.ctx.lineTo(x1, y1 + channelWidth/2);
            this.ctx.closePath();
            this.ctx.fill();
            
            // ENHANCED: Draw support/resistance band lines
            const bandColor = isUptrend ? 'rgba(59, 130, 246, 0.6)' : 'rgba(168, 85, 247, 0.6)';
            
            // Upper resistance band
            this.ctx.strokeStyle = bandColor;
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([8, 4]);
            this.ctx.beginPath();
            this.ctx.moveTo(x1, y1 - channelWidth/2);
            this.ctx.lineTo(x2, y2 - channelWidth/2);
            this.ctx.stroke();
            
            // Lower support band
            this.ctx.beginPath();
            this.ctx.moveTo(x1, y1 + channelWidth/2);
            this.ctx.lineTo(x2, y2 + channelWidth/2);
            this.ctx.stroke();
            
            // Reset dash
            this.ctx.setLineDash([]);
            
            // Main trend line (solid, thicker)
            this.ctx.strokeStyle = isUptrend 
                ? 'rgba(30, 64, 175, 0.8)'  // Deep Blue
                : 'rgba(124, 58, 237, 0.8)'; // Deep Purple
            this.ctx.lineWidth = 2.5;
            this.ctx.beginPath();
            this.ctx.moveTo(x1, y1);
            this.ctx.lineTo(x2, y2);
            this.ctx.stroke();
            
            // ENHANCED: Draw price projection line extending to right edge
            const projectionX = canvasWidth - 100;
            const projectionY = y2 + slope * (projectionX - x2);
            
            // Only draw if projection is within reasonable bounds
            if (projectionY > 0 && projectionY < chartHeight) {
                this.ctx.strokeStyle = isUptrend 
                    ? 'rgba(59, 130, 246, 0.4)' 
                    : 'rgba(168, 85, 247, 0.4)';
                this.ctx.lineWidth = 1.5;
                this.ctx.setLineDash([4, 6]);
                this.ctx.beginPath();
                this.ctx.moveTo(x2, y2);
                this.ctx.lineTo(projectionX, projectionY);
                this.ctx.stroke();
                this.ctx.setLineDash([]);
                
                // Draw projection label
                this.ctx.fillStyle = isUptrend ? '#3b82f6' : '#a855f7';
                this.ctx.font = 'bold 9px Arial';
                this.ctx.textAlign = 'left';
                this.ctx.fillText('PROJ', projectionX + 5, projectionY);
            }
            
            // Draw pips move label at midpoint
            const midX = (x1 + x2) / 2;
            const midY = (y1 + y2) / 2;
            const pips = (priceDiff * 100).toFixed(1);
            
            // Label background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            const labelWidth = this.ctx.measureText(`${pips}p`).width;
            this.ctx.fillRect(midX - labelWidth/2 - 4, midY - 12, labelWidth + 8, 14);
            
            // Label text
            this.ctx.fillStyle = isUptrend ? '#60a5fa' : '#c084fc';
            this.ctx.font = 'bold 10px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.fillText(`${pips}p`, midX, midY - 2);
            
            // Draw channel width label
            const channelPips = (Math.abs(channelWidth / chartHeight * priceRange) * 100).toFixed(1);
            this.ctx.font = '9px Arial';
            this.ctx.fillStyle = isUptrend ? 'rgba(59, 130, 246, 0.7)' : 'rgba(168, 85, 247, 0.7)';
            this.ctx.fillText(`±${channelPips}p`, x2 + 10, y2);
        }
        
        // ENHANCED: Draw overall trend structure zone
        if (sorted.length >= 3) {
            this.drawTrendStructureZone(sorted, chartHeight, priceRange);
        }
    }
    
    drawTrendStructureZone(chochPoints, chartHeight, priceRange) {
        // Draw a comprehensive trend zone showing the overall structure
        const visiblePoints = chochPoints.filter(p => 
            p.index >= this.viewport.startIndex && p.index <= this.viewport.endIndex
        );
        
        if (visiblePoints.length < 3) return;
        
        // Find highest and lowest CHoCH in visible range
        const prices = visiblePoints.map(p => p.price);
        const maxPrice = Math.max(...prices);
        const minPrice = Math.min(...prices);
        const minIndex = Math.min(...visiblePoints.map(p => p.index));
        const maxIndex = Math.max(...visiblePoints.map(p => p.index));
        
        // Convert to canvas coordinates
        const yTop = chartHeight - ((maxPrice - this.viewport.priceRange.min) / priceRange) * chartHeight;
        const yBottom = chartHeight - ((minPrice - this.viewport.priceRange.min) / priceRange) * chartHeight;
        const xLeft = 60 + (minIndex - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
        const xRight = 60 + (maxIndex - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
        
        // Determine overall trend
        const firstPrice = visiblePoints[0].price;
        const lastPrice = visiblePoints[visiblePoints.length - 1].price;
        const isUptrend = lastPrice > firstPrice;
        
        // Draw structure zone with gradient
        const zoneGradient = this.ctx.createLinearGradient(xLeft, yTop, xLeft, yBottom);
        if (isUptrend) {
            zoneGradient.addColorStop(0, 'rgba(59, 130, 246, 0.08)');
            zoneGradient.addColorStop(0.5, 'rgba(59, 130, 246, 0.02)');
            zoneGradient.addColorStop(1, 'rgba(59, 130, 246, 0.08)');
        } else {
            zoneGradient.addColorStop(0, 'rgba(168, 85, 247, 0.08)');
            zoneGradient.addColorStop(0.5, 'rgba(168, 85, 247, 0.02)');
            zoneGradient.addColorStop(1, 'rgba(168, 85, 247, 0.08)');
        }
        
        this.ctx.fillStyle = zoneGradient;
        this.ctx.fillRect(xLeft, yTop, xRight - xLeft, yBottom - yTop);
        
        // Draw structure boundary lines
        this.ctx.strokeStyle = isUptrend ? 'rgba(59, 130, 246, 0.3)' : 'rgba(168, 85, 247, 0.3)';
        this.ctx.lineWidth = 1;
        this.ctx.setLineDash([12, 6]);
        
        // Top boundary
        this.ctx.beginPath();
        this.ctx.moveTo(xLeft, yTop);
        this.ctx.lineTo(xRight, yTop);
        this.ctx.stroke();
        
        // Bottom boundary
        this.ctx.beginPath();
        this.ctx.moveTo(xLeft, yBottom);
        this.ctx.lineTo(xRight, yBottom);
        this.ctx.stroke();
        
        this.ctx.setLineDash([]);
        
        // Draw structure label
        const rangePips = ((maxPrice - minPrice) * 100).toFixed(1);
        const centerX = (xLeft + xRight) / 2;
        
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
        const labelText = `STRUCTURE ${rangePips}p`;
        const labelWidth = this.ctx.measureText(labelText).width;
        this.ctx.fillRect(centerX - labelWidth/2 - 6, yTop - 20, labelWidth + 12, 16);
        
        this.ctx.fillStyle = isUptrend ? '#60a5fa' : '#c084fc';
        this.ctx.font = 'bold 10px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.fillText(labelText, centerX, yTop - 8);
    }
    
    drawOrderBlocks() {
        // Draw Order Blocks - institutional order zones
        const orderBlocks = this.data.priceAction?.orderBlocks || [];
        if (orderBlocks.length === 0) return;
        
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        
        orderBlocks.forEach(ob => {
            // Check if visible
            if (ob.index < this.viewport.startIndex || ob.index > this.viewport.endIndex) return;
            
            const x = 60 + (ob.index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const yHigh = chartHeight - ((ob.high - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yLow = chartHeight - ((ob.low - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yOpen = chartHeight - ((ob.open - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yClose = chartHeight - ((ob.close - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            const isBullish = ob.type === 'bullish';
            const strength = ob.strength || 50;
            
            // Calculate opacity based on strength
            const opacity = 0.3 + (strength / 200); // 0.3 to 0.8
            
            // Distinct colors for order blocks: Teal for bullish, Magenta for bearish
            const obColor = isBullish ? '#0d9488' : '#db2777'; // Teal / Magenta
            const obColorRGBA = isBullish ? `rgba(13, 148, 136, ${opacity})` : `rgba(219, 39, 119, ${opacity})`;
            const obColorSolid = isBullish ? `rgba(13, 148, 136, 1)` : `rgba(219, 39, 119, 1)`;
            
            // Draw order block rectangle covering the candle range
            this.ctx.fillStyle = obColorRGBA;
            this.ctx.fillRect(x - 4, yHigh, 8, yLow - yHigh);
            
            // Draw order block border (thicker for high strength)
            this.ctx.strokeStyle = obColorSolid;
            this.ctx.lineWidth = strength > 70 ? 3 : 2;
            this.ctx.strokeRect(x - 4, yHigh, 8, yLow - yHigh);
            
            // Draw the body of the candle (where orders sit)
            const bodyTop = Math.min(yOpen, yClose);
            const bodyBottom = Math.max(yOpen, yClose);
            this.ctx.fillStyle = isBullish ? 'rgba(13, 148, 136, 0.6)' : 'rgba(219, 39, 119, 0.6)';
            this.ctx.fillRect(x - 2, bodyTop, 4, bodyBottom - bodyTop);
            
            // Draw "OB" label
            this.ctx.fillStyle = obColor;
            this.ctx.font = 'bold 9px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.fillText('OB', x, yHigh - 5);
            
            // Draw strength for high-quality order blocks
            if (strength > 70) {
                this.ctx.font = 'bold 8px Arial';
                this.ctx.fillStyle = '#f59e0b'; // Amber
                this.ctx.fillText(`${Math.round(strength)}%`, x, yLow + 12);
            }
        });
    }
    
    drawLiquiditySweeps() {
        // Draw Liquidity Sweeps (Stop Hunts) - wicks that swept liquidity before reversal
        const sweeps = this.data.priceAction?.liquiditySweeps || [];
        if (sweeps.length === 0) return;
        
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        
        sweeps.forEach(sweep => {
            // Check if visible
            if (sweep.index < this.viewport.startIndex || sweep.index > this.viewport.endIndex) return;
            
            const x = 60 + (sweep.index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const ySweep = chartHeight - ((sweep.sweep_price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const ySwing = chartHeight - ((sweep.swing_price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            const isHighSweep = sweep.type === 'high';
            const strength = sweep.strength || 60;
            
            // Use distinct colors: Orange for high sweep, Cyan for low sweep
            const sweepColor = isHighSweep ? '#ea580c' : '#0891b2'; // Orange / Cyan
            const sweepColorRGBA = isHighSweep ? 'rgba(234, 88, 12, 0.7)' : 'rgba(8, 145, 178, 0.7)';
            
            // Draw wick extension line (dashed) showing the sweep
            this.ctx.strokeStyle = sweepColorRGBA;
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([3, 2]);
            this.ctx.beginPath();
            this.ctx.moveTo(x, ySweep);
            this.ctx.lineTo(x, ySwing);
            this.ctx.stroke();
            this.ctx.setLineDash([]);
            
            // Draw sweep point marker (small circle)
            this.ctx.fillStyle = sweepColor;
            this.ctx.beginPath();
            this.ctx.arc(x, ySweep, 4, 0, Math.PI * 2);
            this.ctx.fill();
            
            // Draw label "LS" (Liquidity Sweep)
            this.ctx.fillStyle = sweepColor;
            this.ctx.font = 'bold 9px Arial';
            this.ctx.textAlign = 'center';
            const labelY = isHighSweep ? ySweep - 8 : ySweep + 12;
            this.ctx.fillText('LS', x, labelY);
            
            // Draw strength indicator for high-quality sweeps
            if (strength > 75) {
                this.ctx.font = 'bold 8px Arial';
                this.ctx.fillStyle = '#f59e0b'; // Amber
                const strengthY = isHighSweep ? ySweep - 18 : ySweep + 22;
                this.ctx.fillText(`${Math.round(strength)}%`, x, strengthY);
            }
            
            // Draw arrow pointing from sweep to CHoCH direction
            const chochX = 60 + (sweep.choch_index - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const arrowY = isHighSweep ? ySweep - 25 : ySweep + 25;
            
            this.ctx.strokeStyle = 'rgba(245, 158, 11, 0.6)'; // Amber arrow
            this.ctx.lineWidth = 1.5;
            this.ctx.setLineDash([2, 3]);
            this.ctx.beginPath();
            this.ctx.moveTo(x, arrowY);
            this.ctx.lineTo(chochX, arrowY);
            this.ctx.stroke();
            this.ctx.setLineDash([]);
            
            // Draw arrowhead
            const direction = chochX > x ? 1 : -1;
            this.ctx.fillStyle = '#fbbf24';
            this.ctx.beginPath();
            this.ctx.moveTo(chochX, arrowY);
            this.ctx.lineTo(chochX - 5 * direction, arrowY - 3);
            this.ctx.lineTo(chochX - 5 * direction, arrowY + 3);
            this.ctx.fill();
        });
    }
    
    drawCrosshair() {
        const { width, height } = this.canvas;
        
        // Enhanced crosshair visibility
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)'; // Increased opacity
        this.ctx.lineWidth = 1.5; // Thicker lines
        this.ctx.setLineDash([5, 3]); // Dashed lines for better visibility
        
        // Vertical line
        this.ctx.beginPath();
        this.ctx.moveTo(this.crosshair.x, 0);
        this.ctx.lineTo(this.crosshair.x, height);
        this.ctx.stroke();
        
        // Horizontal line
        this.ctx.beginPath();
        this.ctx.moveTo(0, this.crosshair.y);
        this.ctx.lineTo(width, this.crosshair.y);
        this.ctx.stroke();
        
        this.ctx.setLineDash([]); // Reset dash pattern
        
        // Draw price label with enhanced visibility
        const chartHeight = height * 0.7;
        const price = this.viewport.priceRange.max - 
            (this.crosshair.y / chartHeight) * 
            (this.viewport.priceRange.max - this.viewport.priceRange.min);
        
        // Enhanced price label background
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.9)'; // Darker background
        this.ctx.fillRect(this.crosshair.x + 10, this.crosshair.y - 15, 90, 25); // Larger box
        
        // Enhanced price label text
        this.ctx.fillStyle = '#ffffff'; // Pure white text
        this.ctx.font = 'bold 12px Arial'; // Bold and larger
        this.ctx.textAlign = 'left';
        this.ctx.fillText(price.toFixed(2), this.crosshair.x + 15, this.crosshair.y + 2);
    }
    
    updatePriceAction(priceActionData) {
        // Update price action patterns from API
        if (!priceActionData) return;
        
        this.data.priceAction = {
            fvgs: priceActionData.fvgs || [],
            zones: priceActionData.zones || [],
            bos: priceActionData.bos || [],
            summary: priceActionData.summary || {}
        };
        
        // Redraw chart
        this.draw();
    }
    
    drawLabels() {
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        
        this.ctx.fillStyle = this.options.textColor;
        this.ctx.font = '10px Arial';
        this.ctx.textAlign = 'right';
        
        // Price labels on the right
        const priceLevels = 8;
        for (let i = 0; i <= priceLevels; i++) {
            const price = this.viewport.priceRange.min + 
                (i / priceLevels) * (this.viewport.priceRange.max - this.viewport.priceRange.min);
            const y = chartHeight - (i / priceLevels) * chartHeight;
            
            this.ctx.fillText(price.toFixed(2), width - 5, y + 3);
        }
        
        // Time labels at the bottom
        this.ctx.textAlign = 'center';
        const timeLevels = 8;
        for (let i = 0; i <= timeLevels; i++) {
            const x = 60 + (i / timeLevels) * (width - 60);
            this.ctx.fillText(`${i}:00`, x, height - 5);
        }
    }
    
    drawNoDataMessage() {
        const { width, height } = this.canvas;
        
        this.ctx.fillStyle = this.options.textColor;
        this.ctx.font = '16px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.fillText('No data available', width / 2, height / 2);
    }
    
    setTimeframe(timeframe) {
        this.selectedTimeframe = timeframe;
        // Trigger data reload for new timeframe
        this.onTimeframeChange(timeframe);
    }
    
    toggleIndicator(indicator) {
        this.indicators[indicator] = !this.indicators[indicator];
        this.draw();
    }
    
    onTimeframeChange(timeframe) {
        // Override this method to handle timeframe changes
        console.log('Timeframe changed to:', timeframe);
    }
    
    calculateProjectionLine(chochPoint, targetPrice, currentIndex, chochIndex) {
        // Calculate the expected price on the projection line at a given index
        const priceDiff = targetPrice - chochPoint.price;
        const indexDiff = currentIndex - chochIndex;
        const slope = priceDiff / 10; // Spread projection over 10 candles
        return chochPoint.price + (slope * indexDiff);
    }
    
    trackNewPrediction(chochPoint, targetDirection, predictionText) {
        // Track a new CHoCH prediction for outcome evaluation
        if (!this.predictionTracker.activePredictions) {
            this.predictionTracker.activePredictions = [];
        }
        
        // Check if this CHoCH is already being tracked
        const existingIndex = this.predictionTracker.activePredictions.findIndex(
            p => p.chochIndex === chochPoint.index
        );
        
        if (existingIndex === -1) {
            // New prediction - add to tracking
            const candles = this.data.candles || [];
            const currentIdx = candles.length - 1;
            
            this.predictionTracker.activePredictions.push({
                chochIndex: chochPoint.index,
                chochPrice: chochPoint.price,
                direction: targetDirection,
                predictionText: predictionText,
                startIndex: currentIdx,
                startPrice: candles.length > 0 ? candles[currentIdx].close : chochPoint.price,
                targetPrice: chochPoint.price + (targetDirection === 'bullish' ? Math.abs(chochPoint.price - chochPoint.previous_swing) : -Math.abs(chochPoint.price - chochPoint.previous_swing)),
                status: 'active', // active, win, loss
                candlesTracked: 0,
                maxCandlesToTrack: 20 // Evaluate within 20 candles
            });
        }
    }
    
    evaluateActivePredictions() {
        // Evaluate all active predictions against current price
        if (!this.predictionTracker.activePredictions || this.predictionTracker.activePredictions.length === 0) {
            return;
        }
        
        const candles = this.data.candles || [];
        if (candles.length === 0) return;
        
        const currentCandle = candles[candles.length - 1];
        const currentPrice = currentCandle.close;
        const currentIndex = candles.length - 1;
        
        this.predictionTracker.activePredictions.forEach(pred => {
            if (pred.status !== 'active') return;
            
            pred.candlesTracked++;
            
            // Check if prediction reached target (win)
            const reachedTarget = pred.direction === 'bullish' 
                ? currentPrice >= pred.targetPrice 
                : currentPrice <= pred.targetPrice;
            
            // Check if prediction was invalidated (loss) - price moved opposite direction significantly
            const invalidationThreshold = Math.abs(pred.chochPrice - pred.startPrice) * 1.5;
            const isInvalidated = pred.direction === 'bullish'
                ? currentPrice < (pred.chochPrice - invalidationThreshold)
                : currentPrice > (pred.chochPrice + invalidationThreshold);
            
            // Check if max tracking candles reached
            const maxCandlesReached = pred.candlesTracked >= pred.maxCandlesToTrack;
            
            // Price moved favorably but didn't reach target
            const movedFavorably = pred.direction === 'bullish'
                ? currentPrice > pred.chochPrice
                : currentPrice < pred.chochPrice;
            
            if (reachedTarget) {
                // WIN: Price reached the predicted target
                pred.status = 'win';
                pred.resolvedAt = currentIndex;
                pred.finalPrice = currentPrice;
                this.recordPredictionOutcome(true);
            } else if (isInvalidated) {
                // LOSS: Price moved significantly against prediction
                pred.status = 'loss';
                pred.resolvedAt = currentIndex;
                pred.finalPrice = currentPrice;
                this.recordPredictionOutcome(false);
            } else if (maxCandlesReached && !movedFavorably) {
                // LOSS: Max time reached and price didn't move in predicted direction
                pred.status = 'loss';
                pred.resolvedAt = currentIndex;
                pred.finalPrice = currentPrice;
                this.recordPredictionOutcome(false);
            } else if (maxCandlesReached && movedFavorably) {
                // WIN: Price moved in predicted direction (partial success)
                pred.status = 'win';
                pred.resolvedAt = currentIndex;
                pred.finalPrice = currentPrice;
                this.recordPredictionOutcome(true);
            }
        });
        
        // Clean up old resolved predictions (keep last 20 in history)
        this.predictionTracker.activePredictions = this.predictionTracker.activePredictions.filter(
            p => p.status === 'active' || (p.resolvedAt && p.resolvedAt > currentIndex - 50)
        );
    }
    
    recordPredictionOutcome(isWin) {
        // Record a win or loss in the tracker
        if (isWin) {
            this.predictionTracker.wins++;
        } else {
            this.predictionTracker.losses++;
        }
        this.predictionTracker.total++;
        
        // Add to history
        this.predictionTracker.history.push({
            outcome: isWin ? 'win' : 'loss',
            timestamp: Date.now()
        });
        
        // Keep only last 100 history entries
        if (this.predictionTracker.history.length > 100) {
            this.predictionTracker.history.shift();
        }
    }
    
    drawPredictionOutcomeMarkers() {
        // Draw visual markers for completed predictions (wins/losses) on the chart
        if (!this.predictionTracker.activePredictions || this.predictionTracker.activePredictions.length === 0) {
            return;
        }
        
        const chartHeight = this.canvas.height / (window.devicePixelRatio || 1);
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        if (priceRange === 0) return;
        
        this.predictionTracker.activePredictions.forEach(pred => {
            if (pred.status === 'active' || !pred.resolvedAt) return;
            
            // Check if resolved point is in viewport
            if (pred.resolvedAt < this.viewport.startIndex || pred.resolvedAt > this.viewport.endIndex) {
                return;
            }
            
            const x = 60 + (pred.resolvedAt - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((pred.finalPrice - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            // Draw marker based on outcome
            const isWin = pred.status === 'win';
            const color = isWin ? '#22c55e' : '#ef4444';
            const emoji = isWin ? '✓' : '✗';
            
            // Draw circle background
            this.ctx.beginPath();
            this.ctx.arc(x, y, 12, 0, Math.PI * 2);
            this.ctx.fillStyle = color;
            this.ctx.fill();
            
            // Draw border
            this.ctx.strokeStyle = '#ffffff';
            this.ctx.lineWidth = 2;
            this.ctx.stroke();
            
            // Draw emoji
            this.ctx.fillStyle = '#ffffff';
            this.ctx.font = 'bold 12px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText(emoji, x, y);
            
            // Draw connecting line from CHoCH to outcome
            if (pred.chochIndex >= this.viewport.startIndex && pred.chochIndex <= this.viewport.endIndex) {
                const chochX = 60 + (pred.chochIndex - this.viewport.startIndex) * (this.viewport.candleWidth + this.viewport.candleSpacing);
                const chochY = chartHeight - ((pred.chochPrice - this.viewport.priceRange.min) / priceRange) * chartHeight;
                
                this.ctx.beginPath();
                this.ctx.moveTo(chochX, chochY);
                this.ctx.lineTo(x, y);
                this.ctx.strokeStyle = isWin ? 'rgba(34, 197, 94, 0.4)' : 'rgba(239, 68, 68, 0.4)';
                this.ctx.lineWidth = 2;
                this.ctx.setLineDash([3, 3]);
                this.ctx.stroke();
                this.ctx.setLineDash([]);
            }
        });
    }
    
    drawPredictionTracker(x, y, width) {
        // Draw prediction accuracy tracker showing win/loss stats
        const trackerHeight = 35;
        
        // Get real stats from prediction tracker
        const tracker = this.predictionTracker || { wins: 0, losses: 0, total: 0, history: [], activePredictions: [] };
        const accuracy = tracker.total > 0 ? Math.round((tracker.wins / tracker.total) * 100) : 0;
        
        // Tracker background
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.9)';
        this.ctx.fillRect(x, y, width, trackerHeight);
        
        // Border
        this.ctx.strokeStyle = accuracy >= 70 ? 'rgba(34, 197, 94, 0.8)' : 
                              accuracy >= 50 ? 'rgba(251, 191, 36, 0.8)' : 'rgba(239, 68, 68, 0.8)';
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(x, y, width, trackerHeight);
        
        // Title
        this.ctx.fillStyle = '#94a3b8';
        this.ctx.font = 'bold 10px Arial';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('📈 TRACKER', x + 8, y + 14);
        
        // Win/Loss counts - LARGER
        this.ctx.fillStyle = '#22c55e';
        this.ctx.font = 'bold 13px Arial';
        this.ctx.fillText(`${tracker.wins}W`, x + 80, y + 14);
        
        this.ctx.fillStyle = '#ef4444';
        this.ctx.fillText(`${tracker.losses}L`, x + 120, y + 14);
        
        // Accuracy percentage - BIGGER, BOLDER
        this.ctx.fillStyle = accuracy >= 70 ? '#22c55e' : 
                            accuracy >= 50 ? '#fbbf24' : '#ef4444';
        this.ctx.font = 'bold 16px Arial';
        this.ctx.textAlign = 'right';
        this.ctx.fillText(`${accuracy}%`, x + width - 8, y + 16);
        
        // Progress bar
        const barY = y + 24;
        const barWidth = width - 16;
        const barHeight = 6;
        
        // Bar background
        this.ctx.fillStyle = 'rgba(255, 255, 255, 0.1)';
        this.ctx.fillRect(x + 8, barY, barWidth, barHeight);
        
        // Win portion (green)
        const winWidth = tracker.total > 0 ? (tracker.wins / tracker.total) * barWidth : 0;
        this.ctx.fillStyle = '#22c55e';
        this.ctx.fillRect(x + 8, barY, winWidth, barHeight);
        
        // Loss portion (red)
        if (tracker.losses > 0) {
            this.ctx.fillStyle = '#ef4444';
            this.ctx.fillRect(x + 8 + winWidth, barY, barWidth - winWidth, barHeight);
        }
        
        // Bar border
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(x + 8, barY, barWidth, barHeight);
    }
    
    getAccountBalance() {
        // Get real account balance from dashboard, fallback to default if not available
        const balanceEl = document.getElementById('balance');
        if (balanceEl) {
            const balanceText = balanceEl.textContent || balanceEl.innerText || '';
            // Remove $ and commas, parse as float
            const balance = parseFloat(balanceText.replace(/[$,]/g, ''));
            if (!isNaN(balance) && balance > 0) {
                return balance;
            }
        }
        // Fallback to checking window.accountData if available
        if (window.accountData && window.accountData.balance) {
            return window.accountData.balance;
        }
        // Default fallback
        return 10000;
    }
    
    updateCHoCHAnalysisPanel() {
        // Update the HTML panel below the chart with CHoCH analysis data
        const panel = document.getElementById('chochAnalysisPanel');
        if (!panel) return;
        
        // Show/hide panel based on CHoCH toggle
        panel.style.display = this.indicators.choch ? 'block' : 'none';
        
        if (!this.indicators.choch || !this.data.priceAction || !this.data.priceAction.bos) {
            return;
        }
        
        // Get CHoCH points
        const bos = this.data.priceAction.bos || [];
        const chochPoints = bos.filter(p => p.type === 'CHoCH');
        
        if (chochPoints.length === 0) return;
        
        // Sort by index
        const sorted = [...chochPoints].sort((a, b) => a.index - b.index);
        const recentChoCH = sorted.slice(-5);
        const mostRecent = sorted[sorted.length - 1];
        
        // Analyze pattern
        const bullishCount = recentChoCH.filter(c => c.direction === 'bullish').length;
        const bearishCount = recentChoCH.filter(c => c.direction === 'bearish').length;
        
        let phase = 'NEUTRAL';
        let prediction = '';
        let targetDirection = '';
        let confidence = 50;
        
        if (recentChoCH.length >= 2) {
            const last = recentChoCH[recentChoCH.length - 1];
            const prev = recentChoCH[recentChoCH.length - 2];
            
            if (last.direction === prev.direction) {
                phase = last.direction === 'bullish' ? 'BULLISH TREND' : 'BEARISH TREND';
                prediction = last.direction === 'bullish' ? 'EXPECT HIGHER HIGH' : 'EXPECT LOWER LOW';
                targetDirection = last.direction;
                confidence = 70 + Math.max(bullishCount, bearishCount) * 5;
            } else {
                phase = 'TRANSITION';
                prediction = last.price > prev.price ? 'BULLISH REVERSAL' : 'BEARISH REVERSAL';
                targetDirection = last.price > prev.price ? 'bullish' : 'bearish';
                confidence = 60;
            }
        }
        
        // Update panel elements
        const phaseEl = document.getElementById('chochPhase');
        const predEl = document.getElementById('chochPrediction');
        const confBar = document.getElementById('chochConfidenceBar');
        const confEl = document.getElementById('chochConfidence');
        
        if (phaseEl) {
            phaseEl.textContent = phase;
            phaseEl.style.color = targetDirection === 'bullish' ? '#3b82f6' : 
                                 targetDirection === 'bearish' ? '#a855f7' : '#94a3b8';
        }
        if (predEl) predEl.textContent = prediction;
        if (confBar) {
            confBar.style.width = `${Math.min(confidence, 100)}%`;
            confBar.style.background = targetDirection === 'bullish' ? 
                'linear-gradient(90deg, #1e40af, #3b82f6)' : 
                targetDirection === 'bearish' ? 
                'linear-gradient(90deg, #7c3aed, #a855f7)' : 
                'linear-gradient(90deg, #475569, #94a3b8)';
        }
        if (confEl) confEl.textContent = `${confidence}%`;
        
        // Calculate position size
        const prevSwing = mostRecent.previous_swing;
        if (prevSwing) {
            const stopDistance = Math.abs(mostRecent.price - prevSwing);
            const accountBalance = this.getAccountBalance(); // Get real balance from dashboard
            const riskPercent = 2;
            const riskAmount = accountBalance * (riskPercent / 100);
            const stopPips = stopDistance * 100;
            const positionSize = (riskAmount / (stopPips * 10)).toFixed(2);
            const microLots = Math.max(0.01, Math.min(2.0, positionSize));
            
            const lotsEl = document.getElementById('positionLots');
            const slEl = document.getElementById('positionSL');
            const riskEl = document.getElementById('positionRisk');
            
            if (lotsEl) lotsEl.textContent = microLots;
            if (slEl) slEl.textContent = `SL: ${stopPips.toFixed(1)}p`;
            if (riskEl) riskEl.textContent = `Risk: $${riskAmount.toFixed(0)}`;
        }
        
        // Update tracker with real data
        const tracker = this.predictionTracker || { wins: 0, losses: 0, total: 0 };
        const accuracy = tracker.total > 0 ? Math.round((tracker.wins / tracker.total) * 100) : 0;
        
        const winsEl = document.getElementById('trackerWins');
        const lossesEl = document.getElementById('trackerLosses');
        const accEl = document.getElementById('trackerAccuracy');
        const barEl = document.getElementById('trackerBar');
        
        if (winsEl) winsEl.textContent = `${tracker.wins}W`;
        if (lossesEl) lossesEl.textContent = `${tracker.losses}L`;
        if (accEl) {
            accEl.textContent = `${accuracy}%`;
            accEl.style.color = accuracy >= 70 ? '#22c55e' : accuracy >= 50 ? '#fbbf24' : '#ef4444';
        }
        if (barEl) {
            const winPercent = (tracker.wins / tracker.total) * 100;
            barEl.style.width = '100%';
            barEl.style.background = `linear-gradient(90deg, #22c55e ${winPercent}%, #ef4444 ${winPercent}%)`;
        }
        
        // Update recent predictions list
        const recentPredEl = document.getElementById('recentPredictions');
        if (recentPredEl && tracker.activePredictions) {
            const resolved = tracker.activePredictions
                .filter(p => p.status === 'win' || p.status === 'loss')
                .slice(-10) // Last 10
                .reverse();
            
            if (resolved.length > 0) {
                recentPredEl.innerHTML = '<span style="color: #64748b;">Recent: </span>' +
                    resolved.map(p => {
                        const color = p.status === 'win' ? '#22c55e' : '#ef4444';
                        const emoji = p.status === 'win' ? '✓' : '✗';
                        const dir = p.direction === 'bullish' ? '▲' : '▼';
                        return `<span style="color: ${color}; font-weight: bold;">${emoji}${dir}</span>`;
                    }).join(' ');
            }
        }
        
        // Update status
        const candles = this.data.candles || [];
        if (candles.length > 0) {
            const currentCandle = candles[candles.length - 1];
            const currentPrice = currentCandle.close;
            const prevSwing = mostRecent.previous_swing;
            const swingSize = Math.abs(mostRecent.price - prevSwing);
            const isBullish = mostRecent.direction === 'bullish';
            const isFollowing = isBullish ? currentPrice >= mostRecent.price : currentPrice <= mostRecent.price;
            const priceDiff = Math.abs(currentPrice - mostRecent.price);
            const isOnTrack = priceDiff < (swingSize * 0.3);
            
            const statusEl = document.getElementById('projectionStatus');
            const priceEl = document.getElementById('currentPriceDisplay');
            
            if (statusEl) {
                statusEl.style.background = isOnTrack ? 'rgba(34, 197, 94, 0.2)' : 
                                              isFollowing ? 'rgba(251, 191, 36, 0.2)' : 'rgba(239, 68, 68, 0.2)';
                statusEl.style.borderColor = isOnTrack ? '#22c55e' : 
                                             isFollowing ? '#fbbf24' : '#ef4444';
                statusEl.innerHTML = `
                    <div style="font-weight: bold; font-size: 18px; color: ${isOnTrack ? '#22c55e' : isFollowing ? '#fbbf24' : '#ef4444'}; margin-bottom: 4px;">
                        ${isOnTrack ? '✓ ON TRACK' : isFollowing ? '⚠ FOLLOWING' : '✗ REJECTING'}
                    </div>
                    <div id="currentPriceDisplay" style="font-size: 14px; color: #ffffff;">Price: ${currentPrice.toFixed(2)}</div>
                `;
            }
        }
    }
    
    // Real-time data methods
    setData(chartData) {
        // Set initial chart data from WebSocket
        if (!chartData || !chartData.candles) {
            console.warn('Invalid chart data received');
            return;
        }
        
        this.data.candles = chartData.candles;
        this.data.volume = chartData.volume || [];
        this.data.indicators = chartData.indicators || {};
        this.data.trades = chartData.trades || [];
        this.data.levels = chartData.levels || [];
        
        // Reset viewport to show all data
        this.resetViewport();
        
        // Redraw chart
        this.draw();
        
        console.log(`✅ Chart loaded with ${this.data.candles.length} candles`);
    }
    
    addRealtimeCandle(candle) {
        // Add new candle from real-time stream
        if (!candle) return;
        
        // Check if this is an update to the last candle or a new candle
        const lastCandle = this.data.candles[this.data.candles.length - 1];
        
        if (lastCandle && lastCandle.time === candle.time) {
            // Update existing candle (current period)
            Object.assign(lastCandle, candle);
        } else {
            // Add new candle
            this.data.candles.push(candle);
            
            // Keep only last 500 candles for performance
            if (this.data.candles.length > 500) {
                this.data.candles.shift();
                this.data.volume.shift();
            }
            
            // Add volume data if provided
            if (candle.volume !== undefined) {
                this.data.volume.push(candle.volume);
            }
        }
        
        // Auto-scroll to latest candle if at the end
        if (this.viewport.endIndex >= this.data.candles.length - 2) {
            this.viewport.endIndex = this.data.candles.length;
            this.viewport.startIndex = Math.max(0, this.viewport.endIndex - this.visibleCandles);
        }
        
        // Update price range
        this.updatePriceRange();
        
        // Redraw chart
        this.draw();
    }
    
    updateIndicators(indicators) {
        // Update technical indicators from real-time stream
        if (!indicators) return;
        
        // Update each indicator type
        Object.keys(indicators).forEach(indicatorType => {
            if (Array.isArray(indicators[indicatorType])) {
                this.data.indicators[indicatorType] = indicators[indicatorType];
            }
        });
        
        // Redraw chart
        this.draw();
    }
    
    addTrade(trade) {
        // Add trade marker from real-time stream
        if (!trade || trade.candleIndex === undefined) return;
        
        // Remove existing trade for same candle if any
        this.data.trades = this.data.trades.filter(t => t.candleIndex !== trade.candleIndex);
        
        // Add new trade
        this.data.trades.push(trade);
        
        // Redraw chart
        this.draw();
    }
    
    addPriceLevel(level) {
        // Add price level from real-time stream
        if (!level || !level.price) return;
        
        // Remove existing level for same price if any
        this.data.levels = this.data.levels.filter(l => 
            Math.abs(l.price - level.price) > 0.1
        );
        
        // Add new level
        this.data.levels.push(level);
        
        // Keep only last 10 levels
        if (this.data.levels.length > 10) {
            this.data.levels.shift();
        }
        
        // Redraw chart
        this.draw();
    }
    
    resetViewport() {
        // Reset viewport to show all data
        this.viewport = {
            startIndex: 0,
            endIndex: Math.min(this.visibleCandles, this.data.candles.length),
            candleWidth: this.calculateCandleWidth(),
            candleSpacing: 2,
            priceRange: this.calculatePriceRange(),
            volumeRange: this.calculateVolumeRange()
        };
    }
    
    calculateCandleWidth() {
        // Calculate optimal candle width based on data size
        if (this.data.candles.length === 0) return 8;
        return Math.max(4, Math.min(12, (this.canvas.width - 60) / Math.min(this.data.candles.length, this.visibleCandles) - 2));
    }
    
    calculatePriceRange() {
        // Calculate price range with some padding
        if (this.data.candles.length === 0) {
            return { min: 0, max: 100 };
        }
        
        const visibleCandles = this.data.candles.slice(
            this.viewport.startIndex,
            this.viewport.endIndex
        );
        
        let min = Infinity, max = -Infinity;
        
        visibleCandles.forEach(candle => {
            min = Math.min(min, candle.low);
            max = Math.max(max, candle.high);
        });
        
        // Add 5% padding
        const padding = (max - min) * 0.05;
        return { min: min - padding, max: max + padding };
    }
    
    calculateVolumeRange() {
        // Calculate volume range
        if (this.data.volume.length === 0) {
            return { min: 0, max: 100 };
        }
        
        const visibleVolume = this.data.volume.slice(
            this.viewport.startIndex,
            this.viewport.endIndex
        );
        
        const max = Math.max(...visibleVolume.filter(v => v !== null && v !== undefined));
        return { min: 0, max: max || 100 };
    }
    
    updatePriceRange() {
        // Update viewport price range
        this.viewport.priceRange = this.calculatePriceRange();
    }
    
    // Performance optimization methods
    optimizeForRealtime() {
        // Optimize chart for real-time updates
        // Reduce visible candles for better performance
        this.visibleCandles = 50;
        
        // Increase frame rate for smoother updates
        this.lastDrawTime = 0;
        this.targetFPS = 30;
        this.frameInterval = 1000 / this.targetFPS;
    }
    
    shouldDraw() {
        // Check if chart should be redrawn based on FPS limit
        const now = performance.now();
        if (now - this.lastDrawTime < this.frameInterval) {
            return false;
        }
        this.lastDrawTime = now;
        return true;
    }
    
    drawOptimized() {
        // Optimized draw method for real-time updates
        if (!this.shouldDraw()) return;
        
        this.draw();
    }
    
    checkTradeAlerts() {
        // Check for high-urgency trade suggestions and trigger alerts
        const suggestions = this.data.priceAction?.tradeSuggestions || [];
        
        suggestions.forEach(suggestion => {
            // Only alert for immediate urgency or high confluence
            if (suggestion.urgency === 'immediate' && !suggestion.alerted) {
                suggestion.alerted = true; // Mark as alerted
                this.showTradeAlert(suggestion);
            }
        });
    }
    
    showTradeAlert(suggestion) {
        // Dispatch custom event for dashboard to show toast/alert
        const event = new CustomEvent('tradeAlert', {
            detail: {
                type: suggestion.type,
                entry: suggestion.entry_price,
                stop: suggestion.stop_loss,
                target: suggestion.take_profit,
                rr: suggestion.risk_reward,
                score: suggestion.confluence_score,
                reasons: suggestion.reasons,
                urgency: suggestion.urgency
            }
        });
        document.dispatchEvent(event);
    }
    
    drawTradeSuggestions() {
        // Draw trade entry, stop loss, and take profit levels on chart
        const suggestions = this.data.priceAction?.tradeSuggestions || [];
        if (suggestions.length === 0) return;
        
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        
        suggestions.forEach(suggestion => {
            // Only draw visible suggestions
            if (suggestion.choch_index < this.viewport.startIndex || 
                suggestion.choch_index > this.viewport.endIndex) return;
            
            const x = 60 + (suggestion.choch_index - this.viewport.startIndex) * 
                     (this.viewport.candleWidth + this.viewport.candleSpacing);
            
            const yEntry = chartHeight - ((suggestion.entry_price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yStop = chartHeight - ((suggestion.stop_loss - this.viewport.priceRange.min) / priceRange) * chartHeight;
            const yTarget = chartHeight - ((suggestion.take_profit - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            const isBuy = suggestion.type === 'buy';
            const urgencyColor = suggestion.urgency === 'immediate' ? '#dc2626' : 
                                suggestion.urgency === 'watch' ? '#ea580c' : '#6b7280';
            
            // Draw entry line
            this.ctx.strokeStyle = urgencyColor;
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([5, 3]);
            this.ctx.beginPath();
            this.ctx.moveTo(x, yEntry);
            this.ctx.lineTo(width - 80, yEntry);
            this.ctx.stroke();
            
            // Draw stop loss line (red)
            this.ctx.strokeStyle = '#991b1b';
            this.ctx.lineWidth = 1.5;
            this.ctx.beginPath();
            this.ctx.moveTo(x, yStop);
            this.ctx.lineTo(width - 80, yStop);
            this.ctx.stroke();
            
            // Draw take profit line (green)
            this.ctx.strokeStyle = '#166534';
            this.ctx.lineWidth = 1.5;
            this.ctx.beginPath();
            this.ctx.moveTo(x, yTarget);
            this.ctx.lineTo(width - 80, yTarget);
            this.ctx.stroke();
            
            this.ctx.setLineDash([]);
            
            // Draw labels on the right
            this.ctx.fillStyle = urgencyColor;
            this.ctx.font = 'bold 10px Arial';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(`ENTRY: ${suggestion.entry_price}`, width - 75, yEntry + 3);
            
            this.ctx.fillStyle = '#991b1b';
            this.ctx.fillText(`SL: ${suggestion.stop_loss}`, width - 75, yStop + 3);
            
            this.ctx.fillStyle = '#166534';
            this.ctx.fillText(`TP: ${suggestion.take_profit} (${suggestion.risk_reward}:1)`, width - 75, yTarget + 3);
            
            // Draw risk visualization
            const riskHeight = Math.abs(yStop - yEntry);
            const rewardHeight = Math.abs(yTarget - yEntry);
            
            // Risk zone (light red)
            this.ctx.fillStyle = isBuy ? 'rgba(153, 27, 27, 0.1)' : 'rgba(153, 27, 27, 0.1)';
            this.ctx.fillRect(x - 10, Math.min(yEntry, yStop), 20, riskHeight);
            
            // Reward zone (light green)
            this.ctx.fillStyle = isBuy ? 'rgba(22, 101, 52, 0.1)' : 'rgba(22, 101, 52, 0.1)';
            this.ctx.fillRect(x - 10, Math.min(yEntry, yTarget), 20, rewardHeight);
            
            // Draw confluence score badge
            if (suggestion.confluence_score >= 75) {
                this.ctx.fillStyle = suggestion.confluence_score >= 85 ? '#dc2626' : '#ea580c';
                this.ctx.beginPath();
                this.ctx.arc(x, yEntry - 25, 12, 0, Math.PI * 2);
                this.ctx.fill();
                
                this.ctx.fillStyle = '#ffffff';
                this.ctx.font = 'bold 9px Arial';
                this.ctx.textAlign = 'center';
                this.ctx.fillText(`${Math.round(suggestion.confluence_score)}`, x, yEntry - 21);
            }
        });
    }
    
    drawSwingPoints() {
        // Draw swing high/low points with labels and structure lines
        const swingPoints = this.data.priceAction?.swingPoints || [];
        if (swingPoints.length === 0) return;
        
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        
        // Filter visible swing points
        const visibleSwings = swingPoints.filter(s => 
            s.index >= this.viewport.startIndex && s.index <= this.viewport.endIndex
        );
        
        // Draw structure lines connecting highs and lows
        const swingHighs = visibleSwings.filter(s => s.type === 'high').sort((a, b) => a.index - b.index);
        const swingLows = visibleSwings.filter(s => s.type === 'low').sort((a, b) => a.index - b.index);
        
        // Draw trend line through swing highs
        if (swingHighs.length >= 2) {
            this.ctx.strokeStyle = 'rgba(220, 38, 38, 0.4)'; // Red for highs
            this.ctx.lineWidth = 1.5;
            this.ctx.setLineDash([5, 5]);
            this.ctx.beginPath();
            
            swingHighs.forEach((swing, i) => {
                const x = 60 + (swing.index - this.viewport.startIndex) * 
                         (this.viewport.candleWidth + this.viewport.candleSpacing);
                const y = chartHeight - ((swing.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
                
                if (i === 0) this.ctx.moveTo(x, y);
                else this.ctx.lineTo(x, y);
            });
            this.ctx.stroke();
        }
        
        // Draw trend line through swing lows
        if (swingLows.length >= 2) {
            this.ctx.strokeStyle = 'rgba(34, 197, 94, 0.4)'; // Green for lows
            this.ctx.lineWidth = 1.5;
            this.ctx.setLineDash([5, 5]);
            this.ctx.beginPath();
            
            swingLows.forEach((swing, i) => {
                const x = 60 + (swing.index - this.viewport.startIndex) * 
                         (this.viewport.candleWidth + this.viewport.candleSpacing);
                const y = chartHeight - ((swing.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
                
                if (i === 0) this.ctx.moveTo(x, y);
                else this.ctx.lineTo(x, y);
            });
            this.ctx.stroke();
        }
        
        this.ctx.setLineDash([]);
        
        // Draw swing point markers
        visibleSwings.forEach(swing => {
            const x = 60 + (swing.index - this.viewport.startIndex) * 
                     (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((swing.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            const isHigh = swing.type === 'high';
            
            // Draw marker
            this.ctx.fillStyle = isHigh ? '#dc2626' : '#22c55e';
            this.ctx.beginPath();
            
            if (isHigh) {
                // Triangle pointing down for highs
                this.ctx.moveTo(x, y - 8);
                this.ctx.lineTo(x - 6, y);
                this.ctx.lineTo(x + 6, y);
            } else {
                // Triangle pointing up for lows
                this.ctx.moveTo(x, y + 8);
                this.ctx.lineTo(x - 6, y);
                this.ctx.lineTo(x + 6, y);
            }
            this.ctx.closePath();
            this.ctx.fill();
            
            // Draw label
            this.ctx.fillStyle = isHigh ? '#f87171' : '#4ade80';
            this.ctx.font = 'bold 9px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.fillText(
                isHigh ? 'SH' : 'SL',
                x,
                isHigh ? y - 12 : y + 20
            );
            
            // Draw price
            this.ctx.fillStyle = '#9ca3af';
            this.ctx.font = '8px Arial';
            this.ctx.fillText(
                swing.price.toFixed(1),
                x,
                isHigh ? y - 22 : y + 30
            );
        });
    }
    
    drawPremiumZones() {
        // Highlight high-probability zones where multiple confluences overlap
        const choch = this.data.priceAction?.bos?.filter(b => b.type === 'choch' && b.confluence_score >= 75) || [];
        const orderBlocks = this.data.priceAction?.orderBlocks || [];
        const fvgs = this.data.priceAction?.fvgs?.filter(f => !f.is_filled) || [];
        
        if (choch.length === 0) return;
        
        const { width, height } = this.canvas;
        const chartHeight = height * 0.7;
        const priceRange = this.viewport.priceRange.max - this.viewport.priceRange.min;
        
        choch.forEach(chochPoint => {
            // Only show premium highlighting for visible CHoCH
            if (chochPoint.index < this.viewport.startIndex || chochPoint.index > this.viewport.endIndex) return;
            
            const x = 60 + (chochPoint.index - this.viewport.startIndex) * 
                     (this.viewport.candleWidth + this.viewport.candleSpacing);
            const y = chartHeight - ((chochPoint.price - this.viewport.priceRange.min) / priceRange) * chartHeight;
            
            // Find overlapping order blocks
            const nearbyOBs = orderBlocks.filter(ob => 
                Math.abs(ob.index - chochPoint.index) <= 5 && ob.is_active
            );
            
            // Find overlapping FVGs
            const nearbyFVGs = fvgs.filter(fvg => 
                chochPoint.fvg_aligned_indices && chochPoint.fvg_aligned_indices.includes(fvg.index)
            );
            
            // Calculate premium zone strength
            const confluenceCount = 1 + nearbyOBs.length + nearbyFVGs.length;
            
            // Only highlight if 3+ confluences (CHoCH + OB + FVG)
            if (confluenceCount < 3) return;
            
            // Determine zone size based on confluence
            const zoneWidth = 60 + (confluenceCount * 20);
            const zoneHeight = 40 + (confluenceCount * 15);
            
            // Premium zone color based on confluence strength
            const isBullish = chochPoint.direction === 'bullish';
            const baseColor = isBullish ? '30, 64, 175' : '124, 58, 237'; // Blue / Purple
            const opacity = Math.min(0.45, 0.15 + (confluenceCount * 0.08));
            
            // Draw premium zone glow
            const gradient = this.ctx.createRadialGradient(x, y, 0, x, y, zoneWidth);
            gradient.addColorStop(0, `rgba(${baseColor}, ${opacity})`);
            gradient.addColorStop(0.5, `rgba(${baseColor}, ${opacity * 0.5})`);
            gradient.addColorStop(1, `rgba(${baseColor}, 0)`);
            
            this.ctx.fillStyle = gradient;
            this.ctx.fillRect(x - zoneWidth/2, y - zoneHeight/2, zoneWidth, zoneHeight);
            
            // Draw premium zone border
            this.ctx.strokeStyle = `rgba(${baseColor}, 0.8)`;
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([3, 2]);
            this.ctx.strokeRect(x - zoneWidth/2, y - zoneHeight/2, zoneWidth, zoneHeight);
            this.ctx.setLineDash([]);
            
            // Draw "PREMIUM" label
            this.ctx.fillStyle = `rgba(${baseColor}, 1)`;
            this.ctx.font = 'bold 10px Arial';
            this.ctx.textAlign = 'center';
            this.ctx.fillText('★ PREMIUM', x, y - zoneHeight/2 - 5);
            
            // Draw confluence count badge
            this.ctx.fillStyle = '#fbbf24';
            this.ctx.beginPath();
            this.ctx.arc(x, y - zoneHeight/2 - 20, 10, 0, Math.PI * 2);
            this.ctx.fill();
            
            this.ctx.fillStyle = '#000000';
            this.ctx.font = 'bold 8px Arial';
            this.ctx.fillText(`${confluenceCount}★`, x, y - zoneHeight/2 - 16);
            
            // Draw reasons
            const reasons = [];
            if (nearbyOBs.length > 0) reasons.push('OB');
            if (nearbyFVGs.length > 0) reasons.push('FVG');
            if (chochPoint.fvg_confluence) reasons.push('Aligned');
            
            this.ctx.fillStyle = '#9ca3af';
            this.ctx.font = '9px Arial';
            this.ctx.fillText(reasons.join(' + '), x, y + zoneHeight/2 + 12);
        });
    }
    
    drawFibonacci() {
        // Auto-draw Fibonacci retracement levels from swing high to swing low
        if (!this.indicators.fibonacci) return;
        
        const swingPoints = this.data.priceAction?.swingPoints || [];
        if (swingPoints.length < 2) return;
        
        // Get canvas dimensions
        const rect = this.canvas.getBoundingClientRect();
        const width = rect.width;
        const height = rect.height;
        const chartHeight = height * 0.7;
        
        const priceMin = this.viewport.priceRange.min;
        const priceMax = this.viewport.priceRange.max;
        const priceRange = priceMax - priceMin;
        
        if (priceRange === 0) return;
        
        // Find highest high and lowest low from ALL swing points (not just visible)
        const swingHighs = swingPoints.filter(s => s.type === 'high');
        const swingLows = swingPoints.filter(s => s.type === 'low');
        
        if (swingHighs.length === 0 || swingLows.length === 0) return;
        
        // Get the highest high and lowest low
        const highestHigh = swingHighs.reduce((max, s) => s.price > max.price ? s : max, swingHighs[0]);
        const lowestLow = swingLows.reduce((min, s) => s.price < min.price ? s : min, swingLows[0]);
        
        // Calculate Y positions
        const highY = chartHeight - ((highestHigh.price - priceMin) / priceRange) * chartHeight;
        const lowY = chartHeight - ((lowestLow.price - priceMin) / priceRange) * chartHeight;
        
        // Fibonacci levels
        const fibLevels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
        const fibColors = ['#22c55e', '#4ade80', '#fbbf24', '#f59e0b', '#ef4444', '#dc2626', '#22c55e'];
        const fibLabels = ['0%', '23.6%', '38.2%', '50%', '61.8%', '78.6%', '100%'];
        
        // Draw fib levels
        fibLevels.forEach((level, i) => {
            const price = lowestLow.price + (highestHigh.price - lowestLow.price) * level;
            const y = chartHeight - ((price - priceMin) / priceRange) * chartHeight;
            
            // Draw level line across entire chart width
            this.ctx.strokeStyle = fibColors[i];
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([8, 4]);
            this.ctx.beginPath();
            this.ctx.moveTo(60, y);
            this.ctx.lineTo(width - 100, y);
            this.ctx.stroke();
            
            // Draw level label box on right
            const labelText = fibLabels[i];
            const priceText = price.toFixed(2);
            
            // Label background
            this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
            this.ctx.fillRect(width - 95, y - 10, 90, 20);
            
            // Label text
            this.ctx.fillStyle = fibColors[i];
            this.ctx.font = 'bold 11px Arial';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(labelText, width - 90, y + 4);
            
            // Price text
            this.ctx.font = '9px Arial';
            this.ctx.fillStyle = '#ffffff';
            this.ctx.fillText(priceText, width - 50, y + 4);
        });
        
        this.ctx.setLineDash([]);
        
        // Draw retracement zone shading
        this.ctx.fillStyle = 'rgba(59, 130, 246, 0.05)';
        this.ctx.fillRect(60, highY, width - 160, lowY - highY);
        
        // Draw "FIB" badge at top
        this.ctx.fillStyle = 'rgba(148, 163, 184, 0.9)';
        this.ctx.font = 'bold 12px Arial';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('📐 FIB', 70, 50);
    }
    
    drawVolumeProfile() {
        // Draw Volume Profile - horizontal histogram showing volume at price levels
        if (!this.indicators.volumeProfile) return;
        
        const candles = this.data.candles || [];
        if (candles.length === 0) return;
        
        // Get visible candles
        const visibleCandles = candles.slice(this.viewport.startIndex, this.viewport.endIndex + 1);
        if (visibleCandles.length === 0) return;
        
        // Get canvas dimensions
        const rect = this.canvas.getBoundingClientRect();
        const width = rect.width;
        const height = rect.height;
        const chartHeight = height * 0.7;
        
        const priceMin = this.viewport.priceRange.min;
        const priceMax = this.viewport.priceRange.max;
        const priceRange = priceMax - priceMin;
        
        if (priceRange === 0) return;
        
        // Create price buckets (30 levels)
        const bucketCount = 30;
        const bucketSize = priceRange / bucketCount;
        const volumeByPrice = new Array(bucketCount).fill(0);
        
        // Aggregate volume by price level
        visibleCandles.forEach(candle => {
            const avgPrice = (candle.high + candle.low) / 2;
            const bucketIndex = Math.min(
                Math.floor((avgPrice - priceMin) / bucketSize),
                bucketCount - 1
            );
            if (bucketIndex >= 0) {
                volumeByPrice[bucketIndex] += candle.volume;
            }
        });
        
        // Find max volume for scaling
        const maxVolume = Math.max(...volumeByPrice);
        if (maxVolume === 0) return;
        
        // Draw volume bars on the left side
        const maxBarWidth = 60;
        const barX = 65; // Start after price axis
        
        volumeByPrice.forEach((volume, i) => {
            if (volume === 0) return;
            
            const barWidth = (volume / maxVolume) * maxBarWidth;
            const priceLevel = priceMin + (i * bucketSize);
            const y = chartHeight - ((priceLevel - priceMin) / priceRange) * chartHeight;
            const barHeight = (bucketSize / priceRange) * chartHeight;
            
            // Color based on whether it's buy or sell dominated (using candle close position)
            const isHighVolume = volume > maxVolume * 0.7;
            const alpha = 0.3 + (volume / maxVolume) * 0.5;
            
            // Draw horizontal bar
            this.ctx.fillStyle = isHighVolume 
                ? `rgba(251, 191, 36, ${alpha})` // Amber for high volume
                : `rgba(6, 182, 212, ${alpha})`; // Cyan for normal
            this.ctx.fillRect(barX, y - barHeight/2, barWidth, barHeight);
            
            // Draw outline for high volume nodes
            if (isHighVolume) {
                this.ctx.strokeStyle = 'rgba(251, 191, 36, 0.8)';
                this.ctx.lineWidth = 1;
                this.ctx.strokeRect(barX, y - barHeight/2, barWidth, barHeight);
            }
        });
        
        // Draw "VP" label
        this.ctx.fillStyle = 'rgba(6, 182, 212, 0.8)';
        this.ctx.font = 'bold 10px Arial';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('📊 VP', 70, 65);
    }
    
    drawMultiTimeframeAlignment() {
        // Draw Multi-Timeframe Alignment - show higher timeframe BOS/CHoCH as reference lines
        if (!this.indicators.multiTimeframe) return;
        
        const mtfData = this.data.multiTimeframe || {};
        const h4Bos = mtfData.h4?.bos || [];
        const d1Bos = mtfData.d1?.bos || [];
        
        if (h4Bos.length === 0 && d1Bos.length === 0) return;
        
        // Get canvas dimensions
        const rect = this.canvas.getBoundingClientRect();
        const width = rect.width;
        const height = rect.height;
        const chartHeight = height * 0.7;
        
        const priceMin = this.viewport.priceRange.min;
        const priceMax = this.viewport.priceRange.max;
        const priceRange = priceMax - priceMin;
        
        if (priceRange === 0) return;
        
        // Draw H4 levels (orange dashed lines)
        h4Bos.forEach(bos => {
            const y = chartHeight - ((bos.price - priceMin) / priceRange) * chartHeight;
            
            // Draw dashed horizontal line
            this.ctx.strokeStyle = 'rgba(249, 115, 22, 0.6)'; // Orange
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([10, 5]);
            this.ctx.beginPath();
            this.ctx.moveTo(60, y);
            this.ctx.lineTo(width - 100, y);
            this.ctx.stroke();
            
            // Draw label
            this.ctx.fillStyle = 'rgba(249, 115, 22, 0.9)';
            this.ctx.font = 'bold 10px Arial';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(`H4 ${bos.type.toUpperCase()}`, width - 95, y - 5);
            this.ctx.font = '9px Arial';
            this.ctx.fillText(bos.price.toFixed(2), width - 95, y + 8);
        });
        
        // Draw D1 levels (purple dashed lines)
        d1Bos.forEach(bos => {
            const y = chartHeight - ((bos.price - priceMin) / priceRange) * chartHeight;
            
            // Draw dashed horizontal line
            this.ctx.strokeStyle = 'rgba(168, 85, 247, 0.6)'; // Purple
            this.ctx.lineWidth = 3;
            this.ctx.setLineDash([15, 5]);
            this.ctx.beginPath();
            this.ctx.moveTo(60, y);
            this.ctx.lineTo(width - 100, y);
            this.ctx.stroke();
            
            // Draw label
            this.ctx.fillStyle = 'rgba(168, 85, 247, 0.9)';
            this.ctx.font = 'bold 11px Arial';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(`D1 ${bos.type.toUpperCase()}`, width - 95, y - 5);
            this.ctx.font = '9px Arial';
            this.ctx.fillText(bos.price.toFixed(2), width - 95, y + 8);
        });
        
        this.ctx.setLineDash([]);
        
        // Draw MTF badge
        if (h4Bos.length > 0 || d1Bos.length > 0) {
            this.ctx.fillStyle = 'rgba(249, 115, 22, 0.9)';
            this.ctx.font = 'bold 11px Arial';
            this.ctx.textAlign = 'left';
            this.ctx.fillText('📈 MTF', 70, 80);
        }
    }
    
    drawTrendMeter() {
        // Draw trend strength meter in top right corner
        const summary = this.data.priceAction?.summary || {};
        const trendStrength = summary.trend_strength || 50;
        const trendDirection = summary.trend_direction || 'neutral';
        
        // Use logical canvas dimensions (CSS pixels), not scaled pixels
        const width = this.canvas.width / (window.devicePixelRatio || 1);
        const height = this.canvas.height / (window.devicePixelRatio || 1);
        
        const meterX = width - 110;
        const meterY = 35;
        const meterWidth = 95;
        const meterHeight = 55;
        
        // Draw background
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
        this.ctx.fillRect(meterX, meterY, meterWidth, meterHeight);
        
        // Draw border
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(meterX, meterY, meterWidth, meterHeight);
        
        // Draw title
        this.ctx.fillStyle = '#94a3b8';
        this.ctx.font = 'bold 9px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.fillText('TREND', meterX + meterWidth/2, meterY + 12);
        
        // Draw direction indicator
        let directionColor = '#9ca3af';
        let directionText = 'NEUTRAL';
        if (trendDirection === 'bullish') {
            directionColor = '#22c55e';
            directionText = 'BULLISH';
        } else if (trendDirection === 'bearish') {
            directionColor = '#ef4444';
            directionText = 'BEARISH';
        }
        
        this.ctx.fillStyle = directionColor;
        this.ctx.font = 'bold 10px Arial';
        this.ctx.fillText(directionText, meterX + meterWidth/2, meterY + 26);
        
        // Draw strength bar
        const barWidth = 75;
        const barHeight = 6;
        const barX = meterX + 10;
        const barY = meterY + 35;
        
        // Background bar
        this.ctx.fillStyle = '#374151';
        this.ctx.fillRect(barX, barY, barWidth, barHeight);
        
        // Strength bar color based on value
        let strengthColor = '#ef4444';
        if (trendStrength > 40) strengthColor = '#f59e0b';
        if (trendStrength > 60) strengthColor = '#22c55e';
        if (trendStrength > 80) strengthColor = '#10b981';
        
        this.ctx.fillStyle = strengthColor;
        this.ctx.fillRect(barX, barY, (trendStrength / 100) * barWidth, barHeight);
        
        // Draw percentage
        this.ctx.fillStyle = '#ffffff';
        this.ctx.font = '8px Arial';
        this.ctx.fillText(`${Math.round(trendStrength)}%`, meterX + meterWidth/2, meterY + 50);
    }
    
    drawRiskCalculator() {
        // Draw risk calculator overlay for active trade suggestions
        const suggestions = this.data.priceAction?.tradeSuggestions || [];
        if (suggestions.length === 0) return;
        
        // Use logical canvas dimensions
        const width = this.canvas.width / (window.devicePixelRatio || 1);
        const height = this.canvas.height / (window.devicePixelRatio || 1);
        
        const panelX = 70;
        const panelY = height - 85;
        const panelWidth = 180;
        const panelHeight = 70;
        
        // Draw panel background
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
        this.ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);
        
        // Draw title
        this.ctx.fillStyle = '#94a3b8';
        this.ctx.font = 'bold 9px Arial';
        this.ctx.textAlign = 'left';
        this.ctx.fillText('RISK CALCULATOR', panelX + 8, panelY + 14);
        
        // Calculate for first suggestion
        const suggestion = suggestions[0];
        const entry = suggestion.entry_price;
        const sl = suggestion.stop_loss;
        const tp = suggestion.take_profit;
        const riskPips = Math.abs(entry - sl);
        const rewardPips = Math.abs(tp - entry);
        const rr = riskPips > 0 ? (rewardPips / riskPips).toFixed(2) : '0.00';
        
        // Example calculation with $1000 account, 1% risk
        const accountBalance = 1000;
        const riskPercent = 1;
        const riskAmount = accountBalance * (riskPercent / 100);
        const positionSize = riskPips > 0 ? (riskAmount / (riskPips * 10)).toFixed(2) : '0.00';
        
        // Draw metrics
        this.ctx.fillStyle = '#e2e8f0';
        this.ctx.font = '8px Arial';
        this.ctx.fillText(`Entry: ${entry.toFixed(2)}`, panelX + 8, panelY + 28);
        this.ctx.fillText(`SL: ${sl.toFixed(2)}`, panelX + 8, panelY + 42);
        
        this.ctx.fillStyle = '#22c55e';
        this.ctx.fillText(`TP: ${tp.toFixed(2)}`, panelX + 8, panelY + 56);
        this.ctx.fillText(`R:R ${rr}`, panelX + 95, panelY + 28);
        this.ctx.fillText(`${positionSize} lots`, panelX + 95, panelY + 42);
        this.ctx.fillText(`$${riskAmount} risk`, panelX + 95, panelY + 56);
    }
    
    destroy() {
        // Clean up event listeners
        this.canvas.removeEventListener('mousemove', this.onMouseMove);
        this.canvas.removeEventListener('mousedown', this.onMouseDown);
        this.canvas.removeEventListener('mouseup', this.onMouseUp);
        this.canvas.removeEventListener('mouseleave', this.onMouseLeave);
        this.canvas.removeEventListener('wheel', this.onWheel);
        window.removeEventListener('resize', this.setupCanvas);
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TradingChart;
} else if (typeof window !== 'undefined') {
    window.TradingChart = TradingChart;
}
