# Testing Checklist

## Enterprise Phase 2 Checks

- Quick Counter Order opens from `AimAze Laundry ERP > Orders > Quick Counter Order`.
- Mobile number search finds an existing customer.
- Quick customer creation creates a customer with laundry metadata.
- Service price is fetched from the rate card when available, otherwise from service price.
- Manual discount is blocked for non-admin/non-branch-manager users.
- Counter order creates a confirmed laundry order and garment records.
- Garment buttons move lifecycle stages and create garment history.
- Order workflow queues notification records when templates exist.
- Wallet top-up posts when accounting configuration is complete.
- Wallet payment reduces order balance display.
- Subscription packages and customer subscriptions can be created.
- Driver mobile view shows only the logged-in driver's assigned jobs.
- Washing, Drying, Ironing, QC, and Packing screens show stage-filtered garments.
- Branch profitability computes revenue, discount, tax, costs, and margin for a date range.
- API placeholders require authenticated users and do not expose public data.

- [ ] UAE company exists with AED currency.
- [ ] Pakistan company exists with PKR currency.
- [ ] UAE VAT 5% configured on UAE service products.
- [ ] Pakistan tax configured manually on Pakistan service products.
- [ ] Branch users can only see allowed branch orders.
- [ ] Admin can see all branches.
- [ ] Walk-in order can be created and confirmed.
- [ ] Corporate contract can be created.
- [ ] Corporate monthly invoice action creates invoice for uninvoiced orders.
- [ ] Advance payment creates posted `account.payment`.
- [ ] Partial payment updates paid and balance amounts.
- [ ] Final payment sets order payment status to paid.
- [ ] Customer invoice creation opens `account.move`.
- [ ] Refund/credit note is available from Accounting menu.
- [ ] Pickup job can be created.
- [ ] Delivery job can be assigned and delivered.
- [ ] Pickup and delivery combined option is available.
- [ ] Garment tag numbers and barcodes are created.
- [ ] QC fail/rewash is recorded.
- [ ] Inventory usage can deduct stock when branch location is configured.
- [ ] Machine maintenance records can be created.
- [ ] Staff productivity score calculates.
- [ ] Complaints and compensation can be tracked.
- [ ] Portal user can view own laundry orders.
- [ ] Branch-wise sales pivot opens.
- [ ] Outstanding receivable report opens.

## Phase 3 Commercial Productization Checks

- [ ] Executive Dashboard opens and KPI cards load.
- [ ] Barcode Scan wizard opens from Operations and from an order smart button.
- [ ] Barcode scan can open a garment, order, or delivery package.
- [ ] Scan actions update garment/order stages.
- [ ] My Driver Jobs shows only assigned driver jobs.
- [ ] Driver form shows customer mobile, maps link, OTP placeholder, cash collection, proof fields, and failure reasons.
- [ ] Portal order list shows wallet and subscription summaries.
- [ ] Portal order detail shows garment progress.
- [ ] Portal pickup request creates a delivery request.
- [ ] Portal complaint creates a complaint linked to the customer.
- [ ] Initial Setup Wizard updates company, branch, journals, taxes, and accounting config.
- [ ] AI Analysis menu opens and sequence numbers are generated.
- [ ] Arabic translation placeholder loads without errors.
- [ ] Reports show branch TRN and customer TRN fields when configured.
- [ ] No local paths, SSH keys, passwords, or API secrets are present in module files.

## Phase 4 SaaS and Mobile Checks

- [ ] Mobile customer auth placeholder returns authenticated profile.
- [ ] Customer orders API returns only the logged-in customer records.
- [ ] Customer order detail includes lines, garments, and deliveries.
- [ ] Driver jobs API returns only assigned jobs.
- [ ] Driver update API can update delivery state, proof, signature, and cash collection.
- [ ] Staff scan API resolves barcode/RFID/order/package records.
- [ ] Staff QC API updates garment QC and rewash status.
- [ ] Notification retry fields and queue placeholder cron load correctly.
- [ ] Integration logs can be created from API/notification events.
- [ ] SaaS Tenant menu opens.
- [ ] Backup Configuration menu opens and can log a backup placeholder.
- [ ] Dockerfile, Compose file, Nginx example, backup script, and restore script are present.
- [ ] Demo XML remains demo-only and contains no personal/private data.
- [ ] Security scan shows no real credentials or SSH keys.

## Phase 5 UI/UX Checks

- [ ] AimAze design assets load without backend asset errors.
- [ ] Executive Dashboard opens with premium KPI cards.
- [ ] Quick Counter Order opens in touch-friendly layout.
- [ ] Order, garment, delivery, and complaint kanban views render.
- [ ] Order smart buttons open invoices, payments, deliveries, complaints, wallet, subscriptions, and notifications.
- [ ] Partner and branch smart buttons open related laundry records.
- [ ] Customer portal pages render with responsive cards.
- [ ] Receipt, advance receipt, delivery note, and garment tags print with branded layout.
- [ ] Mobile-width dashboard and POS layouts avoid horizontal scrolling.
