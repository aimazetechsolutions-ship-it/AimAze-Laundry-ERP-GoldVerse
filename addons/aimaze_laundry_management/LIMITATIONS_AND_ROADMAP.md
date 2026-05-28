# Known Limitations and Roadmap

## Known Limitations

- WhatsApp and SMS providers are placeholders through notification logs.
- Automatic advance-to-invoice reconciliation may need localization-specific configuration.
- Barcode printing uses simple tag reports; hardware printer layouts can be customized per client.
- Mobile app endpoints are not exposed yet.

## Roadmap

- Native mobile app API controllers
- WhatsApp Business Cloud API connector
- SMS gateway connector
- Route optimization map integration
- Advanced machine IoT utilization tracking
- Customer prepaid package auto-consumption
- Dedicated executive dashboard UI

## Phase 2 Limitations

- WhatsApp/SMS sending is intentionally queued only; live provider sending needs configured credentials and a future connector.
- Wallet accounting posts only when liability accounts and journals are configured.
- Invoice/payment reconciliation uses standard Odoo Accounting matching for auditability.
- Mobile APIs are authenticated placeholders for a future mobile app and are not public endpoints.

## Phase 3 Recommendations

- Native mobile app for driver and customer portal flows.
- Provider-specific WhatsApp Cloud API and SMS gateway connectors with retry policies.
- Barcode scanner hardware integration and QR label templates per printer size.
- Advanced reconciliation wizard for automatic advance/wallet matching against invoices.
- Real-time dashboard cards with OWL components.
- SLA breach automation for corporate contracts.

## Phase 4 Recommendations

- Build a real Flutter customer app and driver app against the authenticated API layer.
- Add provider-specific WhatsApp Cloud API and SMS gateway connectors with retry policies.
- Add queue-based background workers for high-volume notifications and AI analysis.
- Add scanner hardware profiles for USB barcode scanners, Zebra printers, and RFID readers.
- Add subscription auto-renewal billing and corporate monthly invoice automation.
- Add tenant onboarding automation for SaaS clients.

## Phase 4 Limitations

- Mobile APIs use authenticated Odoo sessions today; production token auth is documented but not enabled.
- WhatsApp/SMS delivery prepares provider payloads and retries, but live sending still requires a paid provider connector and credentials.
- Docker and Nginx files are deployment templates and must be adapted to the client domain and infrastructure.
- Backup scripts are examples and must be tested against the actual production backup path and offsite storage.

## Phase 5 Roadmap

- Token-based mobile authentication with refresh tokens and device management.
- Live WhatsApp Cloud API and Twilio connectors with delivery webhooks.
- Dedicated Flutter customer, driver, and staff apps.
- Real-time Owl dashboard with bus notifications.
- Queue worker integration for notifications, AI analysis, and heavy reports.
- SaaS onboarding wizard for tenant provisioning and client handover.

## Phase 5 Limitations

- Phase 5 uses lightweight styling and view inheritance; it does not bundle a heavy charting library.
- Dark mode is prepared through CSS structure but not enabled as a full alternate theme.
- Owl KPI widget is scaffolded for future live dashboards; current dashboard remains server-rendered for stability.

## Phase 6 Roadmap

- Token-based mobile authentication and production API gateway.
- Live WhatsApp provider adapters and delivery-status webhooks.
- Cached real-time dashboard metrics with bus notifications.
- Branded tenant onboarding wizard and industry-specific templates.
- Client-specific thermal label layouts for common printer sizes.
