# Deployment Guide

YouTube Web Automation Analysis Platform - 部署指南

## 目錄

1. [環境要求](#環境要求)
2. [本地開發部署](#本地開發部署)
3. [生產環境部署](#生產環境部署)
4. [Docker 部署](#docker-部署)
5. [監控與告警](#監控與告警)
6. [維護與運維](#維護與運維)

---

## 環境要求

### 系統要求

| 項目 | 最低要求 | 建議配置 |
|------|---------|---------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Disk | 20 GB | 100+ GB |
| OS | Ubuntu 20.04+ / macOS 12+ | Ubuntu 22.04 LTS |

### 軟體依賴

- Python 3.10+
- Docker & Docker Compose v2.0+
- Git
- PostgreSQL 15+ (生產環境)
- Redis 7+

---

## 本地開發部署

### 1. 克隆專案

```bash
git clone <repository-url>
cd YouTube-Web-Automation-Analysis
```

### 2. 建立虛擬環境

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 .\venv\Scripts\activate  # Windows
```

### 3. 安裝依賴

```bash
pip install -r requirements.txt
```

### 4. 配置環境變數

```bash
cp .env.example .env
# 編輯 .env 填入必要的配置
```

### 5. 啟動開發服務

```bash
# 啟動 Redis (使用 Docker)
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 啟動 FastAPI 開發伺服器
python -m src.app.main
# 或
uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000

# 啟動 Celery Worker (新終端機)
celery -A src.infrastructure.tasks.celery_app worker --loglevel=info

# 啟動 Celery Beat (新終端機)
celery -A src.infrastructure.tasks.celery_app beat --loglevel=info
```

### 6. 存取服務

- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

---

## 生產環境部署

### 1. 準備環境變數

```bash
cp .env.production .env.production.local
# 編輯並填入實際的生產環境值
```

**重要配置項目：**

```env
# 資料庫密碼 (必須修改)
DB_PASSWORD=your_secure_password_here

# YouTube API Key
YOUTUBE_API_KEY=your_production_api_key

# Flower 認證
FLOWER_BASIC_AUTH=admin:your_secure_password

# Grafana 密碼
GRAFANA_ADMIN_PASSWORD=your_secure_password
```

### 2. SSL 證書

```bash
# 生產環境：使用 Let's Encrypt
certbot certonly --webroot -w /var/www/certbot -d your-domain.com

# 開發/測試：使用自簽證書
cd nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -subj "/C=TW/ST=Taiwan/L=Taipei/O=Organization/CN=localhost"
```

### 3. 啟動生產環境

```bash
# 使用生產環境配置啟動
docker-compose -f docker-compose.production.yml up -d

# 查看日誌
docker-compose -f docker-compose.production.yml logs -f

# 查看服務狀態
docker-compose -f docker-compose.production.yml ps
```

### 4. 資料庫遷移

```bash
# 進入 API 容器執行遷移
docker-compose -f docker-compose.production.yml exec api \
  alembic upgrade head
```

---

## Docker 部署

### 服務架構

```
┌─────────────────────────────────────────────────────────────┐
│                      Nginx (Port 80/443)                     │
│                    Load Balancer & SSL                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    │                 │                 │
    ▼                 ▼                 ▼
┌───────┐       ┌───────────┐     ┌──────────┐
│  API  │       │  Grafana  │     │  Flower  │
│ :8000 │       │   :3000   │     │  :5555   │
└───┬───┘       └─────┬─────┘     └────┬─────┘
    │                 │                │
    │                 ▼                │
    │           ┌──────────┐           │
    │           │Prometheus│           │
    │           │  :9090   │           │
    │           └────┬─────┘           │
    │                │                 │
    ▼                ▼                 ▼
┌──────────────────────────────────────────┐
│              Redis (Port 6379)            │
│           Message Broker & Cache          │
└────────────────────┬─────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ Worker  │ │ Worker  │ │  Beat   │
    │   #1    │ │   #2    │ │Scheduler│
    └────┬────┘ └────┬────┘ └────┬────┘
         │           │           │
         └───────────┼───────────┘
                     │
                     ▼
            ┌───────────────┐
            │  PostgreSQL   │
            │   (Port 5432) │
            └───────────────┘
```

### 常用 Docker 命令

```bash
# 建構映像
docker-compose -f docker-compose.production.yml build

# 啟動所有服務
docker-compose -f docker-compose.production.yml up -d

# 停止所有服務
docker-compose -f docker-compose.production.yml down

# 重啟特定服務
docker-compose -f docker-compose.production.yml restart api

# 查看日誌
docker-compose -f docker-compose.production.yml logs -f api

# 擴展 worker 數量
docker-compose -f docker-compose.production.yml up -d --scale celery_worker=4

# 清理未使用的資源
docker system prune -a
```

---

## 監控與告警

### Prometheus Metrics

存取: http://localhost:9090 (或透過 Nginx: /prometheus/)

**主要指標：**

| 指標 | 說明 |
|------|------|
| `up{job="fastapi"}` | API 服務狀態 |
| `pg_up` | PostgreSQL 狀態 |
| `redis_up` | Redis 狀態 |
| `celery_task_received_total` | 收到的任務總數 |
| `celery_task_succeeded_total` | 成功的任務總數 |
| `celery_task_failed_total` | 失敗的任務總數 |

### Grafana Dashboard

存取: http://localhost:3000 (或透過 Nginx: /grafana/)

預設帳號: `admin` / `admin` (首次登入需修改)

**預設 Dashboard：**

- YouTube Automation - Overview
- System Resources
- Celery Tasks

### Flower (Celery 監控)

存取: http://localhost:5555 (或透過 Nginx: /flower/)

**功能：**

- 即時任務監控
- Worker 狀態
- 任務統計
- 任務歷史

### Health Check Endpoints

| Endpoint | 用途 | 說明 |
|----------|------|------|
| `GET /health` | 完整健康檢查 | 檢查所有元件 |
| `GET /health/live` | Liveness Probe | Kubernetes 存活探針 |
| `GET /health/ready` | Readiness Probe | Kubernetes 就緒探針 |
| `GET /health/metrics` | 應用指標 | 資料庫、快取統計 |
| `GET /health/ping` | 簡單 Ping | 基本連線檢查 |
| `GET /health/version` | 版本資訊 | 應用版本與功能狀態 |

### 告警規則

告警配置位於 `monitoring/alerts/application.yml`

**Critical 告警：**

- API 健康檢查失敗
- 資料庫連線中斷
- Redis 連線中斷
- 無活躍的 Celery Worker
- 系統資源耗盡

**Warning 告警：**

- 高 API 回應時間
- 資料庫連線數過高
- Celery 任務佇列增長
- YouTube API 配額警告

---

## 維護與運維

### 日常維護

```bash
# 清理舊的任務記錄 (30天以前)
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U youtube_user -d youtube_automation \
  -c "SELECT clean_old_task_executions(30);"

# 資料庫維護
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U youtube_user -d youtube_automation \
  -c "SELECT maintenance_vacuum_analyze();"

# 清理 Redis 快取
docker-compose -f docker-compose.production.yml exec redis \
  redis-cli FLUSHDB
```

### 備份

```bash
# 資料庫備份
docker-compose -f docker-compose.production.yml exec postgres \
  pg_dump -U youtube_user youtube_automation > backup_$(date +%Y%m%d).sql

# 還原資料庫
cat backup_20231201.sql | docker-compose -f docker-compose.production.yml exec -T postgres \
  psql -U youtube_user youtube_automation
```

### 更新部署

```bash
# 拉取最新程式碼
git pull origin main

# 重新建構映像
docker-compose -f docker-compose.production.yml build

# 滾動更新 (零停機)
docker-compose -f docker-compose.production.yml up -d --no-deps api

# 執行資料庫遷移
docker-compose -f docker-compose.production.yml exec api \
  alembic upgrade head
```

### 故障排除

**API 無回應：**

```bash
# 檢查服務狀態
docker-compose -f docker-compose.production.yml ps

# 檢查 API 日誌
docker-compose -f docker-compose.production.yml logs --tail=100 api

# 重啟 API 服務
docker-compose -f docker-compose.production.yml restart api
```

**Celery 任務堆積：**

```bash
# 檢查 Worker 狀態
docker-compose -f docker-compose.production.yml exec celery_worker \
  celery -A src.infrastructure.tasks.celery_app inspect active

# 擴展 Worker
docker-compose -f docker-compose.production.yml up -d --scale celery_worker=4

# 清空任務佇列 (謹慎使用)
docker-compose -f docker-compose.production.yml exec redis \
  redis-cli DEL celery
```

**資料庫連線問題：**

```bash
# 檢查連線數
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U youtube_user -d youtube_automation \
  -c "SELECT count(*) FROM pg_stat_activity;"

# 終止閒置連線
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U youtube_user -d youtube_automation \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND state_change < NOW() - INTERVAL '30 minutes';"
```

---

## 安全建議

1. **環境變數**: 永遠不要將敏感資訊提交到版本控制
2. **SSL**: 生產環境務必使用有效的 SSL 證書
3. **防火牆**: 只開放必要的端口 (80, 443)
4. **資料庫**: 使用強密碼並限制外部存取
5. **監控**: 設定適當的告警閾值
6. **備份**: 定期備份資料庫和重要配置
7. **更新**: 定期更新依賴套件和系統

---

## 聯絡支援

如有問題，請參考：

- GitHub Issues: [專案 Issues 頁面]
- 文件: [專案 Wiki]
