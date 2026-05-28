# API Readiness

AimAze Laundry ERP includes secure JSON-RPC placeholder routes for future customer, driver, and staff mobile apps. Current routes require authenticated Odoo users and should be protected with portal, API key, OAuth2, or signed-token middleware before public mobile release.

## Current Endpoint Structure

- `/aimaze_laundry/api/customer/session`: authenticated customer profile and active company.
- `/aimaze_laundry/api/orders`: customer order list scoped to the logged-in commercial partner.
- `/aimaze_laundry/api/order/status/<order_id>`: order status and progress.
- `/aimaze_laundry/api/garment/<barcode>`: garment barcode/RFID lookup.
- `/aimaze_laundry/api/staff/scan`: staff scan action for lifecycle updates.
- `/aimaze_laundry/api/driver/deliveries`: assigned driver jobs.
- `/aimaze_laundry/api/wallet/<partner_id>`: wallet balance lookup.
- `/aimaze_laundry/api/subscription/<partner_id>`: active subscription balances.
- `/aimaze_laundry/api/complaints`: customer complaint creation.

## Example JSON-RPC Request

```json
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "barcode": "GARM/2026/00001",
    "scan_action": "washing"
  },
  "id": 1
}
```

## Mobile App Recommendation

Use Odoo session auth for internal staff apps first. For public customer apps, add a token exchange controller, short-lived access tokens, refresh-token rotation, rate limits, device logging, and audit trails.
