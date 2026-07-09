/** @odoo-module **/

/**
 * IAS-style statement header injected above the OCA account report sheet:
 *
 *   GOLDVERSE PREMIUM (PVT.) LIMITED
 *   STATEMENT OF PROFIT OR LOSS
 *   FOR THE PERIOD ENDED July 2026
 *
 * Ported from AimAze Hospitality PAK aimaze_accounting_kit/aimaze_statement_header.js
 * (class names re-prefixed to goldverse_* to avoid collisions).
 */

const TITLE_BY_REPORT = {
    "Balance Sheet": "STATEMENT OF FINANCIAL POSITION",
    "Profit and Loss": "STATEMENT OF PROFIT OR LOSS",
    "Cash Flow Statement": "STATEMENT OF CASH FLOWS",
    "Trial Balance": "TRIAL BALANCE",
    "General Ledger": "GENERAL LEDGER",
    "Aged Receivable": "AGED RECEIVABLE REPORT",
    "Aged Payable": "AGED PAYABLE REPORT",
    "Partner Ledger": "PARTNER LEDGER",
};

const DATE_PREFIX_BY_REPORT = {
    "Balance Sheet": "AS AT",
    "Profit and Loss": "FOR THE PERIOD ENDED",
    "Cash Flow Statement": "FOR THE PERIOD ENDED",
    "Trial Balance": "AS AT",
    "General Ledger": "FOR THE PERIOD",
    "Aged Receivable": "AS AT",
    "Aged Payable": "AS AT",
    "Partner Ledger": "FOR THE PERIOD",
};

function getCompanyName() {
    try {
        const info = (typeof odoo !== "undefined" ? odoo.session_info : null) || {};
        const companies = info.user_companies || {};
        const current = companies.current_company;
        const allowed = companies.allowed_companies || {};
        if (current && allowed[current]) {
            return allowed[current].name;
        }
        if (current && current.name) return current.name;
    } catch (e) { /* fall through */ }
    const navMenu = document.querySelector(".o_user_menu .dropdown-toggle");
    if (navMenu) return navMenu.textContent.trim();
    return "";
}

function getRawReportTitle() {
    const titleEl = document.querySelector(".o_account_report_titlebar h1");
    return titleEl ? titleEl.firstChild?.textContent?.trim() : "Balance Sheet";
}

function getReportTitle() {
    const raw = getRawReportTitle();
    return TITLE_BY_REPORT[raw] || raw.toUpperCase();
}

function getDatePrefix() {
    const raw = getRawReportTitle();
    return DATE_PREFIX_BY_REPORT[raw] || "AS AT";
}

function getAsAtLabel() {
    const btn = document.querySelector(".o_account_date_range_dropdown .o_account_filter_btn span");
    if (btn && btn.textContent.trim()) return btn.textContent.trim();
    return "";
}

function injectStatementHeader(reportSheet) {
    if (reportSheet.querySelector(".goldverse_statement_header")) return;

    const company = getCompanyName();
    const title = getReportTitle();
    const asAt = getAsAtLabel();
    const datePrefix = getDatePrefix();

    const wrap = document.createElement("div");
    wrap.className = "goldverse_statement_header";
    wrap.style.cssText = `
        text-align: left;
        padding: 14px 22px 14px 22px;
        border-bottom: 1px solid rgba(125, 104, 173, 0.18);
        font-family: 'Times New Roman', serif;
        line-height: 1.35;
    `;
    wrap.innerHTML = `
        <div class="goldverse_sh_company" style="
            font-size: 16px;
            font-weight: 700;
            color: #4a2978;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        ">${company || ""}</div>
        <div class="goldverse_sh_title" style="
            font-size: 13.5px;
            font-weight: 600;
            color: #4a2978;
            letter-spacing: 0.5px;
            margin-top: 3px;
        ">${title}</div>
        <div class="goldverse_sh_asat" style="
            font-size: 13.5px;
            font-weight: 600;
            color: #4a2978;
            letter-spacing: 0.5px;
            margin-top: 3px;
            text-transform: uppercase;
        ">${datePrefix} ${asAt}</div>
    `;
    reportSheet.insertBefore(wrap, reportSheet.firstChild);
}

function refreshHeader() {
    const asAt = getAsAtLabel();
    const datePrefix = getDatePrefix();
    const title = getReportTitle();
    const company = getCompanyName();
    document.querySelectorAll(".goldverse_sh_asat").forEach((el) => {
        el.textContent = `${datePrefix} ${asAt}`;
    });
    document.querySelectorAll(".goldverse_sh_title").forEach((el) => {
        if (title && el.textContent.trim() !== title) el.textContent = title;
    });
    document.querySelectorAll(".goldverse_sh_company").forEach((el) => {
        if (company && el.textContent.trim() !== company) el.textContent = company;
    });
}

function getCurrencyCode() {
    try {
        const info = (typeof odoo !== "undefined" ? odoo.session_info : null) || {};
        const companies = info.user_companies || {};
        const current = companies.current_company;
        const allowed = companies.allowed_companies || {};
        const co = current && allowed[current] ? allowed[current] : current;
        if (co && co.currency_id && info.currencies) {
            const cur = info.currencies[co.currency_id];
            if (cur && cur.name) return cur.name;
        }
    } catch (e) { /* fall through */ }
    const filters = document.querySelector(".o_account_report_filters");
    if (filters) {
        const btns = filters.querySelectorAll(".o_account_filter_btn");
        for (const b of btns) {
            const t = b.textContent.trim();
            const m = t.match(/^In\s+([A-Z.]{2,5})$/);
            if (m) return m[1].replace(/\./g, "");
        }
    }
    return "";
}

function replaceBalanceHeader() {
    const code = getCurrencyCode();
    const newText = code ? `Amount (${code})` : "Amount";
    document.querySelectorAll(".o_account_statement_measure").forEach((el) => {
        if (el.textContent.trim() !== newText) {
            el.textContent = newText;
        }
    });
}

function processSheets() {
    document.querySelectorAll(".o_account_report_sheet").forEach((sheet) => {
        try {
            injectStatementHeader(sheet);
        } catch (e) {
            console.warn("GoldVerse statement header:", e);
        }
    });
}

function bootstrap() {
    processSheets();
    replaceBalanceHeader();
    const observer = new MutationObserver(() => {
        processSheets();
        replaceBalanceHeader();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setInterval(() => {
        refreshHeader();
        replaceBalanceHeader();
    }, 1500);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
} else {
    bootstrap();
}
