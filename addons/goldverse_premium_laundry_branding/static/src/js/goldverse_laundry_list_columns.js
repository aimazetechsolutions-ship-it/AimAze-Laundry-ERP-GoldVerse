/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { ListRenderer } from "@web/views/list/list_renderer";

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
const AMOUNT_FIELD_PATTERN = /(amount|price|qty|quantity|tax|balance|charge|discount|debit|credit|received|paid|total|net|gross)/i;

function isGoldverseLaundryList(renderer) {
    return (
        renderer.props?.list?.resModel === "aimaze.laundry.order" &&
        renderer.props?.archInfo?.className?.includes("goldverse-laundry-order-list")
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

function textWidth(cell) {
    const clone = cell.cloneNode(true);
    clone.style.position = "absolute";
    clone.style.left = "-10000px";
    clone.style.top = "-10000px";
    clone.style.width = "auto";
    clone.style.minWidth = "0";
    clone.style.maxWidth = "none";
    clone.style.whiteSpace = "nowrap";
    clone.style.visibility = "hidden";
    clone.style.pointerEvents = "none";
    document.body.appendChild(clone);
    const width = Math.ceil(clone.scrollWidth || clone.getBoundingClientRect().width || 0);
    clone.remove();
    return width;
}

function setCellWidth(cell, width) {
    cell.style.width = `${width}px`;
    cell.style.minWidth = `${width}px`;
    cell.style.maxWidth = `${width}px`;
}

function alignColumn(cells, key) {
    const align = AMOUNT_FIELD_PATTERN.test(key) ? "right" : "center";
    for (const cell of cells) {
        cell.classList.toggle("goldverse-list-amount-column", align === "right");
        cell.classList.toggle("goldverse-list-text-column", align === "center");
        cell.style.textAlign = align;
    }
}

function autoFitTableColumns(table) {
    const headerRow = table.querySelector("thead tr");
    if (!headerRow) {
        return;
    }
    table.style.tableLayout = "fixed";
    const headers = Array.from(headerRow.children);
    const colgroup = table.querySelector("colgroup");
    let totalWidth = 0;
    headers.forEach((header, index) => {
        const key = columnKey(header);
        const cells = [
            header,
            ...Array.from(table.querySelectorAll("tbody tr")).map((row) => row.children[index]).filter(Boolean),
        ];
        const padding = key === "__actions__" ? 12 : 22;
        const measured = Math.max(...cells.map(textWidth), 0) + padding;
        const width = clampWidth(measured, key);
        totalWidth += width;
        alignColumn(cells, key);
        cells.forEach((cell) => setCellWidth(cell, width));
        const col = colgroup?.children[index];
        if (col) {
            setCellWidth(col, width);
        }
    });
    table.style.width = `${totalWidth}px`;
    table.style.minWidth = `${totalWidth}px`;
    table.style.maxWidth = "none";
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

if (ListRenderer.prototype.__goldverseLaundryListColumnPatchVersion !== 3) {
    patch(ListRenderer.prototype, {
        __goldverseLaundryListColumnPatchVersion: 3,

        getActiveColumns() {
            const columns = super.getActiveColumns(...arguments);
            return isGoldverseLaundryList(this) ? applySavedOrder(this, columns) : columns;
        },
    });
}
