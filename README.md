# StreamHub — Вебплатформа соціальної взаємодії та аналітики мультимедійного контенту

Повнофункціональна мікросервісна платформа відеостримінгу з підтримкою адаптивного HLS-стримінгу, аналітики авторів, повнотекстового пошуку, OAuth-автентифікації та моніторингу в реальному часі.

---

## Технологічний стек

| Рівень | Технологія | Версія |
|--------|-----------|--------|
| **Backend (BFF)** | FastAPI | 0.129 |
| **Frontend** | React + TypeScript + Vite | 19 / 5.8 / 7.x |
| **База даних** | PostgreSQL | 16 |
| **ORM / Міграції** | SQLAlchemy + Alembic | 2.0 |
| **Кеш / Rate limiting** | Redis | latest |
| **Черга повідомлень** | RabbitMQ + FastStream | 3.8 |
| **Об'єктне сховище** | MinIO | latest |
| **Пошуковий рушій** | Elasticsearch | 9.2.0 |
| **Транскодування** | FFmpeg (GPU + CPU fallback) | — |
| **Управління секретами** | HashiCorp Vault | latest |
| **Шлюз** | NGINX | alpine |
| **Моніторинг** | Prometheus + Grafana + Loki | — |
| **Контейнеризація** | Docker + Docker Compose | 24+ |
| **Пакетний менеджер Python** | uv | — |
| **CI/CD** | GitLab CI (`.gitlab-ci.yml` + `ci/*.yml`, self-hosted runner з тегом `local`) | — |

---

## Системні вимоги

| Компонент | Мінімальна версія |
|-----------|------------------|
| Docker Engine | 24.0+ |
| Docker Compose | v2.20+ |
| Python | 3.12+ |
| Node.js | 20+ |
| npm | 10+ |
| uv | 0.4+ |
| Git | 2.40+ |
| RAM | 8 GB |
| Дисковий простір | 20 GB |
| OS | Linux / macOS / Windows 10+ (WSL2) |

---

## Розгортання

### 1. Клонування репозиторію

```bash
git clone https://github.com/feed7362/Video_streaming.git
cd Video_streaming
```

### 2. Налаштування змінних середовища

```bash
cp Docker/.env.example Docker/.env
# Відредагуйте Docker/.env: вкажіть паролі БД, ключі MinIO тощо
```

### 3. Запуск контейнерів

```bash
cd Docker
docker compose up -d
```

Запустяться 14 сервісів: nginx, bff, frontend, convertor, postgres, redis, rabbitmq, minio, elasticsearch, vault, prometheus, grafana, loki, promtail.

### 4. Ініціалізація Vault (лише при першому запуску)

Backend читає **всі** свої секрети з Vault (KV v2, mount `secret`), тому без цього кроку `bff` не стартує (`ValueError: Vault address or token not provided` або 503 на `/api/health/ready`).

```bash
# 4.1 Ініціалізувати Vault. Зберігши вивід: 2 unseal-ключі + root token.
docker exec vault vault operator init -key-shares=2 -key-threshold=2

# 4.2 Вписати VAULT_TOKEN, VAULT_UNSEAL_KEY_1, VAULT_UNSEAL_KEY_2 у Docker/.env
#     і перезапустити vault — vault/config/unseal.sh розпечатає його автоматично.
docker compose up -d --force-recreate vault

# 4.3 Увімкнути KV v2 на шляху secret/ (свіжий Vault його не має — лише dev-режим)
#     і записати секрети застосунку (значення мають збігатися з Docker/.env
#     там, де це ті самі облікові дані — БД, MinIO, Elasticsearch).
#     Після 4.2 контейнер уже має VAULT_TOKEN з .env, тому -e не потрібен.
docker exec vault sh -c '
  vault secrets enable -path=secret kv-v2
  vault kv put secret/database  POSTGRES_HOST=postgres POSTGRES_PORT=5432 POSTGRES_DB=<VIDEO_DB> POSTGRES_USER=<POSTGRES_USER> POSTGRES_PASSWORD=<POSTGRES_PASSWORD>
  vault kv put secret/s3        MINIO_ROOT_USER=<MINIO_ROOT_USER> MINIO_ROOT_PASSWORD=<MINIO_ROOT_PASSWORD> MINIO_ENDPOINT_URL=http://minio:9000 MINIO_REGION_NAME=us-east-1 BUCKET_NAMES=videos,video-thumbnails
  vault kv put secret/elastic   ELASTIC_HOST=http://elasticsearch:9200 ELASTIC_PASSWORD=<ELASTIC_PASSWORD>
  vault kv put secret/jwt       JWT_SECRET=<випадковий рядок, мінімум 32 символи>
  vault kv put secret/github_oauth GITHUB_CLIENT_ID=<id> GITHUB_CLIENT_SECRET=<secret> GITHUB_CALLBACK_URL=http://localhost/api/auth/github/callback FRONTEND_URL=http://localhost
  vault kv put secret/redis     REDIS_HOST=redis REDIS_PORT=6379
  vault kv put secret/rabbitmq  RABBITMQ_HOST=rabbitmq RABBITMQ_PORT=5672 RABBITMQ_USER=guest RABBITMQ_PASSWORD=guest
'

# 4.4 Перезапустити bff, щоб він підхопив секрети.
docker compose up -d --force-recreate bff
```

Назви полів — це точні імена з `backend/src/config.py` (`DatabaseSettings`, `S3Settings`, `ElasticSettings`, `JWTSettings`, `GitHubOAuthSettings`, `RedisSettings`, `RABBITMQSettings`). `JWT_SECRET` коротший за 32 символи або рівний значенню за замовчуванням відхиляється при старті.

### 5. Застосування міграцій бази даних

```bash
docker exec bff_service alembic upgrade head
```

### 6. Встановлення залежностей та збірка frontend (для розробки)

```bash
# Backend
cd backend
uv sync

# Frontend
cd frontend
npm install
npm run build
```

### 7. Наповнення тестовими даними (опціонально)

```bash
docker exec bff_service python -m utils.db_seeder
```

### 8. Перевірка стану сервісів

```bash
docker ps
curl http://localhost/api/health/ready
```

---

## Доступ до сервісів

| Сервіс | URL |
|--------|-----|
| Головна сторінка | http://localhost |
| API документація | http://localhost/api/docs |
| Grafana | http://localhost/grafana (admin / admin) |
| MinIO Console | http://localhost/minio/ui |
| RabbitMQ | http://localhost/rabbitmq |

---

## Структура проєкту

```
Video_streaming/
├── .gitlab-ci.yml           # Точка входу CI: stages + include ci/*.yml
├── .pre-commit-config.yaml  # gitleaks, detect-private-key, лінтери
├── ci/                      # GitLab CI jobs: python, node, security, deploy (build+Trivy+push), auto-pr
├── Docker/
│   ├── docker-compose.yml   # 14 сервісів локального стеку
│   ├── .env.example         # Шаблон інфраструктурних змінних (копіювати в .env)
│   └── postgres/            # Dockerfile + init-скрипт створення БД
├── backend/                 # FastAPI BFF (Python 3.12, uv)
│   ├── src/api/             # REST endpoint handlers (15 роутерів)
│   ├── src/services/        # Бізнес-логіка
│   ├── src/models/          # SQLAlchemy ORM моделі
│   ├── src/core/            # Спільне: пагінація, uuid5-ідентифікатори статусів
│   ├── src/infrastructure/  # Клієнти: DB, Redis, MinIO, ES, Vault, RabbitMQ
│   ├── alembic/             # Міграції БД
│   ├── tests/               # Unit-тести (мокована сесія)
│   ├── tests/integration/   # Тести на реальному Postgres через Testcontainers (потрібен Docker)
│   └── utils/               # Dev-тулінг: db_seeder, es_reindexer, seed_analytics
├── frontend/                # React 19 + TypeScript SPA (Vite)
│   ├── src/
│   │   ├── pages/           # 27 сторінок (lazy-loaded); Watch/ і Studio/ — розбиті на підкомпоненти
│   │   ├── components/      # UI-компоненти; common/ — спільні (Avatar), ui/ — Radix-примітиви
│   │   ├── hooks/queries/   # TanStack Query хуки (єдина пагінація/кеш)
│   │   └── lib/api/         # Axios API-клієнти + доменні типи
│   └── tests/               # Vitest + Testing Library
├── services/
│   ├── convertor/           # FFmpeg мікросервіс транскодування (RabbitMQ-консюмер)
│   └── moderation/          # НЕ РЕАЛІЗОВАНО: заглушка без Dockerfile, не в compose
├── gateway/
│   └── nginx.conf           # Reverse proxy + маршрутизація (лише HTTP, без TLS)
├── monitoring/              # Prometheus, Grafana, Loki, Promtail конфіги
├── vault/
│   └── config/              # vault.hcl (TLS наразі вимкнено) + unseal.sh (авто-розпечатування)
└── video-streaming/         # Helm chart — WIP: лише backend/convertor/frontend, без БД/черг/сховища
```

---

## Ліцензія

[Apache License 2.0](LICENSE)
