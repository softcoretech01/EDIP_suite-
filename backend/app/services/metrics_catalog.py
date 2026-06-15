CALCULATED_METRICS = {
    "sales_order_value": {
        "description": "Total value of a Sales Order. Calculate by joining Sales_Masters.SalesOrder_Header and Sales_Masters.SalesOrder_Details on So_number, and computing SUM(T2.ordered_qty * T2.unit_price).",
        "formula": "SUM(SalesOrder_Details.ordered_qty * SalesOrder_Details.unit_price)",
        "tables_involved": ["Sales_Masters.SalesOrder_Header", "Sales_Masters.SalesOrder_Details"],
        "instructions": "To get Sales Order total value, ALWAYS join SalesOrder_Header (T1) and SalesOrder_Details (T2) ON T1.So_number = T2.So_number and use SUM(T2.ordered_qty * T2.unit_price). Do NOT select or filter on T1.total or T2.total (they do not exist)."
    },
    "purchase_order_value": {
        "description": "Total value of a Purchase Order. Use grand_total column on Purchase_Masters.purchase_orders_Header.",
        "formula": "Purchase_Masters.purchase_orders_Header.grand_total",
        "tables_involved": ["Purchase_Masters.purchase_orders_Header"],
        "instructions": "Use T1.grand_total from Purchase_Masters.purchase_orders_Header. Do NOT use total or grand_total on purchase_order_Details."
    },
    "inventory_value": {
        "description": "Total value of items in inventory. Calculate by joining masters.items and Purchase_Masters.inventory_batches on item_id, and computing SUM(T1.current_qty * T1.landed_unit_cost).",
        "formula": "SUM(inventory_batches.current_qty * inventory_batches.landed_unit_cost)",
        "tables_involved": ["Purchase_Masters.inventory_batches", "masters.items"],
        "instructions": "To get total inventory value, compute SUM(T1.current_qty * T1.landed_unit_cost) from Purchase_Masters.inventory_batches."
    },
    "grn_value": {
        "description": "Total value of Goods Receipt Note (GRN) received. Calculate by joining Purchase_Masters.grn_Header, Purchase_Masters.grn_Details on grn_id, and masters.items on item_id, and computing SUM(T2.received_qty * T3.standardPrice).",
        "formula": "SUM(grn_Details.received_qty * items.standardPrice)",
        "tables_involved": ["Purchase_Masters.grn_Header", "Purchase_Masters.grn_Details", "masters.items"],
        "instructions": "To get GRN total value, join grn_Header (T1), grn_Details (T2) ON T1.grn_id = T2.grn_id, and masters.items (T3) ON T2.item_id = T3.id, and compute SUM(T2.received_qty * T3.standardPrice). Do NOT use total or grand_total on grn tables."
    }
}

def get_metrics_prompt_extension() -> str:
    """Generates a text prompt extension detailing the Calculated Metrics Catalog."""
    prompt = "\n=== CALCULATED METRICS CATALOG ===\n"
    prompt += "When generating SQL for metrics, use these strict calculations and instructions:\n\n"
    for metric_name, info in CALCULATED_METRICS.items():
        prompt += f"Metric: {metric_name}\n"
        prompt += f"- Description: {info['description']}\n"
        prompt += f"- Calculation: {info['instructions']}\n\n"
    return prompt
