/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { ListRenderer } from "@web/views/list/list_renderer";
import { onMounted, onPatched } from "@odoo/owl";

const LEGACY_ORDER_KEY_PREFIX = "goldverse_laundry_order_list_column_order";
const ORDER_KEY_PREFIX = "goldverse_laundry_order_list_column_order_v2";
const PINNED_FIELD_ORDER = ["name", "partner_id", "goldverse_flow_status", "priority", "payment_status"];
const COLUMN_WIDTH_LIMITS = {
    "__selector__": { min: 42, max: 42 },
    "__actions__": { min: 150, max: 360 },
    name: { min: 130, max: 280 },
    partner_id: { min: 110, max: 340 },
    goldverse_flow_status: { min: 130, max: 280 },
    priority: { min: 90, max: 150 },
    payment_status: { min: 105, max: 170 },
    invoice_status: { min: 105, max: 170 },
    date_order: { min: 115, max: 185 },
    expected_delivery_datetime: { min: 150, max: 230 },
    actual_delivery_datetime: { min: 170, max: 260 },
};
const AMOUNT_FIELD_PATTERN = /(amount|price|qty|quantity|tax|balance|charge|discount|debit|credit|total|net|gross)/i;
const TOTALABLE_FIELD_TYPES = new Set(["float", "integer", "monetary"]);
const TOTALABLE_MODEL_PREFIXES = ["aimaze.laundry.", "goldverse."];
const TOTALABLE_MODELS = new Set(["account.move", "account.move.line", "account.payment"]);
let measureContext = null;

function isGoldverseLaundryList(renderer) {
    return (
        renderer.props?.list?.resModel === "aimaze.laundry.order" &&
        renderer.props?.archInfo?.className?.includes("goldverse-laundry-order-list")
    );
}

function isGoldverseTotalsList(renderer) {
    const model = renderer.props?.list?.resModel || "";
    return (
        isGoldverseLaundryList(renderer) ||
        TOTALABLE_MODELS.has(model) ||
        TOTALABLE_MODEL_PREFIXES.some((prefix) => model.startsWith(prefix))
    );
}

function columnStorageKey(renderer) {
    const db = session.db || "db";
    const uid = session.uid || "uid";
    const model = renderer?.props?.list?.resModel || "aimaze.laundry.order";
    return `${ORDER_KEY_PREFIX}:${db}:${uid}:${model}`;
}

function removeLegacyColumnOrders() {
    for (const key of Object.keys(localStorage)) {
        if (key === LEGACY_ORDER_KEY_PREFIX || key.startsWith(`${LEGACY_ORDER_KEY_PREFIX}:`)) {
            localStorage.removeItem(key);
        }
    }
}

function sanitizeOrder(order, columns) {
    const allowed = columns?.length
        ? new Set(
              columns
                  .filter((column) => column.type === "field" && column.name)
                  .map((column) => column.name)
          )
        : null;
    const clean = [];
    for (const name of Array.isArray(order) ? order : []) {
        if ((!allowed || allowed.has(name)) && name && !clean.includes(name)) {
            clean.push(name);
        }
    }
    return clean;
}

function isPinnedField(name) {
    return PINNED_FIELD_ORDER.includes(name);
}

function readColumnOrder(renderer, columns) {
    try {
        const value = JSON.parse(localStorage.getItem(columnStorageKey(renderer)) || "[]");
        return sanitizeOrder(value, columns);
    } catch {
        localStorage.removeItem(columnStorageKey(renderer));
        return [];
    }
}

function writeColumnOrder(renderer, order) {
    const columns = renderer?.columns || renderer?.getActiveColumns?.() || [];
    localStorage.setItem(columnStorageKey(renderer), JSON.stringify(sanitizeOrder(order, columns)));
}

function applySavedOrder(renderer, columns) {
    const order = readColumnOrder(renderer, columns);
    const buttonGroups = [];
    const otherFixed = [];
    const movable = [];
    for (const column of columns) {
        if (column.type === "button_group") {
            buttonGroups.push(column);
        } else if (column.type === "field" && column.name) {
            movable.push(column);
        } else {
            otherFixed.push(column);
        }
    }
    const byName = new Map(movable.map((column) => [column.name, column]));
    const pinnedFields = PINNED_FIELD_ORDER.map((name) => byName.get(name)).filter(Boolean);
    const pinnedNames = new Set(pinnedFields.map((column) => column.name));
    const remainder = movable.filter((column) => !pinnedNames.has(column.name));
    const remainderOrder = order.filter((name) => !pinnedNames.has(name));
    const orderedRemainder = remainderOrder.length ? [
        ...remainderOrder.map((name) => byName.get(name)).filter(Boolean),
        ...remainder.filter((column) => !remainderOrder.includes(column.name)),
    ] : remainder;
    return [...buttonGroups, ...pinnedFields, ...orderedRemainder, ...otherFixed];
}

function moveNameBefore(order, source, target) {
    const clean = order.filter((name) => name && name !== source);
    const index = clean.indexOf(target);
    clean.splice(index >= 0 ? index : clean.length, 0, source);
    return clean;
}

function orderNamesFromHeader(row) {
    return Array.from(row.querySelectorAll("th[data-name]")).map((th) => th.dataset.name);
}

function reorderNamedCells(row, order, selector) {
    const namedCells = Array.from(row.querySelectorAll(selector));
    if (!namedCells.length) {
        return;
    }
    const byName = new Map(namedCells.map((cell) => [cell.dataset.name || cell.getAttribute("name"), cell]));
    const anchor = namedCells[namedCells.length - 1].nextSibling;
    for (const name of order) {
        const cell = byName.get(name);
        if (cell) {
            row.insertBefore(cell, anchor);
        }
    }
}

function applyOrderToTable(table, order) {
    const headerRow = table.querySelector("thead tr");
    if (headerRow) {
        reorderNamedCells(headerRow, order, "th[data-name]");
    }
    for (const row of table.querySelectorAll("tbody tr, tfoot tr")) {
        reorderNamedCells(row, order, "td[name]");
    }
}

function tableForHeader(header) {
    return header.closest(".goldverse-laundry-order-list table.o_list_table");
}

function rendererForTable(table) {
    return table.closest(".o_list_renderer")?.__owl__?.component || null;
}

function clampWidth(value, key) {
    const limits = COLUMN_WIDTH_LIMITS[key] || { min: 72, max: 360 };
    return Math.min(Math.max(value, limits.min), limits.max);
}

function columnKey(header) {
    if (header.classList.contains("o_list_record_selector")) {
        return "__selector__";
    }
    if (header.classList.contains("o_list_button")) {
        return "__actions__";
    }
    return header.dataset.name || "";
}

function canvasContext() {
    if (!measureContext) {
        measureContext = document.createElement("canvas").getContext("2d");
    }
    return measureContext;
}

function fontFor(cell) {
    const style = getComputedStyle(cell);
    return `${style.fontStyle} ${style.fontVariant} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
}

function measureText(text, cell) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    if (!clean) {
        return 0;
    }
    const context = canvasContext();
    context.font = fontFor(cell);
    return Math.ceil(context.measureText(clean).width);
}

function cellText(cell) {
    const title = cell.querySelector(".o_column_title, .o_list_number_th");
    return (title || cell).innerText || (title || cell).textContent || "";
}

function textWidth(cell, key) {
    if (key === "__selector__") {
        return 24;
    }
    if (key === "__actions__") {
        const buttons = [...cell.querySelectorAll("button, .btn")].filter((button) => button.offsetParent !== null);
        if (buttons.length) {
            return buttons.reduce((total, button) => total + measureText(button.innerText || button.textContent, button) + 22, 0)
                + Math.max(buttons.length - 1, 0) * 5;
        }
    }
    return measureText(cellText(cell), cell);
}

function setCellWidth(cell, width) {
    cell.style.setProperty("width", `${width}px`, "important");
    cell.style.setProperty("min-width", `${width}px`, "important");
    cell.style.setProperty("max-width", `${width}px`, "important");
}

function alignColumn(cells, key) {
    const align = AMOUNT_FIELD_PATTERN.test(key) ? "right" : "center";
    for (const cell of cells) {
        cell.classList.toggle("goldverse-list-amount-column", align === "right");
        cell.classList.toggle("goldverse-list-text-column", align === "center");
        cell.style.textAlign = align;
    }
}

function totalableFields(renderer) {
    const list = renderer.props?.list;
    const fields = list?.fields || {};
    const columns = renderer.columns || renderer.getActiveColumns?.() || [];
    const names = [];
    for (const column of columns) {
        if (column.type !== "field" || !column.name || names.includes(column.name)) {
            continue;
        }
        const field = fields[column.name] || {};
        if (TOTALABLE_FIELD_TYPES.has(field.type) && AMOUNT_FIELD_PATTERN.test(column.name)) {
            names.push(column.name);
        }
    }
    return names;
}

function totalableHeaders(table, fields) {
    const fieldSet = new Set(fields);
    return Array.from(table.querySelectorAll("thead tr th[data-name]")).filter((header) =>
        fieldSet.has(header.dataset.name)
    );
}

function numericValue(value) {
    if (typeof value === "number") {
        return Number.isFinite(value) ? value : 0;
    }
    if (Array.isArray(value)) {
        return 0;
    }
    const parsed = Number(String(value || "").replace(/[^\d.-]/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
}

function pageTotals(renderer, fields) {
    const totals = Object.fromEntries(fields.map((field) => [field, 0]));
    for (const record of renderer.props?.list?.records || []) {
        for (const field of fields) {
            totals[field] += numericValue(record.data?.[field]);
        }
    }
    return totals;
}

function formatTotalValue(renderer, fieldName, value) {
    const field = renderer.props?.list?.fields?.[fieldName] || {};
    const isQty = /qty|quantity/i.test(fieldName);
    const formatter = new Intl.NumberFormat(undefined, {
        minimumFractionDigits: isQty ? 2 : 2,
        maximumFractionDigits: isQty ? 2 : 2,
    });
    const formatted = formatter.format(numericValue(value));
    return field.type === "monetary" || (/amount|balance|price|tax|charge|discount|debit|credit|net|gross/i.test(fieldName) && !isQty)
        ? `${formatted} Rs.`
        : formatted;
}

function totalsCacheKey(renderer, fields) {
    const list = renderer.props?.list;
    let domain = "[]";
    try {
        domain = JSON.stringify(list?.domain || []);
    } catch {
        domain = String(list?.domain || "");
    }
    return JSON.stringify({
        model: list?.resModel || "",
        count: list?.count || 0,
        domain,
        fields,
    });
}

function removeTotalsFooter(table) {
    table.querySelector("tfoot.goldverse-list-totals-footer")?.remove();
}

function buildTotalsRow(renderer, table, label, totals, className) {
    const row = document.createElement("tr");
    row.className = `goldverse-list-total-row ${className}`;
    const headers = Array.from(table.querySelectorAll("thead tr:first-child > th"));
    let labelPlaced = false;
    for (const header of headers) {
        const key = columnKey(header);
        const fieldName = header.dataset.name || "";
        const cell = document.createElement("td");
        if (fieldName) {
            cell.setAttribute("name", fieldName);
        }
        if (header.classList.contains("o_list_button")) {
            cell.classList.add("o_list_button");
        }
        if (!labelPlaced && key !== "__selector__" && !header.classList.contains("o_list_button")) {
            cell.textContent = label;
            cell.classList.add("goldverse-list-total-label");
            labelPlaced = true;
        } else if (fieldName && Object.prototype.hasOwnProperty.call(totals || {}, fieldName)) {
            cell.textContent = formatTotalValue(renderer, fieldName, totals[fieldName]);
            cell.classList.add("goldverse-list-total-value");
        }
        row.appendChild(cell);
    }
    if (!labelPlaced && row.children.length) {
        row.children[0].textContent = label;
        row.children[0].classList.add("goldverse-list-total-label");
    }
    return row;
}

function renderTotalsFooter(renderer, table, page, grand) {
    removeTotalsFooter(table);
    const fields = totalableFields(renderer);
    if (!fields.length || !totalableHeaders(table, fields).length) {
        return;
    }
    const footer = document.createElement("tfoot");
    footer.className = "goldverse-list-totals-footer";
    footer.appendChild(buildTotalsRow(renderer, table, "Page Total", page, "goldverse-page-total-row"));
    footer.appendChild(buildTotalsRow(renderer, table, "Grand Total", grand || page, "goldverse-grand-total-row"));
    table.appendChild(footer);
}

function autoFitTableColumns(table) {
    const headerRow = table.querySelector("thead tr");
    if (!headerRow) {
        return;
    }
    table.style.setProperty("table-layout", "fixed", "important");
    const headers = Array.from(headerRow.children);
    const colgroup = table.querySelector("colgroup");
    let totalWidth = 0;
    headers.forEach((header, index) => {
        const key = columnKey(header);
        const cells = [
            header,
            ...Array.from(table.querySelectorAll("tbody tr, tfoot tr")).map((row) => row.children[index]).filter(Boolean),
        ];
        const padding = key === "__actions__" ? 12 : 22;
        const measured = Math.max(...cells.map((cell) => textWidth(cell, key)), 0) + padding;
        const width = clampWidth(measured, key);
        totalWidth += width;
        alignColumn(cells, key);
        cells.forEach((cell) => setCellWidth(cell, width));
        const col = colgroup?.children[index];
        if (col) {
            setCellWidth(col, width);
        }
    });
    table.style.setProperty("width", `${totalWidth}px`, "important");
    table.style.setProperty("min-width", `${totalWidth}px`, "important");
    table.style.setProperty("max-width", "none", "important");
}

let autoFitRequest = null;

function scheduleAutoFit() {
    if (autoFitRequest) {
        return;
    }
    autoFitRequest = requestAnimationFrame(() => {
        autoFitRequest = null;
        document
            .querySelectorAll(".goldverse-laundry-order-list table.o_list_table")
            .forEach(autoFitTableColumns);
    });
}

if (!window.__goldverseLaundryColumnDragEnabled) {
    window.__goldverseLaundryColumnDragEnabled = true;
    removeLegacyColumnOrders();

    document.addEventListener("dragstart", (ev) => {
        const header = ev.target.closest(".goldverse-laundry-order-list table.o_list_table th[data-name]");
        if (!header || ev.target.closest(".o_resize") || isPinnedField(header.dataset.name)) {
            return;
        }
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", header.dataset.name);
        header.classList.add("goldverse-column-dragging");
    });

    document.addEventListener("dragend", (ev) => {
        ev.target.closest("th")?.classList.remove("goldverse-column-dragging");
        document
            .querySelectorAll(".goldverse-column-drop-target")
            .forEach((node) => node.classList.remove("goldverse-column-drop-target"));
    });

    document.addEventListener("dragover", (ev) => {
        const header = ev.target.closest(".goldverse-laundry-order-list table.o_list_table th[data-name]");
        if (!header || isPinnedField(header.dataset.name)) {
            return;
        }
        ev.preventDefault();
        header.classList.add("goldverse-column-drop-target");
    });

    document.addEventListener("dragleave", (ev) => {
        ev.target
            .closest(".goldverse-laundry-order-list table.o_list_table th[data-name]")
            ?.classList.remove("goldverse-column-drop-target");
    });

    document.addEventListener("drop", (ev) => {
        const header = ev.target.closest(".goldverse-laundry-order-list table.o_list_table th[data-name]");
        const table = header && tableForHeader(header);
        const source = ev.dataTransfer.getData("text/plain");
        const target = header?.dataset.name;
        if (!table || !source || !target || source === target || isPinnedField(source) || isPinnedField(target)) {
            return;
        }
        ev.preventDefault();
        const nextOrder = moveNameBefore(orderNamesFromHeader(table.querySelector("thead tr")), source, target);
        writeColumnOrder(rendererForTable(table), nextOrder);
        applyOrderToTable(table, nextOrder);
        autoFitTableColumns(table);
        header.classList.remove("goldverse-column-drop-target");
    });

    const markHeadersDraggable = () => {
        document
            .querySelectorAll(".goldverse-laundry-order-list table.o_list_table th[data-name]")
            .forEach((header) => {
                const pinned = isPinnedField(header.dataset.name);
                header.draggable = !pinned;
                header.title = pinned
                    ? "Pinned column. Use the edge handle to resize."
                    : header.title || "Drag to move column. Use the edge handle to resize.";
            });
        scheduleAutoFit();
    };

    const observer = new MutationObserver(markHeadersDraggable);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    markHeadersDraggable();
}

if (ListRenderer.prototype.__goldverseLaundryListColumnPatchVersion !== 4) {
    patch(ListRenderer.prototype, {
        __goldverseLaundryListColumnPatchVersion: 4,

        setup() {
            super.setup(...arguments);
            onMounted(() => this.goldverseUpdateListTotals());
            onPatched(() => this.goldverseUpdateListTotals());
        },

        getActiveColumns() {
            const columns = super.getActiveColumns(...arguments);
            return isGoldverseLaundryList(this) ? applySavedOrder(this, columns) : columns;
        },

        async goldverseUpdateListTotals() {
            const table = this.tableRef?.el || document.querySelector(".o_list_renderer table.o_list_table");
            if (!table || table.closest(".o_field_x2many, .o_field_one2many") || !isGoldverseTotalsList(this)) {
                if (table) {
                    removeTotalsFooter(table);
                }
                return;
            }

            const fields = totalableFields(this);
            if (!fields.length || !totalableHeaders(table, fields).length) {
                removeTotalsFooter(table);
                return;
            }

            const page = pageTotals(this, fields);
            const key = totalsCacheKey(this, fields);
            const cachedGrand = this.__goldverseTotalsKey === key ? this.__goldverseGrandTotals : null;
            renderTotalsFooter(this, table, page, cachedGrand || page);
            autoFitTableColumns(table);

            if (cachedGrand) {
                return;
            }

            const sequence = (this.__goldverseTotalsSequence || 0) + 1;
            this.__goldverseTotalsSequence = sequence;
            try {
                const grand = await this.orm.call(
                    this.props.list.resModel,
                    "goldverse_list_totals",
                    [this.props.list.domain || [], fields],
                    { context: this.props.list.context || {} }
                );
                if (this.__goldverseTotalsSequence !== sequence) {
                    return;
                }
                this.__goldverseTotalsKey = key;
                this.__goldverseGrandTotals = grand;
                renderTotalsFooter(this, table, page, grand);
                autoFitTableColumns(table);
            } catch {
                renderTotalsFooter(this, table, page, page);
            }
        },
    });
}
