# WhatsApp Integration Guide

Phase 4 enhances notification providers and queues for Meta WhatsApp Cloud API, Twilio WhatsApp, SMS, and email. It does not include paid credentials.

## Architecture

- Provider: API URL, auth type, sender, timeout, retry limit, webhook placeholder.
- Template: event, language, channel, company, and branch.
- Queue: retry count, next retry, external message ID, delivery status, provider payload.
- Integration logs: all prepared sends and failures are logged.

## Supported Events

- Order confirmed
- Pickup assigned
- Order ready
- Out for delivery
- Delivered
- Payment reminder
- Complaint update
- Wallet recharge
- Subscription expiry

## Production Connector Steps

1. Configure provider with Meta or Twilio account details.
2. Store live tokens in secure Odoo system parameters or a secret manager.
3. Enable the inactive scheduler after live connector code is added.
4. Add webhook controller for delivery/read status updates.
5. Monitor failed queue and retry counts daily.
