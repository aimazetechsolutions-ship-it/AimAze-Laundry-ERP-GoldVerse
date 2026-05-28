# AI Roadmap

Phase 3 adds the `aimaze.laundry.ai.analysis` model as an AI-ready structure. It does not call any paid AI provider and does not store API credentials.

## Supported Future Use Cases

- Stain image analysis
- Fabric care recommendation
- Complaint sentiment review
- Delay risk prediction
- Revenue forecasting
- Customer churn risk scoring

## Production Integration Plan

1. Add a secure provider configuration model for AI vendors.
2. Store API secrets only in Odoo system parameters or an external secret manager.
3. Queue analysis jobs with `queue_job` or cron-based workers.
4. Keep human approval before applying AI recommendations.
5. Log requests and responses for audit without storing unnecessary personal data.

For UAE, Pakistan, and GCC deployments, obtain customer consent before using garment images or complaint text for AI processing.
