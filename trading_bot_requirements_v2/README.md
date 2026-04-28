# Binance AI Trading Bot Requirements v2

ชุดเอกสาร requirements แยกตามส่วนระบบ:

## Frontend
หน้าจอสำหรับแสดงผลและควบคุมระบบ

## Backend Go
ระบบหลักสำหรับเชื่อม Binance, strategy, risk, order, backtest และ paper trading

## AI Python Service
ระบบสำหรับ dataset, feature engineering, training, model registry และ inference

## Recommended Build Order

### Phase 1 - Foundation
- Frontend Dashboard
- Frontend Market Watch
- Frontend Bot Control
- Backend Binance Connector
- Backend Data Collector
- Backend Market Data Service
- Backend Bot Runtime Controller

### Phase 2 - Strategy & Backtest
- Backend Strategy Engine
- Backend Risk Engine
- Backend Backtesting Engine
- Frontend Backtesting Result
- Frontend Risk Monitor
- Frontend Trade Logs

### Phase 3 - Paper Trading
- Backend Paper Trading Engine
- Backend Order Manager
- Backend Trade Log Service
- Frontend Paper Trading Page

### Phase 4 - AI
- AI Dataset Builder
- AI Feature Engineering
- AI Training Pipeline
- AI Model Registry
- AI Inference API
- Frontend AI Training Page

### Phase 5 - Live Trading & Alerts
- Backend Alert Service
- Frontend Alert Center
- Frontend Settings
- Backend Auth/User
- Backend API Gateway
- Live Trading mode with Kill Switch
