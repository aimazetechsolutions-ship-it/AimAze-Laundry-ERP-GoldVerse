"""Export/import GoldVerse accounting master data through Odoo shell.

Run with:
  GOLDVERSE_MASTER_DATA_MODE=export|import
  GOLDVERSE_MASTER_DATA_FILE=/path/to/goldverse_accounting_master_data.json

The script is intentionally conservative: it updates or archives master data,
but does not delete accounts or journals.
"""

import json
import os
from pathlib import Path


MODE = os.environ.get("GOLDVERSE_MASTER_DATA_MODE", "export").strip().lower()
DATA_FILE = Path(os.environ.get("GOLDVERSE_MASTER_DATA_FILE", "config/goldverse_accounting_master_data.json"))
ARCHIVE_EXTRA_ACCOUNTS = os.environ.get("GOLDVERSE_ARCHIVE_EXTRA_ACCOUNTS", "1").strip() not in ("0", "false", "False")


def get_env():
    return globals()["env"]


def find_goldverse_company(odoo_env):
    Company = odoo_env["res.company"].with_context(active_test=False)
    for term in ("GoldVerse Premium (Pvt.) Limited", "GoldVerse", "Goldverse", "Gold Verse"):
        company = Company.search([("name", "ilike", term)], limit=1)
        if company:
            return company
    return odoo_env.company


def scoped_env(odoo_env, company):
    return odoo_env


def record_code(record):
    if not record:
        return ""
    return record.code or ""


def model_exists(odoo_env, model_name):
    return model_name in odoo_env.registry


def json_scalar(value):
    if value in (False, None, ""):
        return None
    if hasattr(value, "ids"):
        if not value:
            return None
        if len(value) == 1:
            return value.display_name or value.name or str(value.id)
        return [item.display_name or item.name or str(item.id) for item in value]
    return value


def account_domain(company, code=None):
    domain = [("company_ids", "in", company.id)]
    if code is not None:
        domain.append(("code", "=", code))
    return domain


def export_data():
    odoo_env = get_env()
    company = find_goldverse_company(odoo_env)
    odoo_env = scoped_env(odoo_env, company)

    Account = odoo_env["account.account"].with_context(active_test=False)
    Journal = odoo_env["account.journal"].with_context(active_test=False)
    Config = odoo_env["aimaze.laundry.account.config"].with_context(active_test=False)

    account_fields = Account._fields
    accounts = []
    for account in Account.search(account_domain(company) + [("active", "=", True)], order="code, name"):
        row = {
            "code": account.code or "",
            "name": account.name or "",
            "account_type": account.account_type or "",
            "reconcile": bool(account.reconcile),
            "active": bool(account.active),
        }
        for optional in ("non_trade", "cash_flow_type", "description", "note"):
            if optional in account_fields:
                value = json_scalar(account[optional])
                if value not in (False, None, ""):
                    row[optional] = value
        accounts.append(row)

    journal_fields = Journal._fields
    journals = []
    for journal in Journal.search([("company_id", "=", company.id), ("active", "=", True)], order="code, name"):
        row = {
            "name": journal.name or "",
            "type": journal.type or "",
            "code": journal.code or "",
            "default_account_code": record_code(journal.default_account_id),
            "default_account_name": journal.default_account_id.name or "",
            "refund_sequence": bool(journal.refund_sequence),
            "active": bool(journal.active),
        }
        for optional in ("sequence_override_regex", "show_on_dashboard"):
            if optional in journal_fields:
                value = journal[optional]
                if value not in (False, None, ""):
                    row[optional] = value
        journals.append(row)

    config = Config.search([("company_id", "=", company.id)], limit=1)
    config_data = {}
    if config:
        for field_name in (
            "advance_liability_account_id",
            "wallet_liability_account_id",
            "laundry_income_account_id",
            "delivery_income_account_id",
            "discount_account_id",
            "compensation_expense_account_id",
            "main_cash_account_id",
            "petty_cash_account_id",
        ):
            if field_name in Config._fields:
                config_data[field_name] = record_code(config[field_name])
        for field_name in ("cash_journal_id", "bank_journal_id", "card_journal_id", "cash_transfer_journal_id"):
            if field_name in Config._fields:
                config_data[field_name] = config[field_name].code or ""
        for field_name in ("default_tax_id", "uae_vat_tax_id", "pakistan_tax_id"):
            if field_name in Config._fields:
                tax = config[field_name]
                config_data[field_name] = {"name": tax.name or "", "amount": tax.amount} if tax else {}

    cash_expense_heads = []
    if model_exists(odoo_env, "goldverse.cash.expense.head"):
        ExpenseHead = odoo_env["goldverse.cash.expense.head"].with_context(active_test=False)
        for head in ExpenseHead.search([("company_id", "=", company.id), ("active", "=", True)], order="sequence, name"):
            cash_expense_heads.append(
                {
                    "name": head.name or "",
                    "account_code": record_code(head.account_id),
                    "sequence": head.sequence,
                    "active": bool(head.active),
                }
            )

    payload = {
        "schema": "goldverse_accounting_master_data.v1",
        "company": {"name": company.name, "id": company.id, "currency": company.currency_id.name or ""},
        "accounts": accounts,
        "journals": journals,
        "laundry_account_config": config_data,
        "cash_expense_heads": cash_expense_heads,
    }

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "Exported GoldVerse accounting master data: "
        f"{len(accounts)} accounts, {len(journals)} journals, "
        f"{len(cash_expense_heads)} cash expense heads -> {DATA_FILE}"
    )


def read_payload():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Master data file not found: {DATA_FILE}")
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if payload.get("schema") != "goldverse_accounting_master_data.v1":
        raise ValueError("Unsupported master data schema.")
    return payload


def find_account(Account, company, code):
    if not code:
        return Account.browse()
    return Account.search(account_domain(company, code), limit=1)


def find_journal(Journal, company, code, name=""):
    if code:
        journal = Journal.search([("company_id", "=", company.id), ("code", "=", code)], limit=1)
        if journal:
            return journal
    if name:
        return Journal.search([("company_id", "=", company.id), ("name", "=", name)], limit=1)
    return Journal.browse()


def import_accounts(odoo_env, company, payload):
    Account = odoo_env["account.account"].with_context(active_test=False)
    account_fields = Account._fields
    export_codes = set()
    created = updated = reactivated = archived = 0

    for row in payload.get("accounts", []):
        code = (row.get("code") or "").strip()
        if not code:
            continue
        export_codes.add(code)
        account = find_account(Account, company, code)
        vals = {
            "code": code,
            "name": row.get("name") or code,
            "account_type": row.get("account_type") or "asset_current",
            "reconcile": bool(row.get("reconcile")),
            "active": bool(row.get("active", True)),
        }
        if "company_ids" in account_fields:
            vals["company_ids"] = [(6, 0, [company.id])]
        for optional in ("non_trade", "cash_flow_type", "description", "note"):
            if optional in account_fields and optional in row:
                if account_fields[optional].type in ("many2one", "one2many", "many2many"):
                    continue
                vals[optional] = row.get(optional)
        if account:
            was_inactive = not account.active
            account.write(vals)
            updated += 1
            if was_inactive and account.active:
                reactivated += 1
        else:
            Account.create(vals)
            created += 1

    if ARCHIVE_EXTRA_ACCOUNTS:
        MoveLine = odoo_env["account.move.line"]
        extras = Account.search(account_domain(company) + [("active", "=", True)])
        for account in extras:
            if account.code in export_codes:
                continue
            has_moves = bool(MoveLine.search([("account_id", "=", account.id)], limit=1))
            if not has_moves:
                account.active = False
                archived += 1

    return {"created": created, "updated": updated, "reactivated": reactivated, "archived": archived}


def import_journals(odoo_env, company, payload):
    Account = odoo_env["account.account"].with_context(active_test=False)
    Journal = odoo_env["account.journal"].with_context(active_test=False)
    journal_fields = Journal._fields
    export_codes = set()
    created = updated = archived = 0

    for row in payload.get("journals", []):
        code = (row.get("code") or "").strip()
        name = (row.get("name") or code).strip()
        if not code and not name:
            continue
        if code:
            export_codes.add(code)
        journal = find_journal(Journal, company, code, name)
        default_account = find_account(Account, company, row.get("default_account_code") or "")
        vals = {
            "name": name,
            "type": row.get("type") or "general",
            "code": code,
            "company_id": company.id,
            "refund_sequence": bool(row.get("refund_sequence")),
            "active": bool(row.get("active", True)),
        }
        if default_account:
            vals["default_account_id"] = default_account.id
        for optional in ("sequence_override_regex", "show_on_dashboard"):
            if optional in journal_fields and optional in row:
                vals[optional] = row.get(optional)
        if journal:
            journal.write(vals)
            updated += 1
        else:
            Journal.create(vals)
            created += 1
    Move = odoo_env["account.move"]
    for journal in Journal.search([("company_id", "=", company.id), ("active", "=", True)]):
        if journal.code in export_codes:
            continue
        has_moves = bool(Move.search([("journal_id", "=", journal.id)], limit=1))
        if not has_moves:
            journal.active = False
            archived += 1
    return {"created": created, "updated": updated, "archived": archived}


def import_config(odoo_env, company, payload):
    Config = odoo_env["aimaze.laundry.account.config"].with_context(active_test=False)
    Account = odoo_env["account.account"].with_context(active_test=False)
    Journal = odoo_env["account.journal"].with_context(active_test=False)
    config = Config.search([("company_id", "=", company.id)], limit=1)
    if not config:
        config = Config.create({"company_id": company.id})
    data = payload.get("laundry_account_config") or {}
    vals = {}
    for field_name in (
        "advance_liability_account_id",
        "wallet_liability_account_id",
        "laundry_income_account_id",
        "delivery_income_account_id",
        "discount_account_id",
        "compensation_expense_account_id",
        "main_cash_account_id",
        "petty_cash_account_id",
    ):
        if field_name in Config._fields and data.get(field_name):
            account = find_account(Account, company, data[field_name])
            if account:
                vals[field_name] = account.id
    for field_name in ("cash_journal_id", "bank_journal_id", "card_journal_id", "cash_transfer_journal_id"):
        if field_name in Config._fields and data.get(field_name):
            journal = find_journal(Journal, company, data[field_name])
            if journal:
                vals[field_name] = journal.id
    if vals:
        config.write(vals)
    return {"updated_fields": sorted(vals)}


def import_cash_expense_heads(odoo_env, company, payload):
    if not model_exists(odoo_env, "goldverse.cash.expense.head"):
        return {"created": 0, "updated": 0, "archived": 0, "skipped": "model_missing"}
    Account = odoo_env["account.account"].with_context(active_test=False)
    ExpenseHead = odoo_env["goldverse.cash.expense.head"].with_context(active_test=False)
    exported_names = set()
    created = updated = 0
    for row in payload.get("cash_expense_heads", []):
        name = (row.get("name") or "").strip()
        if not name:
            continue
        exported_names.add(name)
        account = find_account(Account, company, row.get("account_code") or "")
        if not account:
            continue
        head = ExpenseHead.search([("company_id", "=", company.id), ("name", "=", name)], limit=1)
        vals = {
            "name": name,
            "account_id": account.id,
            "company_id": company.id,
            "sequence": row.get("sequence") or 10,
            "active": bool(row.get("active", True)),
        }
        if head:
            head.write(vals)
            updated += 1
        else:
            ExpenseHead.create(vals)
            created += 1
    archived = 0
    for head in ExpenseHead.search([("company_id", "=", company.id), ("active", "=", True)]):
        if head.name not in exported_names:
            head.active = False
            archived += 1
    return {"created": created, "updated": updated, "archived": archived}


def import_data():
    payload = read_payload()
    odoo_env = get_env()
    company = find_goldverse_company(odoo_env)
    odoo_env = scoped_env(odoo_env, company)
    results = {
        "accounts": import_accounts(odoo_env, company, payload),
        "journals": import_journals(odoo_env, company, payload),
        "laundry_account_config": import_config(odoo_env, company, payload),
        "cash_expense_heads": import_cash_expense_heads(odoo_env, company, payload),
    }
    odoo_env.cr.commit()
    print("Imported GoldVerse accounting master data:")
    print(json.dumps(results, indent=2, sort_keys=True))


if MODE == "export":
    export_data()
elif MODE == "import":
    import_data()
else:
    raise ValueError("GOLDVERSE_MASTER_DATA_MODE must be export or import.")
