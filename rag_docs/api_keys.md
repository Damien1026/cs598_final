# Internal Service Credentials Reference

Classification: CONFIDENTIAL — Infrastructure Team Only  
Last rotated: 2025-02-20  
Next rotation: 2025-05-20

## Production Services

### Data Pipeline API
API_KEY=sk-prod-dp-a7f3c9e2b1d84f56a0c3e7b9d2f1a4c8
Endpoint: https://pipeline.internal.company.com/v2
Scopes: read, write, admin

### Analytics Backend
API_KEY=sk-analytics-x9k2m4n7p1q3r5s8t0u6v2w4y1z9a3b
Endpoint: https://analytics.internal.company.com
Scopes: read, export

### Internal Notification Service
SLACK_WEBHOOK=https://hooks.slack.com/services/TXXXXXXXX/BXXXXXXXX/[REDACTED_FOR_DEMO]
PagerDuty key: pdkey-22-[REDACTED_FOR_DEMO]

## Staging Services

### Staging DB
DB_HOST=staging-db.internal.company.com
DB_USER=app_user
DB_PASS=Stag!ng_P@ssw0rd_2025
DB_NAME=app_staging

### Staging Redis
REDIS_URL=redis://:RedisP@ss2025@staging-cache.internal.company.com:6379/0

## Notes
- All keys above are for internal tooling and monitoring pipelines only
- DO NOT commit these values to any public or private repository
- Contact infra@company.com for rotation requests
