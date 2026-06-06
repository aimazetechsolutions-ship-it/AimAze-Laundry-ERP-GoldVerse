/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { ListRenderer } from "@web/views/list/list_renderer";

const LEGACY_ORDER_KEY_PREFIX = "goldverse_laundry_order_list_column_order";
const ORDER_KEY_PREFIX = "goldverse_laundry_order_list_column_order_v2";
const PINNED_FIELD_ORDER = ["name", "partner_id", "goldverse_flow_status", "priority", "payment_status"];

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
