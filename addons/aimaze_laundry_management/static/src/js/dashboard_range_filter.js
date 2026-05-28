/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

const RANGE_WRAPPER = ".aimaze-custom-range-wrapper";
const RANGE_OPEN = "aimaze-range-open";
const DATE_PICKER = ".o_datetime_picker, .bootstrap-datetimepicker-widget, .datepicker, .ui-datepicker";
const STORAGE_PREFIX = "aimaze_dashboard_custom_range_";
const RANGE_STYLE_ID = "aimaze-dashboard-range-style";
const autoSaveTimers = new WeakMap();
const RANGE_STYLE = `
.aimaze-report-filter-strip {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 10px;
}
.aimaze-dashboard-branch-filter,
.aimaze-dashboard-branch-filter .o-autocomplete,
.aimaze-dashboard-branch-filter .o-autocomplete--input,
.aimaze-dashboard-branch-filter .o_input,
.aimaze-dashboard-branch-filter input {
    box-sizing: border-box !important;
    width: 200px !important;
    max-width: 200px !important;
}
@media (max-width: 420px) {
    .aimaze-dashboard-branch-filter,
    .aimaze-dashboard-branch-filter .o-autocomplete,
    .aimaze-dashboard-branch-filter .o-autocomplete--input,
    .aimaze-dashboard-branch-filter .o_input,
    .aimaze-dashboard-branch-filter input {
        box-sizing: border-box !important;
        width: 200px !important;
        max-width: calc(100vw - 160px) !important;
        min-width: 150px !important;
    }
}
.aimaze-custom-range-wrapper {
    position: relative !important;
    display: inline-flex !important;
    align-items: center !important;
    box-sizing: border-box !important;
    width: 200px !important;
    max-width: 200px !important;
    min-height: 42px;
}
.aimaze-date-range-pill {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-sizing: border-box !important;
    gap: 6px;
    width: 200px !important;
    min-width: 200px;
    max-width: 200px !important;
    height: 42px;
    padding: 0 10px !important;
    border: 1px solid #7563a7;
    border-radius: 999px;
    background: #fff;
    color: #1a2d40;
    box-shadow: 0 2px 8px rgba(15, 34, 51, 0.05);
    font-size: 12px;
    font-weight: 750;
    line-height: 42px;
    cursor: pointer;
    text-decoration: none !important;
}
.aimaze-date-range-label,
.aimaze-date-range-label .o_field_widget,
.aimaze-date-range-label span {
    display: inline-flex !important;
    align-items: center !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1 !important;
    min-width: 0 !important;
    max-width: 146px !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap;
}
.aimaze-date-popover {
    position: absolute !important;
    top: calc(100% + 8px) !important;
    right: 0 !important;
    z-index: 1060;
    display: none !important;
    width: 250px !important;
    max-width: calc(100vw - 48px) !important;
    overflow: hidden;
    border: 1px solid #d8d2ea;
    border-radius: 12px;
    background: #fff;
    box-shadow: 0 16px 34px rgba(15, 34, 51, 0.14);
}
.aimaze-custom-range-wrapper.aimaze-range-open .aimaze-date-popover {
    display: block !important;
}
.aimaze-date-popover-body {
    display: grid !important;
    gap: 7px;
    padding: 12px 16px 14px !important;
}
.aimaze-date-popover-body label,
.aimaze-date-popover-body .o_form_label {
    margin: 0 !important;
    color: #7a7383;
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
}
.aimaze-date-popover-body .o_field_widget {
    width: 200px !important;
    max-width: 200px !important;
    margin: 0 !important;
}
.aimaze-date-popover-body input,
.aimaze-date-popover-body .o_input {
    box-sizing: border-box !important;
    width: 200px !important;
    min-width: 200px !important;
    max-width: 200px !important;
    min-height: 42px !important;
    height: 42px !important;
    border: 1px solid #ddd8ec !important;
    border-radius: 8px !important;
    background: #f8f7fc !important;
    color: #1a2d40;
    font-size: 13px !important;
    box-shadow: none !important;
}
.aimaze-date-popover-footer {
    display: flex !important;
    justify-content: center !important;
    gap: 8px;
    padding: 10px 12px !important;
    border-top: 1px solid #eee9f8;
    background: #f6f1fb;
}
.aimaze-date-popover-footer .btn {
    min-width: 82px;
    min-height: 34px;
    padding: 7px 12px !important;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 750;
}
.aimaze-date-popover-footer .aimaze-range-apply {
    border-color: #7563a7;
    background: #7563a7;
    color: #fff;
    min-width: 112px;
}
@media (max-width: 992px) {
    .aimaze-report-filter-strip {
        justify-content: flex-start;
    }
    .aimaze-date-popover {
        left: 0 !important;
        right: auto !important;
    }
}
@media (max-width: 640px) {
    .aimaze-date-range-pill,
    .aimaze-custom-range-wrapper {
        width: 200px !important;
        max-width: 200px !important;
    }
    .aimaze-date-popover {
        width: 250px !important;
        max-width: calc(100vw - 72px) !important;
    }
}
`;
const MONTHS = {
    jan: 1,
    feb: 2,
    mar: 3,
    apr: 4,
    may: 5,
    jun: 6,
    jul: 7,
    aug: 8,
    sep: 9,
    oct: 10,
    nov: 11,
    dec: 12,
};

function pad(value) {
    return String(value).padStart(2, "0");
}

function ensureRangeStyle() {
    if (document.getElementById(RANGE_STYLE_ID)) {
        return;
    }
    const style = document.createElement("style");
    style.id = RANGE_STYLE_ID;
    style.textContent = RANGE_STYLE;
    document.head.appendChild(style);
}

function toIsoDate(value) {
    if (!value) {
        return "";
    }
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

function parseDisplayDate(value, fallbackYear) {
    const match = String(value || "")
        .trim()
        .match(/^([A-Za-z]{3,})\s+(\d{1,2})(?:,\s*(\d{4}))?$/);
    if (!match) {
        return null;
    }
    const month = MONTHS[match[1].slice(0, 3).toLowerCase()];
    const day = Number(match[2]);
    const year = Number(match[3] || fallbackYear);
    if (!month || !day || !year) {
        return null;
    }
    return new Date(year, month - 1, day);
}

function parseRangeLabel(label) {
    const [fromLabel, toLabel] = String(label || "").split(" - ");
    const toDate = parseDisplayDate(toLabel, new Date().getFullYear());
    const fromDate = parseDisplayDate(fromLabel, toDate ? toDate.getFullYear() : new Date().getFullYear());
    return {
        dateFrom: toIsoDate(fromDate),
        dateTo: toIsoDate(toDate || fromDate),
    };
}

function formatDisplayDate(isoDate, includeYear = false) {
    if (!isoDate) {
        return "";
    }
    const date = new Date(`${isoDate}T00:00:00`);
    const month = date.toLocaleString("en-US", { month: "short" });
    const day = date.getDate();
    return includeYear ? `${month} ${day}, ${date.getFullYear()}` : `${month} ${day}`;
}

function formatRangeLabel(dateFrom, dateTo) {
    if (!dateFrom && !dateTo) {
        return "";
    }
    const fromValue = dateFrom || dateTo;
    const toValue = dateTo || dateFrom;
    const fromYear = Number(fromValue.slice(0, 4));
    const toYear = Number(toValue.slice(0, 4));
    return fromYear === toYear
        ? `${formatDisplayDate(fromValue)} - ${formatDisplayDate(toValue, true)}`
        : `${formatDisplayDate(fromValue, true)} - ${formatDisplayDate(toValue, true)}`;
}

function visibleRangeWrappers() {
    return [...document.querySelectorAll(RANGE_WRAPPER)].filter(
        (wrapper) => wrapper.offsetParent && !wrapper.closest(".o_invisible_modifier")
    );
}

function dashboardRecordId() {
    const match = window.location.pathname.match(/\/action-\d+\/(\d+)/);
    return match ? Number(match[1]) : 0;
}

function storageKey(recordId) {
    return `${STORAGE_PREFIX}${recordId}`;
}

function hardReload() {
    window.location.reload();
}

function rangeValues(wrapper) {
    const fromInput = wrapper.querySelector(".aimaze-date-from-input");
    const toInput = wrapper.querySelector(".aimaze-date-to-input");
    let dateFrom = fromInput?.value || "";
    let dateTo = toInput?.value || "";
    if (dateFrom && dateTo && dateTo < dateFrom) {
        dateTo = dateFrom;
        if (toInput) {
            toInput.value = dateTo;
        }
    }
    return { dateFrom, dateTo };
}

function updateVisibleLabel(wrapper) {
    const label = wrapper.querySelector(".aimaze-date-range-label");
    const values = rangeValues(wrapper);
    const text = formatRangeLabel(values.dateFrom, values.dateTo);
    if (label && text) {
        label.textContent = text;
    }
}

function clearRangeAutoSave(wrapper) {
    const timer = autoSaveTimers.get(wrapper);
    if (timer) {
        window.clearTimeout(timer);
        autoSaveTimers.delete(wrapper);
    }
}

function scheduleRangeAutoSave(wrapper) {
    if (!wrapper) {
        return;
    }
    const values = rangeValues(wrapper);
    if (!values.dateFrom || !values.dateTo) {
        return;
    }
    clearRangeAutoSave(wrapper);
    autoSaveTimers.set(
        wrapper,
        window.setTimeout(() => {
            if (wrapper.dataset.aimazeRangeDirty === "1") {
                saveNativeRange(wrapper);
            }
        }, 1200)
    );
}

function initializeNativeInputs(wrapper) {
    const parsed = parseRangeLabel(wrapper.querySelector(".aimaze-date-range-label")?.textContent || "");
    const today = toIsoDate(new Date());
    const fromInput = wrapper.querySelector(".aimaze-date-from-input");
    const toInput = wrapper.querySelector(".aimaze-date-to-input");
    if (fromInput && !fromInput.value) {
        fromInput.value = parsed.dateFrom || today;
    }
    if (toInput && !toInput.value) {
        toInput.value = parsed.dateTo || parsed.dateFrom || today;
    }
}

async function saveNativeRange(wrapper) {
    const values = rangeValues(wrapper);
    const recordId = dashboardRecordId();
    if (!recordId || !values.dateFrom || !values.dateTo) {
        wrapper.classList.remove(RANGE_OPEN);
        return;
    }
    clearRangeAutoSave(wrapper);
    wrapper.classList.remove(RANGE_OPEN);
    window.localStorage.setItem(storageKey(recordId), JSON.stringify(values));
    hardReload();
}

async function applyPendingRange() {
    const recordId = dashboardRecordId();
    if (!recordId) {
        return;
    }
    const key = storageKey(recordId);
    const rawValue = window.localStorage.getItem(key);
    if (!rawValue) {
        return;
    }
    let values;
    try {
        values = JSON.parse(rawValue);
    } catch {
        window.localStorage.removeItem(key);
        return;
    }
    if (!values.dateFrom || !values.dateTo) {
        window.localStorage.removeItem(key);
        return;
    }
    if (values.dateTo < values.dateFrom) {
        values.dateTo = values.dateFrom;
    }
    try {
        await rpc("/web/dataset/call_kw/aimaze.laundry.executive.dashboard/write", {
            model: "aimaze.laundry.executive.dashboard",
            method: "write",
            args: [
                [recordId],
                {
                    period_filter: "custom",
                    date_from: values.dateFrom,
                    date_to: values.dateTo,
                },
            ],
            kwargs: {},
        });
        window.localStorage.removeItem(key);
        hardReload();
    } catch {
        window.localStorage.removeItem(key);
    }
}

function closeRange(wrapper, applyDirty = false) {
    if (!wrapper) {
        return;
    }
    if (applyDirty) {
        saveNativeRange(wrapper);
        return;
    }
    wrapper.classList.remove(RANGE_OPEN);
}

function closeAllRanges(applyDirty = false) {
    document.querySelectorAll(`${RANGE_WRAPPER}.${RANGE_OPEN}`).forEach((wrapper) => closeRange(wrapper, applyDirty));
}

function openRange(wrapper) {
    if (!wrapper) {
        return;
    }
    closeAllRanges(false);
    initializeNativeInputs(wrapper);
    wrapper.classList.add(RANGE_OPEN);
}

function openVisibleCustomRange() {
    const wrapper = visibleRangeWrappers()[0];
    if (wrapper) {
        openRange(wrapper);
    }
}

document.addEventListener(
    "pointerdown",
    (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        if (
            target.closest(RANGE_WRAPPER) ||
            target.closest(DATE_PICKER) ||
            target.closest(".aimaze-report-filter-strip .o_selection_badge")
        ) {
            return;
        }
        closeAllRanges(true);
    },
    true
);

document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
        return;
    }

    if (target.closest(DATE_PICKER)) {
        return;
    }

    const badge = target.closest(".aimaze-report-filter-strip .o_selection_badge");
    if (badge) {
        if (badge.textContent.trim() === "Custom") {
            window.setTimeout(openVisibleCustomRange, 250);
        } else {
            closeAllRanges(false);
        }
        return;
    }

    const pill = target.closest(".aimaze-date-range-pill");
    if (pill) {
        event.preventDefault();
        const wrapper = pill.closest(RANGE_WRAPPER);
        if (wrapper.classList.contains(RANGE_OPEN)) {
            closeRange(wrapper, false);
        } else {
            openRange(wrapper);
        }
        return;
    }

    const cancel = target.closest(".aimaze-range-cancel");
    if (cancel) {
        event.preventDefault();
        const wrapper = cancel.closest(RANGE_WRAPPER);
        wrapper.dataset.aimazeRangeDirty = "0";
        clearRangeAutoSave(wrapper);
        closeRange(wrapper, false);
        return;
    }

    const apply = target.closest(".aimaze-range-apply");
    if (apply) {
        event.preventDefault();
        event.stopPropagation();
        const wrapper = apply.closest(RANGE_WRAPPER);
        if (wrapper) {
            wrapper.dataset.aimazeRangeDirty = "0";
            saveNativeRange(wrapper);
        }
        return;
    }

    if (!target.closest(RANGE_WRAPPER)) {
        closeAllRanges(true);
    }
});

document.addEventListener("input", (event) => {
    const target = event.target;
    if (target instanceof Element && target.closest(".aimaze-date-popover")) {
        const wrapper = target.closest(RANGE_WRAPPER);
        wrapper.dataset.aimazeRangeDirty = "1";
        updateVisibleLabel(wrapper);
        scheduleRangeAutoSave(wrapper);
    }
});

document.addEventListener("change", (event) => {
    const target = event.target;
    if (target instanceof Element && target.closest(".aimaze-date-popover")) {
        const wrapper = target.closest(RANGE_WRAPPER);
        wrapper.dataset.aimazeRangeDirty = "1";
        updateVisibleLabel(wrapper);
        scheduleRangeAutoSave(wrapper);
    }
});

window.setTimeout(applyPendingRange, 1200);
ensureRangeStyle();
