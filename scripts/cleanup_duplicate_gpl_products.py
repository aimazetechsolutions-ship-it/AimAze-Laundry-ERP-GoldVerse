import os
from collections import Counter, defaultdict


APPLY = os.getenv("GV_APPLY") == "1"


def model_exists(model_name):
    return model_name in env.registry


def ref_count(model_name, domain):
    if not model_exists(model_name):
        return 0
    return env[model_name].sudo().with_context(active_test=False).search_count(domain)


Product = env["product.product"].sudo().with_context(active_test=False)
Service = env["aimaze.laundry.service"].sudo().with_context(active_test=False)

products = Product.search([("default_code", "like", "GPL-MPL-%")], order="default_code, id")
services = Service.search([("code", "like", "GPL-MPL-%")])

code_counts = Counter(product.default_code for product in products if product.default_code)
linked_products_by_code = defaultdict(set)
linked_product_ids = set()

for service in services:
    if service.product_id and service.code:
        linked_product_ids.add(service.product_id.id)
        linked_products_by_code[service.code].add(service.product_id.id)


def candidate_info(product):
    code = product.default_code or ""
    service_link_count = ref_count("aimaze.laundry.service", [("product_id", "=", product.id)])
    laundry_line_count = ref_count("aimaze.laundry.order.line", [("product_id", "=", product.id)])
    aml_count = ref_count("account.move.line", [("product_id", "=", product.id)])
    sale_line_count = ref_count("sale.order.line", [("product_id", "=", product.id)])
    purchase_line_count = ref_count("purchase.order.line", [("product_id", "=", product.id)])
    stock_move_count = ref_count("stock.move", [("product_id", "=", product.id)])
    stock_quant_count = ref_count("stock.quant", [("product_id", "=", product.id)])
    has_keeper = bool(linked_products_by_code.get(code))
    is_keeper = product.id in linked_products_by_code.get(code, set())
    is_duplicate_code = code_counts.get(code, 0) > 1
    is_unreferenced = (
        service_link_count == 0
        and laundry_line_count == 0
        and aml_count == 0
        and sale_line_count == 0
        and purchase_line_count == 0
        and stock_move_count == 0
        and stock_quant_count == 0
    )
    return {
        "product": product,
        "code": code,
        "is_keeper": is_keeper,
        "has_keeper": has_keeper,
        "is_duplicate_code": is_duplicate_code,
        "is_unreferenced": is_unreferenced,
        "service_link_count": service_link_count,
        "laundry_line_count": laundry_line_count,
        "aml_count": aml_count,
        "sale_line_count": sale_line_count,
        "purchase_line_count": purchase_line_count,
        "stock_move_count": stock_move_count,
        "stock_quant_count": stock_quant_count,
        "safe_to_delete": False,
        "delete_reason": "",
    }


infos = [candidate_info(product) for product in products]
infos_by_code = defaultdict(list)
for info in infos:
    if info["code"]:
        infos_by_code[info["code"]].append(info)

for code, group_infos in infos_by_code.items():
    keeper_infos = [info for info in group_infos if info["is_keeper"]]
    if keeper_infos:
        for info in group_infos:
            if code_counts.get(code, 0) > 1 and not info["is_keeper"] and info["is_unreferenced"]:
                info["safe_to_delete"] = True
                info["delete_reason"] = "duplicate code with master-price keeper"
        continue
    if all(info["is_unreferenced"] for info in group_infos):
        for info in group_infos:
            info["safe_to_delete"] = True
            info["delete_reason"] = (
                "duplicate code not present in GPL configuration"
                if code_counts.get(code, 0) > 1
                else "unused GPL product not present in GPL configuration"
            )

keepers = [info for info in infos if info["is_keeper"]]
candidates = [info for info in infos if info["safe_to_delete"]]
blocked = [
    info
    for info in infos
    if info["is_duplicate_code"] and not info["safe_to_delete"] and not info["is_keeper"]
]

print("GPL product cleanup scan")
print("========================")
print("apply_mode=", APPLY)
print("total_gpl_products=", len(products))
print("total_gpl_services=", len(services))
print("duplicate_code_groups=", sum(1 for _, count in code_counts.items() if count > 1))
print("keeper_products=", len(keepers))
print("delete_candidates=", len(candidates))
print("blocked_duplicates=", len(blocked))
print("")

if candidates:
    print("Delete candidates:")
    for info in candidates[:200]:
        product = info["product"]
        print(
            f"- id={product.id} tmpl={product.product_tmpl_id.id} code={info['code']} "
            f"name={product.display_name} price={product.list_price} reason={info['delete_reason']}"
        )
    if len(candidates) > 200:
        print(f"... {len(candidates) - 200} more candidates omitted")
    print("")

if blocked:
    print("Blocked duplicate products kept for safety:")
    for info in blocked[:100]:
        product = info["product"]
        print(
            f"- id={product.id} tmpl={product.product_tmpl_id.id} code={info['code']} "
            f"name={product.display_name} service_links={info['service_link_count']} "
            f"laundry_lines={info['laundry_line_count']} aml={info['aml_count']} "
            f"sale_lines={info['sale_line_count']} purchase_lines={info['purchase_line_count']} "
            f"stock_moves={info['stock_move_count']} stock_quants={info['stock_quant_count']}"
        )
    if len(blocked) > 100:
        print(f"... {len(blocked) - 100} more blocked duplicates omitted")
    print("")

if APPLY and candidates:
    ids_to_delete = [info["product"].id for info in candidates]
    print(f"Deleting {len(ids_to_delete)} orphan duplicate GPL products...")
    Product.browse(ids_to_delete).unlink()
    env.cr.commit()
    print("Deletion completed and committed.")
elif APPLY:
    print("No delete candidates found. Nothing deleted.")
else:
    print("Dry run only. Set GV_APPLY=1 to delete candidates.")
