"""Import GoldVerse legacy EME sales as invoice-level accounting history.

Run through Odoo shell. The JSON payload path is read from
GOLDVERSE_LEGACY_IMPORT_JSON. By default this performs a rollback dry-run.
Set GOLDVERSE_LEGACY_IMPORT_COMMIT=1 to commit.
"""

import json
import os
import re
from pathlib import Path

from odoo import api, fields
from odoo.exceptions import UserError


IMPORT_MARKER = "GOLDVERSE_LEGACY_EME_SALES_IMPORT"
COMPANY_NAME = "GoldVerse Premium (Pvt.) Limited"
LEGACY_CUSTOMER_NAME = "Legacy EME Walk-in Customer"
LEGACY_PRODUCT_NAME = "Legacy Laundry Sale - EME"


def _money(value):
    return round(float(value or 0.0), 2)


def _date_or_false(value):
    if not value or str(value).lower() in ("nan", "nat", "none", "false"):
        return False
    return fields.Date.to_date(value)


def _account_by_name(env, company, name):
    Account = env["account.account"].sudo()
    domain = [("name", "=", name)]
    if "company_ids" in Account._fields:
        domain.append(("company_ids", "in", [company.id]))
    else:
        domain.append(("company_id", "=", company.id))
    account = Account.search(domain, limit=1)
    if not account:
        raise UserError("Missing account for legacy import: %s" % name)
    return account


def _prepare_env(env):
    company = env["res.company"].sudo().search([("name", "=", COMPANY_NAME)], limit=1)
    if not company:
        raise UserError("Missing company for legacy import: %s" % COMPANY_NAME)

    ctx = dict(env.context, allowed_company_ids=[company.id], force_company=company.id)
    company_env = api.Environment(env.cr, env.uid, ctx)

    partner = company_env["res.partner"].sudo().search([("name", "=", LEGACY_CUSTOMER_NAME)], limit=1)
    if not partner:
        partner_vals = {
            "name": LEGACY_CUSTOMER_NAME,
            "customer_rank": 1,
            "company_id": company.id,
        }
        if "laundry_customer_type" in company_env["res.partner"]._fields:
            partner_vals["laundry_customer_type"] = "b2c"
        partner = company_env["res.partner"].sudo().create(partner_vals)

    income_account = _account_by_name(company_env, company, "Laundry Income - B2C")
    receivable_account = _account_by_name(company_env, company, "Accounts Receivable")
    partner.with_context(goldverse_skip_duplicate_mobile_check=True).write(
        {"property_account_receivable_id": receivable_account.id}
    )

    sales_journal = company_env["account.journal"].sudo().search(
        [("company_id", "=", company.id), ("type", "=", "sale")],
        limit=1,
    )
    cash_journal = company_env["account.journal"].sudo().search(
        [("company_id", "=", company.id), ("name", "=", "Cash Sales")],
        limit=1,
    )
    if not sales_journal:
        raise UserError("Missing Sales journal for legacy import.")
    if not cash_journal:
        raise UserError("Missing Cash Sales journal for legacy import.")
    payment_method_line = cash_journal.inbound_payment_method_line_ids[:1]
    if not payment_method_line:
        raise UserError("Cash Sales journal has no inbound payment method line.")

    return {
        "env": company_env,
        "company": company,
        "partner": partner,
        "income_account": income_account,
        "sales_journal": sales_journal,
        "cash_journal": cash_journal,
        "payment_method_line": payment_method_line,
    }


def _reconcile_payment_to_invoice(invoice, payment):
    invoice_lines = invoice.line_ids.filtered(
        lambda line: line.account_id.account_type == "asset_receivable" and not line.reconciled
    )
    payment_lines = payment.move_id.line_ids.filtered(
        lambda line: line.account_id.account_type == "asset_receivable" and not line.reconciled
    )
    (invoice_lines + payment_lines).reconcile()


def _existing_row_indexes(Move, company):
    existing_moves = Move.search([("company_id", "=", company.id), ("narration", "ilike", IMPORT_MARKER)])
    existing = set()
    for move in existing_moves:
        match = re.search(r"%s:ROW:(\d+)" % re.escape(IMPORT_MARKER), move.narration or "")
        if match:
            existing.add(int(match.group(1)))
    return existing


def _chunks(records, size):
    for index in range(0, len(records), size):
        yield records[index : index + size]


def _import_rows(env, rows, commit=False, limit=0):
    prepared = _prepare_env(env)
    company_env = prepared["env"]
    quiet_context = {
        "tracking_disable": True,
        "mail_create_nolog": True,
        "mail_notrack": True,
        "no_reset_password": True,
    }
    Move = company_env["account.move"].sudo().with_context(**quiet_context)
    Payment = company_env["account.payment"].sudo().with_context(**quiet_context)
    existing_rows = _existing_row_indexes(Move, prepared["company"])
    chunk_size = int(os.environ.get("GOLDVERSE_LEGACY_IMPORT_CHUNK_SIZE") or 200)

    created_invoices = 0
    created_payments = 0
    skipped = 0
    totals = {
        "net_sale": 0.0,
        "cash_collected": 0.0,
        "receivable": 0.0,
    }

    selected_rows = rows[:limit or None]
    import_rows = []
    for row in selected_rows:
        if int(row["row_index"]) in existing_rows:
            skipped += 1
            continue
        net_sale = _money(row.get("net_sale"))
        if net_sale <= 0:
            skipped += 1
            continue
        import_rows.append(row)

    for chunk_no, chunk_rows in enumerate(_chunks(import_rows, chunk_size), start=1):
        invoice_vals_list = []
        prepared_rows = []
        for row in chunk_rows:
            row_index = int(row["row_index"])
            marker = "%s:ROW:%s" % (IMPORT_MARKER, row_index)
            net_sale = _money(row.get("net_sale"))
            invoice_date = _date_or_false(row["sale_date"])
            old_ref = row["old_ref"]
            narration = "%s\n%s\nSource file row: %s\nOld Inv No: %s" % (
                marker,
                row.get("source_file", ""),
                row_index,
                row.get("inv_no", ""),
            )
            invoice_vals_list.append(
                {
                    "move_type": "out_invoice",
                    "company_id": prepared["company"].id,
                    "partner_id": prepared["partner"].id,
                    "journal_id": prepared["sales_journal"].id,
                    "invoice_date": invoice_date,
                    "ref": old_ref,
                    "invoice_origin": old_ref,
                    "payment_reference": old_ref,
                    "narration": narration,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "%s (%s)" % (LEGACY_PRODUCT_NAME, old_ref),
                                "quantity": 1,
                                "price_unit": net_sale,
                                "account_id": prepared["income_account"].id,
                            },
                        )
                    ],
                }
            )
            prepared_rows.append(row)

        invoices = Move.create(invoice_vals_list)
        invoices.action_post()
        created_invoices += len(invoices)

        payment_vals_list = []
        payment_invoices = []
        for invoice, row in zip(invoices, prepared_rows):
            cash_collected = _money(row.get("cash_collected"))
            if cash_collected <= 0:
                continue
            old_ref = row["old_ref"]
            invoice_date = _date_or_false(row["sale_date"])
            payment_date = _date_or_false(row.get("payment_date")) or invoice_date
            payment_vals_list.append(
                {
                    "company_id": prepared["company"].id,
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": prepared["partner"].id,
                    "amount": cash_collected,
                    "date": payment_date,
                    "journal_id": prepared["cash_journal"].id,
                    "payment_method_line_id": prepared["payment_method_line"].id,
                    "memo": "%s PAYMENT" % old_ref,
                    "destination_account_id": invoice.line_ids.filtered(
                        lambda line: line.account_id.account_type == "asset_receivable"
                    )[:1].account_id.id,
                }
            )
            payment_invoices.append(invoice)

        if payment_vals_list:
            payments = Payment.create(payment_vals_list)
            payments.action_post()
            for invoice, payment in zip(payment_invoices, payments):
                _reconcile_payment_to_invoice(invoice, payment)
            created_payments += len(payments)

        for row in prepared_rows:
            totals["net_sale"] += _money(row.get("net_sale"))
            totals["cash_collected"] += _money(row.get("cash_collected"))
            totals["receivable"] += _money(row.get("receivable"))

        last_invoice_date = _date_or_false(prepared_rows[-1]["sale_date"])
        if commit:
            env.cr.commit()
        print(
            json.dumps(
                {
                    "chunk": chunk_no,
                    "created_invoices": created_invoices,
                    "created_payments": created_payments,
                    "skipped": skipped,
                    "last_invoice_date": str(last_invoice_date),
                },
                sort_keys=True,
            ),
            flush=True,
        )

    totals = {key: _money(value) for key, value in totals.items()}
    result = {
        "commit": bool(commit),
        "created_invoices": created_invoices,
        "created_payments": created_payments,
        "skipped": skipped,
        "totals": totals,
    }
    if commit:
        env.cr.commit()
        result["transaction"] = "committed"
    else:
        env.cr.rollback()
        result["transaction"] = "rolled_back"
    return result


payload_path = os.environ.get("GOLDVERSE_LEGACY_IMPORT_JSON")
if not payload_path:
    raise UserError("Set GOLDVERSE_LEGACY_IMPORT_JSON before running this script.")

payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
rows = payload["rows"]
limit = int(os.environ.get("GOLDVERSE_LEGACY_IMPORT_LIMIT") or 0)
commit = os.environ.get("GOLDVERSE_LEGACY_IMPORT_COMMIT") == "1"
result = _import_rows(env, rows, commit=commit, limit=limit)
print(json.dumps(result, indent=2, sort_keys=True))
