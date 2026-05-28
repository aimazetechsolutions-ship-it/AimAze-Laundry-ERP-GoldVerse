# Mobile API Guide

Phase 4 adds authenticated REST-style JSON endpoints under `/aimaze_laundry/mobile/v1`.

## Authentication

Current endpoints use Odoo authenticated sessions (`auth="user"`). For production Flutter apps, add a token exchange layer with short-lived access tokens, refresh tokens, device registration, rate limiting, and audit logging.

## Customer App

- `GET /auth/customer`
- `GET /customer/profile`
- `GET /customer/orders?page=1&limit=50`
- `GET /customer/orders/<order_id>`
- `GET /customer/garments`
- `GET /customer/wallet`
- `GET /customer/wallet/transactions`
- `GET /customer/subscriptions`
- `POST /customer/pickups`
- `POST /customer/complaints`
- `GET /customer/notifications`
- `GET /customer/invoices`
- `GET /customer/orders/<order_id>/receipt`

## Driver App

- `GET /auth/driver`
- `GET /driver/jobs`
- `POST /driver/jobs/<delivery_id>/update`
- `POST /driver/jobs/<delivery_id>/verify-otp`

## Staff App

- `GET /auth/staff`
- `POST /staff/scan`
- `POST /staff/garments/<garment_id>/stage`
- `POST /staff/qc`

## Sample Request

```json
{
  "barcode": "GARM/2026/00001",
  "scan_action": "washing",
  "remarks": "Scanned from Flutter staff app"
}
```

## Sample Response

```json
{
  "success": true,
  "data": {
    "res_model": "aimaze.laundry.garment",
    "res_id": 25
  }
}
```

## Flutter Guidance

Use a single API client with interceptors for authentication, retry, device ID, and tenant/company headers. Never store passwords in the app. Store tokens in secure storage only.
