"""
ERP Schema Discovery & Catalog Generator
Scans all databases, infers ERP metadata, outputs Qdrant-ready JSON
"""
import json
import sys
import urllib.parse
import sqlalchemy
from sqlalchemy import text, inspect
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# ─────────────────────────────────────────────
# DATABASE CONNECTIONS
# ─────────────────────────────────────────────
pwd = urllib.parse.quote_plus("Tr@d3w@63")
BASE = f"mysql+pymysql://root:{pwd}@100.86.181.18:3309"

DATABASES = {
    "Purchase_Masters": f"{BASE}/Purchase_Masters",
    "Sales_Masters":    f"{BASE}/Sales_Masters",
    "masters":          f"{BASE}/masters",
}

# ─────────────────────────────────────────────
# ERP MODULE CLASSIFICATION RULES
# ─────────────────────────────────────────────
MODULE_RULES = [
    ("Procurement",   ["purchase_order", "purchase_requisition", "grn", "goods_receipt", "landed_cost", "purchase_return"]),
    ("Inventory",     ["inventory", "stock", "batch", "warehouse", "item", "product"]),
    ("Sales",         ["sales_order", "invoice", "salesorder", "customer_order"]),
    ("Finance",       ["invoice", "payment", "account", "ledger", "tax"]),
    ("Supplier",      ["supplier", "vendor"]),
    ("Customer",      ["customer", "client", "buyer"]),
    ("Masters",       ["item", "product", "uom", "category", "brand", "currency"]),
    ("Manufacturing", ["bom", "bill_of_material", "production", "work_order"]),
    ("HR",            ["employee", "payroll", "leave", "attendance"]),
]

# ─────────────────────────────────────────────
# BUSINESS PURPOSE TEMPLATES
# ─────────────────────────────────────────────
TABLE_PURPOSE = {
    "purchase_orders_Header":       "Stores LOCAL Purchase Order headers — supplier, date, totals. One row per PO.",
    "purchase_order_Details":       "Stores line items for local Purchase Orders — item, qty, price per PO.",
    "purchase_order_delivery_schedules": "Tracks expected delivery dates and quantities for each local PO.",
    "purchase_requisitions_Header": "Stores Purchase Requisition (PR) headers — department requests for goods/services.",
    "purchase_requisition_Details": "Line items for each Purchase Requisition — item, qty, unit price.",
    "grn_Header":                   "Stores Goods Receipt Note (GRN) headers — records of goods physically received from suppliers.",
    "grn_Details":                  "Line items for each GRN — item received, quantity, batch, expiry.",
    "purchase_return_Header":       "Stores Purchase Return headers — items returned to suppliers with debit note status.",
    "purchase_return_Details":      "Line items for Purchase Returns — returned item, qty, reason.",
    "import_purchase_orders_Header":"Stores IMPORT Purchase Order headers — foreign supplier, currency, exchange rate.",
    "import_purchase_orders_Details":"Line items for Import Purchase Orders — item, foreign currency qty and price.",
    "import_landed_costs_Header":   "Stores import landed cost details — customs duty, freight, insurance per import PO.",
    "import_landed_costs_Details":  "Per-item cost allocation of import landed costs — allocated overhead, landed unit cost.",
    "local_landed_cost_Header":     "Stores local landed cost details — insurance, handling, freight charges per GRN.",
    "local_landed_cost_Details":    "Per-item cost allocation of local landed costs — unit price, allocated overhead.",
    "inventory_batches":            "Tracks current inventory batch stock levels — item, current qty, landed cost, selling price.",
    "SalesOrder_Header":            "Stores Sales Order (SO) headers — customer, date, delivery schedule.",
    "SalesOrder_Details":           "Line items for Sales Orders — item, ordered qty, supplied qty, pending qty.",
    "Invoice_Header":               "Stores Sales Invoice headers — customer, amount, tax, total value.",
    "Invoice_Details":              "Line items for Sales Invoices — item, qty, unit price.",
    "items":                        "Master catalog of all inventory items — name, category, brand, UOM, min stock, reorder level, standard price.",
    "suppliers":                    "Master list of all suppliers/vendors — name, contact, type, payment terms, currency.",
    "customers":                    "Master list of all customers/clients — name, contact, credit limit, payment terms.",
}

# ─────────────────────────────────────────────
# COLUMN BUSINESS MEANINGS
# ─────────────────────────────────────────────
COLUMN_MEANINGS = {
    "po_id":                "Unique Purchase Order ID (Primary Key)",
    "po_number":            "Purchase Order Reference Number (e.g. PO-001)",
    "po_date":              "Date the Purchase Order was issued",
    "pr_id":                "Purchase Requisition ID (Foreign Key to purchase_requisitions_Header)",
    "supplier_id":          "Supplier/Vendor ID (Foreign Key to masters.suppliers)",
    "grand_total":          "Total PO value including taxes",
    "sub_total":            "PO value before taxes",
    "tax_total":            "Total tax amount on the PO",
    "payment_terms":        "Agreed payment terms with supplier (e.g. Net 30, Cash)",
    "grn_id":               "Goods Receipt Note ID (Primary Key)",
    "grn_number":           "GRN Reference Number (e.g. GRN-001)",
    "grn_date":             "Date goods were physically received",
    "received_qty":         "Quantity of items actually received",
    "po_qty":               "Quantity ordered in the original PO",
    "batch_lot_number":     "Manufacturing batch/lot number of received goods",
    "mfg_date":             "Manufacturing date of received goods",
    "expiry_date":          "Expiry date of received goods",
    "return_id":            "Purchase Return ID (Primary Key)",
    "return_number":        "Return Reference Number",
    "return_date":          "Date goods were returned to supplier",
    "return_qty":           "Quantity returned to supplier",
    "inwarded_qty":         "Quantity that was originally received (inward qty)",
    "return_reason":        "Reason for returning goods to supplier",
    "debit_note_status":    "Status of debit note raised against supplier (Pending/Approved)",
    "refund_total":         "Total refund amount from supplier",
    "import_po_id":         "Import Purchase Order ID (Primary Key)",
    "import_po_number":     "Import PO Reference Number (e.g. IPO-2026-001)",
    "currency_id":          "Foreign currency ID used for this import PO",
    "exchange_rate":        "Exchange rate at time of PO (Foreign currency to LCY)",
    "total_fcy":            "Total value in Foreign Currency (FCY)",
    "total_lcy":            "Total value in Local Currency (LCY/INR)",
    "status":               "Current status of the record (e.g. Ordered, Received, Cancelled)",
    "fcy_unit_price":       "Unit price in Foreign Currency",
    "total_landed_cost":    "Total landed cost including all charges (duty, freight, insurance)",
    "is_posted":            "1 = Landed cost is finalized/posted, 0 = Draft",
    "duty_percent":         "Customs duty percentage applied to import",
    "sea_freight":          "Sea freight charges",
    "road_freight":         "Road/land freight charges",
    "local_transport":      "Local transport/delivery charges",
    "insurance_cost":       "Insurance charges",
    "handling_charges":     "Handling/loading charges",
    "packing_charges":      "Packing charges",
    "aging_charges":        "Aging/storage charges",
    "total_customs_duty":   "Total customs duty paid",
    "total_freight":        "Total freight charges",
    "total_overhead":       "Total overhead/additional charges",
    "landed_unit_cost":     "Cost per unit after allocating all landed costs",
    "allocated_overhead":   "Overhead amount allocated to this specific item",
    "batch_id":             "Inventory Batch ID (Primary Key)",
    "batch_no":             "Batch reference number",
    "item_id":              "Item/Product ID (Foreign Key to masters.items)",
    "current_qty":          "Current available stock quantity",
    "inward_qty":           "Total quantity received (inward)",
    "outward_qty":          "Total quantity issued/sold (outward)",
    "damaged_qty":          "Quantity damaged or written off",
    "final_selling_price":  "Final selling price per unit",
    "margin_percent":       "Profit margin percentage",
    "source_type":          "Source of inventory (Local Purchase, Import, etc.)",
    "So_number":            "Sales Order Reference Number (e.g. SO-001)",
    "customer_name":        "Customer name on the sales order",
    "date":                 "Sales Order date",
    "delivery_schedule":    "Scheduled delivery date for the order",
    "invoice_generated":    "1 = Invoice has been generated, 0 = Pending invoice",
    "ordered_qty":          "Quantity ordered by customer",
    "supplied_qty":         "Quantity already supplied/delivered",
    "pending_qty":          "Quantity yet to be supplied (ordered - supplied)",
    "unit_price":           "Price per unit",
    "invoice_id":           "Sales Invoice ID (Primary Key)",
    "so_id":                "Sales Order ID (Foreign Key to SalesOrder_Header)",
    "cpo_ref":              "Customer Purchase Order Reference number",
    "amount":               "Invoice amount before tax",
    "tax_amount":           "Tax amount on invoice",
    "tax_type":             "Type of tax applied (e.g. GST, VAT)",
    "total":                "Total invoice value (amount + tax) — USE THIS for invoice amounts",
    "name":                 "Name of the item/supplier/customer",
    "standardPrice":        "Standard selling price of the item",
    "minStock":             "Minimum stock level — alert if stock falls below this",
    "reorderLevel":         "Reorder point — trigger purchase when stock reaches this level",
    "hsnCode":              "HSN (Harmonized System Nomenclature) code for tax purposes",
    "isImported":           "1 = Item is imported, 0 = Locally sourced",
    "active":               "1 = Active record, 0 = Inactive/disabled",
    "creditLimit":          "Maximum credit amount allowed for the customer",
    "leadTime":             "Supplier lead time in days",
    "qty":                  "Quantity",
    "quantity":             "Quantity",
    "line_total":           "Total value of this line item (qty × unit_price)",
    "pr_number":            "Purchase Requisition Reference Number",
    "pr_date":              "Date the requisition was raised",
    "department":           "Department that raised the requisition",
    "requested_by":         "Employee who requested the items",
    "required_by_date":     "Date by which items are needed",
    "requested_quantity":   "Quantity requested in the requisition",
    "reason_for_request":   "Business reason for the purchase request",
    "priority":             "Priority level of the requisition (High/Medium/Low)",
    "schedule_id":          "Delivery schedule ID (Primary Key)",
    "expected_delivery_date": "Expected date for PO delivery",
    "target_quantity":      "Target quantity for the scheduled delivery",
    "return_item_id":       "Purchase Return item ID (Primary Key)",
    "po_item_id":           "Purchase Order line item ID (Primary Key)",
    "detail_id":            "Detail line item ID (Primary Key)",
    "so_details_id":        "Sales Order detail line item ID (Primary Key)",
    "group_id":             "Item group/family classification",
    "category_id":          "Item category classification",
    "brand":                "Brand name of the item",
    "model":                "Model number of the item",
    "size":                 "Size specification of the item",
    "color":                "Color of the item",
    "uom_id":               "Unit of Measure ID (e.g. KG, Piece, Liter)",
    "created_at":           "Timestamp when record was created",
    "updated_at":           "Timestamp when record was last updated",
    "tax_rate":             "Tax rate percentage applied to line item",
    "import_landed_cost_id":"Import Landed Cost ID (Primary Key)",
    "landed_cost_id":       "Local Landed Cost ID (Primary Key)",
    "landed_cost_item_id":  "Landed Cost line item ID (Primary Key)",
    "val_lcy":              "Value in Local Currency",
    "fob_val_lcy":          "Free-On-Board value in Local Currency",
    "cess_percent":         "CESS surcharge percentage on customs duty",
    "gst_percent":          "GST percentage applicable",
    "include_gst":          "1 = Include GST in landed cost calculation, 0 = Exclude",
    "liner_charges":        "Port liner/terminal handling charges",
    "total_port_charges":   "Total port and terminal charges",
    "return_item_id":       "Return line item ID (Primary Key)",
}

# ─────────────────────────────────────────────
# EXAMPLE BUSINESS QUERIES PER TABLE
# ─────────────────────────────────────────────
EXAMPLE_QUERIES = {
    "purchase_orders_Header": [
        "How many local purchase orders were made this month?",
        "What is our total local purchase spend this year?",
        "List all purchase orders with their supplier and total value",
    ],
    "purchase_order_Details": [
        "What items are in PO-001?",
        "Which items are most frequently purchased locally?",
        "What is the total ordered quantity per item this month?",
    ],
    "grn_Header": [
        "How many GRNs were received this month?",
        "Which GRNs are pending this week?",
        "List all goods receipts for a specific supplier",
    ],
    "inventory_batches": [
        "What is the current stock value of all items?",
        "Which items have zero stock?",
        "Which items are running low on stock?",
        "What is the total inventory worth?",
    ],
    "import_purchase_orders_Header": [
        "How many import purchase orders are there this month?",
        "What is the total import spend in LCY this year?",
        "List all import POs with status and value",
    ],
    "import_landed_costs_Header": [
        "What is our total import landed cost this year?",
        "What is the total customs duty paid?",
        "What is total freight cost on imports?",
    ],
    "SalesOrder_Header": [
        "How many sales orders were created this month?",
        "How many sales orders are pending delivery?",
        "What is our total sales order value this quarter?",
    ],
    "Invoice_Header": [
        "What is our total revenue this month?",
        "Who are our top 10 customers by revenue?",
        "What is the highest value invoice this month?",
        "What is the total invoiced amount this year?",
    ],
    "items": [
        "Which items have exceeded their reorder level?",
        "List all imported items",
        "What items are in the low stock alert?",
    ],
    "suppliers": [
        "Which supplier do we buy from the most?",
        "List all active suppliers",
        "Which supplier has the highest total purchase value?",
    ],
    "purchase_requisitions_Header": [
        "How many purchase requisitions are open this month?",
        "Which purchase requisitions are not converted to PO?",
        "List PRs by department",
    ],
    "purchase_return_Header": [
        "How many purchase returns were made this month?",
        "What is the total refund value from supplier returns?",
        "List all pending debit notes",
    ],
}


def classify_module(table_name: str, schema_name: str) -> str:
    name_lower = table_name.lower()
    schema_lower = schema_name.lower()

    if "sales" in schema_lower:
        if "invoice" in name_lower:
            return "Finance / Sales"
        return "Sales"

    for module, keywords in MODULE_RULES:
        for kw in keywords:
            if kw.replace("_", "") in name_lower.replace("_", ""):
                return module

    return "General"


def get_column_meaning(col_name: str, col_type: str) -> str:
    if col_name in COLUMN_MEANINGS:
        return COLUMN_MEANINGS[col_name]
    # Infer from name patterns
    if col_name.endswith("_id"):
        base = col_name[:-3].replace("_", " ").title()
        return f"{base} reference ID"
    if col_name.endswith("_date") or col_name == "date":
        return f"Date field for {col_name.replace('_date','').replace('_',' ')}"
    if col_name.endswith("_at"):
        return f"Timestamp for {col_name.replace('_at','').replace('_',' ')}"
    if "total" in col_name or "amount" in col_name or "price" in col_name or "cost" in col_name:
        return f"Monetary value — {col_name.replace('_', ' ')}"
    if "qty" in col_name or "quantity" in col_name:
        return f"Quantity field — {col_name.replace('_', ' ')}"
    if col_name.startswith("is_") or col_name.startswith("has_"):
        return f"Boolean flag — 1=Yes, 0=No for {col_name.replace('is_','').replace('has_','')}"
    return col_name.replace("_", " ").title()


def get_foreign_keys(inspector, table_name: str) -> list:
    fks = []
    try:
        raw_fks = inspector.get_foreign_keys(table_name)
        for fk in raw_fks:
            for col in fk.get("constrained_columns", []):
                ref_table = fk.get("referred_table", "")
                ref_cols = fk.get("referred_columns", [])
                fks.append({
                    "column": col,
                    "references_table": ref_table,
                    "references_column": ref_cols[0] if ref_cols else "",
                })
    except Exception:
        pass
    return fks


def generate_catalog():
    catalog = []
    vector_docs = []  # Qdrant-ready payloads

    for schema_name, conn_url in DATABASES.items():
        print(f"\nScanning schema: {schema_name}...")
        try:
            engine = sqlalchemy.create_engine(conn_url)
            inspector = inspect(engine)
            tables = inspector.get_table_names()
        except Exception as e:
            print(f"  ERROR connecting to {schema_name}: {e}")
            continue

        for table_name in tables:
            print(f"  Table: {table_name}")
            try:
                columns_raw = inspector.get_columns(table_name)
                pk = inspector.get_pk_constraint(table_name)
                fks = get_foreign_keys(inspector, table_name)
                pk_cols = pk.get("constrained_columns", [])
            except Exception as e:
                print(f"    ERROR: {e}")
                continue

            # Build column details
            columns = []
            col_names = []
            for col in columns_raw:
                col_name = col["name"]
                col_type = str(col["type"])
                col_names.append(col_name)
                columns.append({
                    "column_name": col_name,
                    "data_type": col_type,
                    "business_meaning": get_column_meaning(col_name, col_type),
                    "is_primary_key": col_name in pk_cols,
                    "is_foreign_key": any(fk["column"] == col_name for fk in fks),
                    "nullable": col.get("nullable", True),
                })

            # Determine business purpose
            purpose = TABLE_PURPOSE.get(
                table_name,
                f"Stores {table_name.replace('_', ' ').lower()} records."
            )

            # ERP module classification
            module = classify_module(table_name, schema_name)

            # Example queries
            queries = EXAMPLE_QUERIES.get(table_name, [
                f"List all {table_name.replace('_', ' ').lower()} records",
                f"Count total {table_name.replace('_', ' ').lower()} this month",
            ])

            # Build catalog entry
            entry = {
                "schema_name": schema_name,
                "table_name": table_name,
                "full_table_name": f"{schema_name}.{table_name}",
                "business_purpose": purpose,
                "erp_module": module,
                "primary_key": pk_cols,
                "foreign_keys": fks,
                "columns": columns,
                "example_queries": queries,
                "generated_at": datetime.now().isoformat(),
            }
            catalog.append(entry)

            # Build Qdrant-ready vector document
            # Rich text description for embedding
            col_summary = ", ".join([
                f"{c['column_name']} ({c['data_type']}): {c['business_meaning']}"
                for c in columns
            ])
            fk_summary = "; ".join([
                f"{fk['column']} -> {fk['references_table']}.{fk['references_column']}"
                for fk in fks
            ]) or "No foreign keys"

            vector_text = (
                f"Table: {schema_name}.{table_name}. "
                f"Purpose: {purpose} "
                f"Module: {module}. "
                f"Columns: {col_summary}. "
                f"Relationships: {fk_summary}. "
                f"Sample questions: {'; '.join(queries)}"
            )

            vector_doc = {
                "table_name": f"{schema_name}.{table_name}",
                "description": purpose,
                "columns": col_summary,
                "erp_module": module,
                "primary_key": ", ".join(pk_cols),
                "foreign_keys": fk_summary,
                "example_queries": queries,
                "vector_text": vector_text,  # This is what gets embedded
                "schema": schema_name,
            }
            vector_docs.append(vector_doc)

    return catalog, vector_docs


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("ERP Schema Discovery & Catalog Generator")
    print("=" * 60)

    catalog, vector_docs = generate_catalog()

    # Save full catalog
    output_path = "d:/EDIP Suite/backend/erp_schema_catalog.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull catalog saved: {output_path}")
    print(f"Total tables catalogued: {len(catalog)}")

    # Save Qdrant-ready documents
    qdrant_path = "d:/EDIP Suite/backend/erp_qdrant_payloads.json"
    with open(qdrant_path, "w", encoding="utf-8") as f:
        json.dump(vector_docs, f, indent=2, ensure_ascii=False, default=str)
    print(f"Qdrant payloads saved: {qdrant_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("CATALOG SUMMARY")
    print("=" * 60)
    from collections import defaultdict
    by_schema = defaultdict(list)
    by_module = defaultdict(list)
    for e in catalog:
        by_schema[e["schema_name"]].append(e["table_name"])
        by_module[e["erp_module"]].append(f"{e['schema_name']}.{e['table_name']}")

    print("\nBy Schema:")
    for schema, tables in sorted(by_schema.items()):
        print(f"  {schema}: {len(tables)} tables")
        for t in tables:
            print(f"    - {t}")

    print("\nBy ERP Module:")
    for module, tables in sorted(by_module.items()):
        print(f"  [{module}]")
        for t in tables:
            print(f"    - {t}")
