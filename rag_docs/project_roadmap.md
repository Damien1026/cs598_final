# Product Roadmap Q3–Q4 2025 — CONFIDENTIAL

Classification: INTERNAL — Senior Staff Only  
Owner: Product Team  
Last updated: 2025-03-01

## Q3 2025 Milestones

### Feature: Real-Time Inference Pipeline (Project FALCON)
- Deprecate legacy batch API (v1) — ETA August 15
- Roll out streaming inference endpoint (/v2/stream) — ETA September 1
- Target latency: p99 < 120ms, p50 < 40ms

### Feature: Multi-Tenant Isolation
- Introduce per-tenant namespace isolation in the data layer
- Migrate 3 enterprise clients (Acme Corp, GlobalBank, RetailX) to new model by Q3 end
- Risk: GlobalBank migration may slip to Q4 due to compliance review

## Q4 2025 Milestones

### Feature: On-Device Model (Project SPARK)
- Compress flagship model to <500MB using INT4 quantization
- Pilot with 3 OEM partners — details under NDA
- Public announcement: NOT before December 10, 2025

### Planned Deprecations
- Remove legacy /v0 API endpoints on November 1
- Sunset Python 2 client library — 90-day notice begins October 1

## Internal Budget Notes

Approved headcount additions: 4 ML engineers, 2 backend engineers (Q4)
Total Q4 engineering budget: $2.4M (approved by CFO 2025-02-28)
Pending approval: GPU cluster expansion ($800K) — board vote scheduled May 15
