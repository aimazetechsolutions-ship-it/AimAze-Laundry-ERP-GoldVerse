/** @odoo-module */

import { download } from "@web/core/network/download";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { Component, onWillStart, useExternalListener, useState } from "@odoo/owl";

const dateString = (date) => [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
].join("-");

const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
];

const shortMonthNames = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const periodOptions = [
    { key: "month", label: "Month" },
    { key: "quarter", label: "Quarter" },
    { key: "year", label: "Year" },
    { key: "custom", label: "Custom Dates..." },
];

const quickPeriodOptions = [
    { key: "today", label: "Today" },
    { key: "mtd", label: "MTD" },
    { key: "ytd", label: "YTD" },
    { key: "custom", label: "Custom" },
];

const parseDate = (value) => {
    const fallback = new Date();
    if (!value) {
        return fallback;
    }
    const [year, month, day] = String(value).split("-").map((part) => Number(part));
    if (!year || !month || !day) {
        return fallback;
    }
    return new Date(year, month - 1, day);
};

const addMonths = (date, months) => new Date(date.getFullYear(), date.getMonth() + months, 1);

const periodBounds = (period, anchorDate, customStart, customEnd) => {
    const anchor = parseDate(anchorDate || dateString(new Date()));
    let start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    let end = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    if (period === "today") {
        start = anchor;
        end = anchor;
    } else if (period === "mtd") {
        end = anchor;
    } else if (period === "ytd") {
        start = new Date(anchor.getFullYear(), 0, 1);
        end = anchor;
    } else if (period === "quarter") {
        const quarterStart = Math.floor(anchor.getMonth() / 3) * 3;
        start = new Date(anchor.getFullYear(), quarterStart, 1);
        end = new Date(anchor.getFullYear(), quarterStart + 3, 0);
    } else if (period === "year") {
        start = new Date(anchor.getFullYear(), 0, 1);
        end = new Date(anchor.getFullYear(), 11, 31);
    } else if (period === "custom") {
        start = parseDate(customStart || anchorDate);
        end = parseDate(customEnd || customStart || anchorDate);
    }
    const startDate = dateString(start);
    let endDate = dateString(end);
    if (endDate < startDate) {
        endDate = startDate;
    }
    return { startDate, endDate };
};

const periodDisplay = (period, bounds) => {
    const start = parseDate(bounds.startDate);
    const end = parseDate(bounds.endDate);
    if (period === "today") {
        return "Today";
    }
    if (period === "mtd") {
        return "MTD";
    }
    if (period === "ytd") {
        return "YTD";
    }
    if (period === "month") {
        return `${monthNames[start.getMonth()]} ${start.getFullYear()}`;
    }
    if (period === "quarter") {
        return `${shortMonthNames[start.getMonth()]} - ${shortMonthNames[end.getMonth()]} ${end.getFullYear()}`;
    }
    if (period === "year") {
        return `${start.getFullYear()}`;
    }
    return "Custom";
};

const compactDateRangeDisplay = (bounds) => {
    const start = parseDate(bounds.startDate);
    const end = parseDate(bounds.endDate);
    const sameYear = start.getFullYear() === end.getFullYear();
    const sameMonth = sameYear && start.getMonth() === end.getMonth();
    const startText = sameYear
        ? `${shortMonthNames[start.getMonth()]} ${start.getDate()}`
        : `${shortMonthNames[start.getMonth()]} ${start.getDate()}, ${start.getFullYear()}`;
    const endText = sameMonth
        ? `${shortMonthNames[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`
        : `${shortMonthNames[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
    return `${startText} - ${endText}`;
};

class InteractiveAccountReport extends Component {
    static template = "base_accounting_kit.InteractiveAccountReport";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.reportKey = this.props.action.context.report_key || "profit_and_loss";
        this.drillBack = this.props.action.context.drill_back || null;
        const now = new Date();
        const today = dateString(now);
        const defaultPeriod = "mtd";
        const defaultBounds = periodBounds(defaultPeriod, today, null, null);
        const contextOptions = this.props.action.context.default_options || {};
        const initialOptions = {
            period: defaultPeriod,
            anchor_date: today,
            date_from: defaultBounds.startDate,
            date_to: defaultBounds.endDate,
            ...contextOptions,
        };
        this.state = useState({
            loading: true,
            dateMenuOpen: false,
            journalMenuOpen: false,
            comparisonMenuOpen: false,
            openLineMenuId: null,
            searchTerm: contextOptions.account_search || "",
            report: null,
            unfoldedLineIds: [],
            pendingDateFrom: initialOptions.date_from,
            pendingDateTo: initialOptions.date_to,
            pendingCmpFrom: initialOptions.comparison_date_from || "",
            pendingCmpTo: initialOptions.comparison_date_to || "",
            options: initialOptions,
        });
        onWillStart(() => this.loadReport());
        // Close any open filter dropdown / line menu when clicking outside it.
        useExternalListener(window, "click", (ev) => this._onOutsideClick(ev));
    }

    _onOutsideClick(ev) {
        const target = ev.target;
        const closest = target && target.closest ? (sel) => target.closest(sel) : () => null;
        if (!closest(".o_account_filter_dropdown") && !closest(".o_account_custom_date_popover")) {
            this.state.comparisonMenuOpen = false;
            this.state.dateMenuOpen = false;
            this.state.journalMenuOpen = false;
        }
        if (!closest(".o_account_line_action_wrap")) {
            this.state.openLineMenuId = null;
        }
    }

    get periodOptions() {
        return periodOptions;
    }

    get quickPeriodOptions() {
        return quickPeriodOptions;
    }

    get report() {
        return this.state.report || { title: "", columns: [], lines: [], journals: [], options: this.state.options };
    }

    get options() {
        return this.report.options || this.state.options;
    }

    get bounds() {
        return periodBounds(
            this.options.period || "year",
            this.options.anchor_date || this.options.date_to,
            this.options.date_from,
            this.options.date_to
        );
    }

    get periodMenuLabel() {
        return periodDisplay(this.options.period || "year", this.bounds);
    }

    get dateRangeButtonLabel() {
        return compactDateRangeDisplay(this.bounds);
    }

    get isAgedPartnerReport() {
        return ["aged_receivable", "aged_payable"].includes(this.reportKey);
    }

    get isTrialBalanceReport() {
        return this.reportKey === "trial_balance";
    }

    get isGeneralLedgerReport() {
        return this.reportKey === "general_ledger";
    }

    get showReportSearch() {
        return this.isTrialBalanceReport || this.isGeneralLedgerReport;
    }

    get reportSearchTerm() {
        return this.state.searchTerm;
    }

    get dateFilterLabel() {
        if (this.isAgedPartnerReport) {
            return `As of ${this.formatDateLabel(this.options.date_to || this.options.anchor_date)}`;
        }
        return this.periodMenuLabel;
    }

    get agedAccountLabel() {
        return this.reportKey === "aged_payable" ? "Account: Payable" : "Account: Receivable";
    }

    get agedPeriodLengthLabel() {
        return `${Number(this.options.period_length || 30)} Days`;
    }

    get showDebitCredit() {
        return this.isStatementReport;
    }

    get showComparisonFilter() {
        // Only Balance Sheet + P&L can render comparison columns today. Trial
        // Balance keeps its fixed-column layout and Cash Flow shows a single
        // period, so the comparison dropdown stays hidden there.
        return this.isComparableStatement;
    }

    get isComparableStatement() {
        return ["balance_sheet", "profit_and_loss"].includes(this.reportKey);
    }

    get isBalanceSheetReport() {
        return this.reportKey === "balance_sheet";
    }

    get comparisonMode() {
        return this.options.comparison || "none";
    }

    get comparisonCount() {
        return Number(this.options.comparison_count || 1);
    }

    get hasComparison() {
        return this.showComparisonFilter && this.comparisonMode !== "none";
    }

    get comparisonLabel() {
        return this.options.comparison_label || "Comparison";
    }

    get comparisonCustomLabel() {
        // Balance Sheet compares a point in time; statements compare a range.
        return this.isBalanceSheetReport ? "Specific Date" : "Custom Dates";
    }

    get periodOrder() {
        return this.options.period_order || "ascending";
    }

    get isStatementReport() {
        return ["profit_and_loss", "balance_sheet", "cash_flow"].includes(this.reportKey);
    }

    get showStatementHeader() {
        // Hide the single-period sticky header once comparison columns are shown,
        // otherwise it lies about the range the numbers cover.
        return this.isStatementReport && !this.options.debit_credit && !this.hasComparison;
    }

    get showDisplayAccount() {
        return ["bank_book", "cash_book"].includes(this.reportKey);
    }

    get showInitialBalance() {
        return ["bank_book", "cash_book"].includes(this.reportKey);
    }

    get showPartnerType() {
        return ["partner_ledger", "aged_partner_balance"].includes(this.reportKey);
    }

    get showReconciled() {
        return this.reportKey === "partner_ledger";
    }

    get showAmountCurrency() {
        return ["partner_ledger", "journal_audit"].includes(this.reportKey);
    }

    get showSortBy() {
        return ["journal_audit", "bank_book", "cash_book"].includes(this.reportKey);
    }

    get showPeriodLength() {
        return this.reportKey === "aged_partner_balance";
    }

    get agedHeaderColspan() {
        return Math.max((this.report.columns || []).length - 2, 1);
    }

    get hasLines() {
        return Boolean(this.report.lines && this.report.lines.length);
    }

    get visibleLines() {
        const unfolded = new Set(this.state.unfoldedLineIds || []);
        let lines = (this.report.lines || []).filter((line) => !line.parent_id || unfolded.has(line.parent_id));
        if (this.isTrialBalanceReport && this.state.searchTerm) {
            const search = this.state.searchTerm.toLowerCase();
            lines = lines.filter((line) => {
                const values = line.values || {};
                return String(values.name || line.name || "").toLowerCase().includes(search) || line.is_total;
            });
        }
        return lines;
    }

    async loadReport(options = null) {
        this.state.loading = true;
        const nextOptions = options || this.state.options;
        const payload = await this.orm.call("account.interactive.report", "get_report", [this.reportKey, nextOptions]);
        const lineIds = new Set((payload.lines || []).map((line) => line.id));
        const defaultUnfolded = (payload.lines || []).filter((line) => line.default_unfolded).map((line) => line.id);
        const previousUnfolded = (this.state.unfoldedLineIds || []).filter((lineId) => lineIds.has(lineId));
        this.state.report = payload;
        this.state.options = payload.options;
        this.state.unfoldedLineIds = [...new Set([...defaultUnfolded, ...previousUnfolded])];
        this.state.searchTerm = this.isGeneralLedgerReport ? (payload.options.account_search || "") : this.state.searchTerm;
        this.state.openLineMenuId = null;
        this.state.loading = false;
    }

    updateOptions(values) {
        const options = { ...this.state.options, ...values };
        return this.loadReport(options);
    }

    toggleDateMenu() {
        if (!this.state.dateMenuOpen) {
            this.prepareCustomRange();
        }
        this.state.dateMenuOpen = !this.state.dateMenuOpen;
        this.state.journalMenuOpen = false;
        this.state.comparisonMenuOpen = false;
        this.state.openLineMenuId = null;
    }

    async goBackToParent() {
        if (!this.drillBack) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.client",
            tag: "base_accounting_kit.interactive_account_report",
            name: this.drillBack.label || "Report",
            context: {
                report_key: this.drillBack.report_key,
                default_options: this.drillBack.options,
            },
        });
    }

    toggleJournalMenu() {
        this.state.journalMenuOpen = !this.state.journalMenuOpen;
        this.state.dateMenuOpen = false;
        this.state.comparisonMenuOpen = false;
        this.state.openLineMenuId = null;
    }

    selectPeriod(period) {
        if (period === "custom") {
            this.prepareCustomRange();
            this.state.dateMenuOpen = true;
            return this.updateOptions({ period: "custom" });
        }
        const anchor = this.options.anchor_date || this.options.date_to || dateString(new Date());
        const bounds = periodBounds(period, anchor, this.options.date_from, this.options.date_to);
        this.state.dateMenuOpen = false;
        return this.updateOptions({
            period,
            anchor_date: anchor,
            date_from: bounds.startDate,
            date_to: bounds.endDate,
        });
    }

    shiftPeriod(period, delta, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        if (period === "custom") {
            return;
        }
        const step = period === "quarter" ? delta * 3 : period === "year" ? delta * 12 : delta;
        const anchor = dateString(addMonths(parseDate(this.options.anchor_date || this.options.date_to), step));
        const bounds = periodBounds(period, anchor, this.options.date_from, this.options.date_to);
        this.state.dateMenuOpen = true;
        return this.updateOptions({
            period,
            anchor_date: anchor,
            date_from: bounds.startDate,
            date_to: bounds.endDate,
        });
    }

    periodOptionLabel(period) {
        const bounds = periodBounds(period, this.options.anchor_date || this.options.date_to, this.options.date_from, this.options.date_to);
        return periodDisplay(period, bounds);
    }

    quickPeriodClass(period) {
        return `o_account_quick_period_btn ${this.options.period === period ? "active" : ""}`;
    }

    periodRowClass(period) {
        return `o_account_period_row ${this.options.period === period ? "active" : ""}`;
    }

    selectQuickPeriod(period) {
        const today = dateString(new Date());
        if (period === "custom") {
            this.prepareCustomRange();
            this.state.dateMenuOpen = true;
            return this.updateOptions({ period: "custom" });
        }
        const bounds = periodBounds(period, today, this.options.date_from, this.options.date_to);
        this.state.dateMenuOpen = false;
        return this.updateOptions({
            period,
            anchor_date: today,
            date_from: bounds.startDate,
            date_to: bounds.endDate,
        });
    }

    setCustomStart(value) {
        this.setPendingCustomStart(value);
    }

    setCustomEnd(value) {
        this.setPendingCustomEnd(value);
    }

    prepareCustomRange() {
        this.state.pendingDateFrom = this.options.date_from || this.bounds.startDate;
        this.state.pendingDateTo = this.options.date_to || this.bounds.endDate;
    }

    setPendingCustomStart(value) {
        // The native <input type="date"> can fire `change` with an empty
        // value while the user is mid-edit (e.g. they cleared the year
        // before typing a new one, leaving an invalid composite date).
        // The previous implementation defaulted to today in that case,
        // silently snapping the field back as the user typed. Preserve
        // the raw input here and validate on Apply instead.
        this.state.pendingDateFrom = value || "";
        if (value && this.state.pendingDateTo && this.state.pendingDateTo < value) {
            this.state.pendingDateTo = value;
        }
    }

    setPendingCustomEnd(value) {
        this.state.pendingDateTo = value || "";
        if (value && this.state.pendingDateFrom && value < this.state.pendingDateFrom) {
            this.state.pendingDateTo = this.state.pendingDateFrom;
        }
    }

    cancelCustomRange() {
        this.state.pendingDateFrom = this.options.date_from;
        this.state.pendingDateTo = this.options.date_to;
        this.state.dateMenuOpen = false;
    }

    applyCustomRange() {
        // Fall back to the current options (or today) only if the user
        // left the field truly blank at Apply time, not on every keystroke.
        const start = this.state.pendingDateFrom
            || this.options.date_from
            || dateString(new Date());
        const rawEnd = this.state.pendingDateTo
            || this.options.date_to
            || start;
        const end = rawEnd >= start ? rawEnd : start;
        this.state.dateMenuOpen = false;
        return this.updateOptions({
            period: "custom",
            anchor_date: end,
            date_from: start,
            date_to: end,
        });
    }

    setTargetMove(targetMove) {
        return this.updateOptions({ target_move: targetMove });
    }

    toggleDebitCredit() {
        return this.updateOptions({ debit_credit: !this.options.debit_credit });
    }

    toggleComparison() {
        return this.updateOptions({ enable_filter: !this.options.enable_filter });
    }

    toggleComparisonMenu() {
        this.state.comparisonMenuOpen = !this.state.comparisonMenuOpen;
        this.state.dateMenuOpen = false;
        this.state.journalMenuOpen = false;
        this.state.openLineMenuId = null;
    }

    selectComparison(mode) {
        if (mode === "none") {
            this.state.comparisonMenuOpen = false;
            return this.updateOptions({
                comparison: "none",
                comparison_date_from: "",
                comparison_date_to: "",
            });
        }
        if (mode === "custom") {
            // keep the menu open so the date inputs stay visible
            this.state.pendingCmpFrom = this.options.comparison_date_from || "";
            this.state.pendingCmpTo = this.options.comparison_date_to || "";
            return this.updateOptions({ comparison: "custom" });
        }
        // previous_period / same_last_year: keep menu open for the count stepper
        const count = this.comparisonMode === mode ? this.comparisonCount : 1;
        return this.updateOptions({
            comparison: mode,
            comparison_count: count,
            comparison_date_from: "",
            comparison_date_to: "",
        });
    }

    setComparisonCount(value) {
        let count = parseInt(value, 10);
        if (!Number.isFinite(count) || count < 1) {
            count = 1;
        }
        count = Math.min(count, 36);
        return this.updateOptions({ comparison_count: count });
    }

    setPeriodOrder(value) {
        return this.updateOptions({ period_order: value === "ascending" ? "ascending" : "descending" });
    }

    setPendingCmpFrom(value) {
        this.state.pendingCmpFrom = value || "";
    }

    setPendingCmpTo(value) {
        this.state.pendingCmpTo = value || "";
    }

    setPendingCmpSpecific(value) {
        // Balance Sheet "Specific Date": one as-of date drives both ends.
        this.state.pendingCmpFrom = value || "";
        this.state.pendingCmpTo = value || "";
    }

    applyComparisonCustom() {
        this.state.comparisonMenuOpen = false;
        return this.updateOptions({
            comparison: "custom",
            comparison_date_from: this.state.pendingCmpFrom,
            comparison_date_to: this.state.pendingCmpTo,
        });
    }

    setSearchTerm(value) {
        this.state.searchTerm = value || "";
    }

    setReportSearchTerm(value) {
        this.state.searchTerm = value || "";
    }

    applyReportSearch(value = null) {
        const searchTerm = value === null ? this.state.searchTerm : value;
        this.state.searchTerm = searchTerm || "";
        if (this.isGeneralLedgerReport) {
            return this.updateOptions({
                account_search: this.state.searchTerm,
                account_ids: [],
            });
        }
    }

    toggleInitialBalance() {
        return this.updateOptions({ initial_balance: !this.options.initial_balance });
    }

    toggleReconciled() {
        return this.updateOptions({ reconciled: !this.options.reconciled });
    }

    toggleAmountCurrency() {
        return this.updateOptions({ amount_currency: !this.options.amount_currency });
    }

    setDisplayAccount(value) {
        return this.updateOptions({ display_account: value });
    }

    setPartnerType(value) {
        return this.updateOptions({ result_selection: value });
    }

    setSortBy(value) {
        if (this.reportKey === "journal_audit") {
            return this.updateOptions({ sort_selection: value });
        }
        return this.updateOptions({ sortby: value });
    }

    setPeriodLength(value) {
        const periodLength = Math.max(Number(value || 30), 1);
        return this.updateOptions({ period_length: periodLength });
    }

    toggleJournal(journalId) {
        const selected = new Set(this.options.journal_ids || []);
        if (selected.has(journalId)) {
            selected.delete(journalId);
        } else {
            selected.add(journalId);
        }
        return this.updateOptions({ journal_ids: [...selected] });
    }

    clearJournals() {
        return this.updateOptions({ journal_ids: [] });
    }

    async printPdf() {
        const action = await this.orm.call("account.interactive.report", "action_pdf", [this.reportKey, this.state.options]);
        if (action) {
            this.action.doAction(action);
        }
    }

    async exportXlsx() {
        await download({
            url: "/base_accounting_kit/interactive_report/xlsx",
            data: {
                report_key: this.reportKey,
                options: JSON.stringify(this.state.options),
            },
        });
    }

    formatAmount(value) {
        const amount = Number(value || 0);
        return new Intl.NumberFormat(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(amount);
    }

    formatDateLabel(value) {
        const date = parseDate(value);
        return new Intl.DateTimeFormat("en-US", {
            month: "2-digit",
            day: "2-digit",
            year: "numeric",
        }).format(date);
    }

    formatCell(line, column) {
        const value = (line.values || {})[column.key];
        if (column.type === "percent") {
            if (value === null || value === undefined || value === "") {
                return "—";
            }
            const pct = Number(value);
            const sign = pct > 0 ? "+" : "";
            return `${sign}${pct.toFixed(1)}%`;
        }
        if (column.type === "number") {
            const amount = this.formatAmount(value);
            return this.isAgedPartnerReport || this.isGeneralLedgerReport ? `${amount} ${this.report.currency_label}` : amount;
        }
        return value || "";
    }

    isUnfolded(line) {
        return (this.state.unfoldedLineIds || []).includes(line.id);
    }

    toggleLine(line) {
        if (!line.unfoldable) {
            return;
        }
        const unfolded = new Set(this.state.unfoldedLineIds || []);
        if (unfolded.has(line.id)) {
            unfolded.delete(line.id);
        } else {
            unfolded.add(line.id);
        }
        this.state.unfoldedLineIds = [...unfolded];
    }

    get hasFoldableLines() {
        return (this.report.lines || []).some((line) => line.unfoldable);
    }

    get allUnfolded() {
        const foldable = (this.report.lines || []).filter((line) => line.unfoldable);
        if (!foldable.length) {
            return false;
        }
        const unfolded = new Set(this.state.unfoldedLineIds || []);
        return foldable.every((line) => unfolded.has(line.id));
    }

    toggleFoldAll() {
        if (this.allUnfolded) {
            this.state.unfoldedLineIds = [];
        } else {
            this.state.unfoldedLineIds = (this.report.lines || [])
                .filter((line) => line.unfoldable)
                .map((line) => line.id);
        }
    }

    async activateLine(line) {
        if (line.unfoldable) {
            this.toggleLine(line);
            return;
        }
        if (line.action) {
            await this.action.doAction(line.action);
        }
    }

    hasLineActions(line) {
        const hasIds = (line.account_ids || []).length > 0;
        return Boolean((line.line_actions || []).length || line.account_id || hasIds || line.move_id);
    }

    lineActions(line) {
        if (line.line_actions && line.line_actions.length) {
            return line.line_actions;
        }
        if (line.move_id) {
            return [{ key: "journal_entry", label: "View Journal Entry" }];
        }
        if (line.account_id) {
            return [{ key: "general_ledger", label: "General Ledger" }];
        }
        return [];
    }

    toggleLineMenu(line, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        this.state.dateMenuOpen = false;
        this.state.journalMenuOpen = false;
        this.state.openLineMenuId = this.state.openLineMenuId === line.id ? null : line.id;
    }

    closeLineMenu() {
        this.state.openLineMenuId = null;
    }

    async runLineAction(line, actionKey, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        this.closeLineMenu();
        if (actionKey === "general_ledger" && (line.account_id || (line.account_ids || []).length)) {
            const isAggregate = !line.account_id && (line.account_ids || []).length > 0;
            const drillAccountIds = isAggregate ? [...line.account_ids] : [line.account_id];
            const accountLabel = isAggregate
                ? (line.name || "").trim()
                : (line.account_code || String(line.name || "").split(" ")[0] || "");
            await this.action.doAction({
                type: "ir.actions.client",
                tag: "base_accounting_kit.interactive_account_report",
                name: "General Ledger",
                context: {
                    report_key: "general_ledger",
                    default_options: {
                        ...this.state.options,
                        account_ids: drillAccountIds,
                        account_search: accountLabel,
                        display_account: "all",
                    },
                    drill_back: {
                        report_key: this.reportKey,
                        options: { ...this.state.options },
                        label: this.report.title || this.reportKey,
                    },
                },
            });
        } else if (actionKey === "journal_entry" && line.move_id) {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Journal Entry",
                res_model: "account.move",
                res_id: line.move_id,
                view_mode: "form",
                views: [[false, "form"]],
                target: "current",
            });
        } else if (line.action) {
            await this.action.doAction(line.action);
        }
    }

    lineClass(line) {
        return [
            "o_account_report_line",
            `level_${line.level || 1}`,
            line.is_total ? "is_total" : "",
            line.is_grand_total ? "is_grand_total" : "",
            line.unfoldable ? "is_foldable" : "",
            (line.action || this.hasLineActions(line)) ? "is_clickable" : "",
            this.isUnfolded(line) ? "is_unfolded" : "",
            line.type ? `line_type_${line.type}` : "",
        ].join(" ");
    }

    cellClass(column, line) {
        const raw = (line.values || {})[column.key];
        const numeric = column.type === "number" || column.type === "percent";
        const amount = Number(raw || 0);
        const negative = numeric && raw !== null && raw !== "" && amount < 0;
        const zero = column.type === "number" && Math.abs(amount) < 0.005;
        return `${numeric ? "o_account_report_number" : ""} ${column.type === "percent" ? "o_account_pct_cell" : ""} ${negative ? "is_negative" : ""} ${zero ? "is_zero" : ""}`;
    }

    nameCellStyle(line) {
        const level = Math.max(line.level || 1, 1);
        return `padding-left: ${24 + ((level - 1) * 12)}px`;
    }
}

registry.category("actions").add("base_accounting_kit.interactive_account_report", InteractiveAccountReport);
