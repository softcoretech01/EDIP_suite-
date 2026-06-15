import os
import json
import requests
from dotenv import load_dotenv


class OllamaService:
    def __init__(self):
        load_dotenv(override=True)
        self.model_name = os.getenv("OLLAMA_MODEL", "llama3").strip().strip('"').strip("'")
        self.api_url = "http://localhost:11434/api/generate"

    def _call_ollama(self, prompt: str, json_format: bool = False) -> str:
        """Helper to call Ollama API directly"""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0}
        }
        if json_format:
            payload["format"] = "json"
        try:
            response = requests.post(self.api_url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError:
            raise Exception("Failed to connect to Ollama. Ensure Ollama is running.")
        except Exception as e:
            raise Exception(f"Ollama API error: {str(e)}")

    def generate_sql_and_dashboard(self, question: str, schema_context: str, previous_error: str = None) -> dict:
        """
        You are EDIP AI — a Senior ERP Business Analyst.
        Generates a SQL query from the schema and classifies the response type.
        """
        from app.services.metrics_catalog import get_metrics_prompt_extension
        metrics_prompt = get_metrics_prompt_extension()

        error_note = (
            f"\nWARNING: Previous SQL failed: '{previous_error}'. "
            f"Fix it using only valid columns from the schema.\n"
        ) if previous_error else ""

        prompt = f"""You are EDIP AI Analytics Assistant.

For comparison, trend, growth, dashboard, KPI, month-wise, year-wise, and analytics questions:
1. Generate SQL to retrieve grouped data.
2. Do not summarize until actual data is available.
3. Return structured dashboard data.

{metrics_prompt}

=== DATABASE UNDERSTANDING RULES ===
Before generating SQL:
- Identify the ERP business module (Sales, Purchase, Inventory, Finance, CRM).
- Identify required tables and columns.
- Verify all columns exist in the schema before using them.

=== ERP MODULE DETECTION ===
Sales: Sales Orders, Revenue, Invoices, Customers, Quotations
Purchase: Purchase Orders, Suppliers, GRN, Procurement
Inventory: Stock, Items, Warehouse, Inventory Movement
Finance: Receivables, Payables, Cash Flow, Payments
CRM: Customers, Leads, Opportunities

=== STRICT SQL RULES ===
1. TABLE NAMES: Always use full prefix as shown in schema (e.g., Sales_Masters.SalesOrder_Header). CASE-SENSITIVE.
   WRONG: FROM SalesOrder_Header
   RIGHT: FROM Sales_Masters.SalesOrder_Header AS T1

2. COLUMNS: Only use columns explicitly listed in the schema. Never invent columns.

3. ALIASES: Every table MUST use an alias (T1, T2...). Every column MUST be prefixed with its alias.

4. JOINS: Only join on columns that exist in both tables.

5. SELECT ONLY. Never INSERT/UPDATE/DELETE/DROP/ALTER.

6. CONVERSATIONAL AND DEFINITION INPUT: If the user is greeting (hi, hello), asking for a general definition/explanation/concept, or not asking for data, return empty SQL "". Generate SQL ONLY when the user explicitly asks for data, reports, analytics, or queries.

7. DATE FILTERS: ONLY add date filters (WHERE MONTH... or WHERE YEAR...) if the user explicitly mentions a time period (e.g., "this month", "today", "last week"). If they ask for an all-time total, do NOT add any date filter.

8. chart_type selection:
   - "card"      → single number result (count, sum, average)
   - "barchart"  → comparison across categories
   - "linechart" → trend over time
   - "piechart"  → proportional breakdown
   - "table"     → list of multiple records/rows

=== EXAMPLES ===

EXAMPLE 1 — "total GRN" (no time period = no date filter):
  Schema: Purchase_Masters.grn_Header (columns: grn_id, grn_number, po_id, supplier_id, grn_date, created_at)
  SQL: SELECT COUNT(T1.grn_id) AS total_grn FROM Purchase_Masters.grn_Header AS T1
  chart_type: card

EXAMPLE 2 — "total purchase amount this month" (time period mentioned = add date filter):
  Schema: Purchase_Masters.purchase_orders_Header (columns: po_id, po_number, po_date, sub_total, tax_total, grand_total)
  SQL: SELECT SUM(T1.grand_total) AS total_purchase FROM Purchase_Masters.purchase_orders_Header AS T1 WHERE MONTH(T1.po_date) = MONTH(CURDATE()) AND YEAR(T1.po_date) = YEAR(CURDATE())
  chart_type: card

EXAMPLE 3 — "show all suppliers":
  Schema: masters.suppliers (columns: id, name, email, phone, type, active)
  SQL: SELECT T1.id, T1.name, T1.email, T1.phone FROM masters.suppliers AS T1
  chart_type: table

EXAMPLE 4 — "which invoice has the highest value" OR "which invoice has high value":
  Schema: Sales_Masters.Invoice_Header (columns: invoice_id, so_id, customer_name, amount, tax_amount, total, created_at)
  IMPORTANT: Column is 'total' NOT 'grand_total' in Invoice_Header.
  SQL: SELECT T1.invoice_id, T1.customer_name, T1.total, T1.created_at FROM Sales_Masters.Invoice_Header AS T1 ORDER BY T1.total DESC LIMIT 10
  chart_type: table

EXAMPLE 5 — "how many invoices this month":
  Schema: Sales_Masters.Invoice_Header (columns: invoice_id, customer_name, total, created_at)
  SQL: SELECT COUNT(T1.invoice_id) AS total_invoices FROM Sales_Masters.Invoice_Header AS T1 WHERE MONTH(T1.created_at) = MONTH(CURDATE()) AND YEAR(T1.created_at) = YEAR(CURDATE())
  chart_type: card

EXAMPLE 6 — "top selling items" OR "which items sold the most":
  Schema: Sales_Masters.SalesOrder_Details (columns: so_details_id, So_number, item_id, name, ordered_qty, unit_price)
         masters.items (columns: id, name, standardPrice)
  SQL: SELECT T1.name, SUM(T1.ordered_qty) AS total_sold FROM Sales_Masters.SalesOrder_Details AS T1 GROUP BY T1.name ORDER BY total_sold DESC LIMIT 10
  chart_type: barchart

EXAMPLE 7 — "what items are in PR-001":
  Schema: Purchase_Masters.purchase_requisitions_Header (columns: pr_id, pr_number, pr_date, department)
         Purchase_Masters.purchase_requisition_Details (columns: pr_id, item_id, requested_quantity, uom, unit_price)
  SQL: SELECT T2.item_id, T2.requested_quantity, T2.uom, T2.unit_price FROM Purchase_Masters.purchase_requisitions_Header AS T1 INNER JOIN Purchase_Masters.purchase_requisition_Details AS T2 ON T1.pr_id = T2.pr_id WHERE T1.pr_number = 'PR-001'
  chart_type: table

EXAMPLE 8 — "show all customers":
  Schema: masters.customers (columns: id, name, email, phone, creditLimit, active)
  SQL: SELECT T1.id, T1.name, T1.email, T1.phone, T1.creditLimit FROM masters.customers AS T1
  chart_type: table

EXAMPLE 9 — "current stock levels" OR "inventory status":
  Schema: Purchase_Masters.inventory_batches (columns: batch_id, item_id, current_qty, final_selling_price, status)
         masters.items (columns: id, name)
  SQL: SELECT T2.name, SUM(T1.current_qty) AS stock FROM Purchase_Masters.inventory_batches AS T1 INNER JOIN masters.items AS T2 ON T1.item_id = T2.id GROUP BY T2.name ORDER BY stock DESC
  chart_type: table

EXAMPLE 10 — "highest value GRN" OR "GRN with high amount":
  Schema: Purchase_Masters.grn_Header (columns: grn_id, grn_number)
         Purchase_Masters.grn_Details (columns: grn_id, item_id, received_qty)
         masters.items (columns: id, name, standardPrice)
  SQL: SELECT T1.grn_number, T3.name, T3.standardPrice, SUM(T2.received_qty * T3.standardPrice) AS total_value FROM Purchase_Masters.grn_Header AS T1 INNER JOIN Purchase_Masters.grn_Details AS T2 ON T1.grn_id = T2.grn_id INNER JOIN masters.items AS T3 ON T2.item_id = T3.id GROUP BY T1.grn_number, T3.name, T3.standardPrice ORDER BY total_value DESC LIMIT 10
  chart_type: table

EXAMPLE 11 — "show the total landed cost for local purchases":
  Schema: Purchase_Masters.local_landed_cost_Header (columns: landed_cost_id, grn_id, total_landed_cost, is_posted)
  SQL: SELECT SUM(T1.total_landed_cost) AS total_local_landed_cost FROM Purchase_Masters.local_landed_cost_Header AS T1 WHERE T1.is_posted = 1
  chart_type: card

EXAMPLE 12 — "total landed cost for import purchases":
  Schema: Purchase_Masters.import_landed_costs_Header (columns: import_landed_cost_id, import_po_id, total_landed_cost, is_posted)
  SQL: SELECT SUM(T1.total_landed_cost) AS total_import_landed_cost FROM Purchase_Masters.import_landed_costs_Header AS T1 WHERE T1.is_posted = 1
  chart_type: card

EXAMPLE 13 — "how many local purchases are made this month" OR "list local purchase this month":
  CRITICAL RULE: 'local purchases' = purchase_orders_Header. Do NOT use grn_Header for this.
  Schema: Purchase_Masters.purchase_orders_Header (columns: po_id, po_number, po_date, grand_total)
  SQL: SELECT T1.po_id, T1.po_number, T1.po_date, T1.grand_total FROM Purchase_Masters.purchase_orders_Header AS T1 WHERE MONTH(T1.po_date) = MONTH(CURDATE()) AND YEAR(T1.po_date) = YEAR(CURDATE()) ORDER BY T1.po_date DESC
  chart_type: table

EXAMPLE 14 — "how many local purchases total" OR "total count of local purchases":
  CRITICAL RULE: 'local purchases' = purchase_orders_Header (NOT grn_Header, NOT inventory_batches).
  Schema: Purchase_Masters.purchase_orders_Header (columns: po_id, po_number, po_date, grand_total)
  SQL: SELECT COUNT(T1.po_id) AS total_local_purchases FROM Purchase_Masters.purchase_orders_Header AS T1
  chart_type: card

EXAMPLE 15 — "how many import purchases this month" OR "list import purchase orders":
  CRITICAL RULE: Use ONLY 'import_purchase_orders_Header'. NEVER use 'import_purchase', 'import_po', or 'import_purchase_item' — those tables DO NOT EXIST.
  Schema: Purchase_Masters.import_purchase_orders_Header (columns: import_po_id, import_po_number, supplier_id, po_date, total_lcy, status)
  SQL: SELECT T1.import_po_id, T1.import_po_number, T1.po_date, T1.total_lcy FROM Purchase_Masters.import_purchase_orders_Header AS T1 WHERE MONTH(T1.po_date) = MONTH(CURDATE()) AND YEAR(T1.po_date) = YEAR(CURDATE()) ORDER BY T1.po_date DESC
  chart_type: table

EXAMPLE 16 — "import purchase items" OR "what items are in import PO":
  CRITICAL RULE: Join import_purchase_orders_Header to import_purchase_orders_Details on import_po_id. Then join masters.items on item_id.
  NEVER use: import_purchase_item, import_purchase_item_details, import_po_Header, import_po_items — NONE of these exist.
  SQL: SELECT T1.import_po_number, T3.name AS item_name, T2.qty, T2.fcy_unit_price FROM Purchase_Masters.import_purchase_orders_Header AS T1 JOIN Purchase_Masters.import_purchase_orders_Details AS T2 ON T1.import_po_id = T2.import_po_id JOIN masters.items AS T3 ON T2.item_id = T3.id LIMIT 20
  chart_type: table

CRITICAL DISTINCTION:
- LOCAL purchases = Purchase_Masters.purchase_orders_Header (domestic supplier POs)
  - Line items = Purchase_Masters.purchase_order_Details (join on po_id)
- IMPORT purchases = Purchase_Masters.import_purchase_orders_Header (foreign supplier POs)
  - Line items = Purchase_Masters.import_purchase_orders_Details (join on import_po_id)
- GRN = grn_Header (goods RECEIVED, NOT purchases — never use for purchase count)
- Purchase Returns = purchase_return_Header (columns: return_id, return_number, grn_id, supplier_id, return_date, refund_total)
- FORBIDDEN table names (DO NOT USE): import_purchase, import_po, import_purchase_item, import_purchase_item_details, import_po_Header, import_po_items

{error_note}
=== SCHEMA ===
{schema_context}

=== QUESTION ===
{question}

Return ONLY valid JSON (no markdown, no code blocks, no explanation):
{{
  "sql": "The MariaDB SELECT query or empty string if not a data question.",
  "chart_type": "card | barchart | linechart | piechart | table",
  "dashboard_type": "comparison",
  "title": "A short descriptive title",
  "kpis": [],
  "chart_data": [],
  "summary": []
}}"""

        try:
            response_text = self._call_ollama(prompt, json_format=True).strip()

            # Extract JSON block even if Llama added text around it
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start != -1 and end != -1:
                response_text = response_text[start:end + 1]

            return json.loads(response_text)
        except json.JSONDecodeError:
            print(f"Ollama returned non-JSON: {response_text}")
            raise Exception("Ollama failed to return a valid JSON response.")
        except Exception as e:
            raise Exception(f"Failed to generate response from Ollama: {str(e)}")

    def generate_rag_response(self, question: str, query_data: list) -> str:
        """
        Acts as EDIP AI — Senior ERP Business Analyst.
        Takes actual database results and returns a concise, business-focused natural language answer.
        """
        data_str = json.dumps(query_data[:20], default=str)
        more_note = f"\n...and {len(query_data) - 20} more records." if len(query_data) > 20 else ""

        prompt = f"""You are EDIP AI, an ERP Business Assistant.

User Question:
{question}

ERP Data:
{data_str}{more_note}

Rules:

1. If ERP Data contains records:
   - Answer using the provided data.
   - Summarize key findings.
   - Never invent data.

2. If ERP Data is empty []:
   - This means NO records matched the query in the database.
   - State clearly that no records were found for that specific criteria.
   - Example: 'All purchase requisitions have been converted to purchase orders.' or 'No items are below minimum stock levels.'
   - Do NOT explain what the concept is. Do NOT generate SQL or sample data.
   - Be concise — 1-2 sentences max.

3. Response Format (STRICT):

For a count/total result (single number):
  Write ONE plain-English sentence. Example: 'There are 44 items in the system.'
  Do NOT show any JSON, brackets, or raw data.

For a list result (multiple rows):
Summary:
- Key Finding 1
- Key Finding 2

Top records (max 5, plain text — NO JSON, NO brackets, NO curly braces):
  - Record name: value
  - Record name: value

4. Avoid long paragraphs.
5. Never create fictional company statistics.
6. Use INR formatting for currency (e.g., INR 1,23,456).
7. Keep responses under 100 words.
8. Do NOT use emoji or special Unicode symbols.
9. Do NOT introduce yourself. Go straight to the answer.
10. Do NOT repeat the question.
11. NEVER output raw JSON arrays like [{...}] or column names like 'COUNT(*)'.
    Always describe data in plain English sentences.
"""
        try:
            return self._call_ollama(prompt, json_format=False).strip()
        except Exception as e:
            print(f"RAG generation failed: {e}")
            return "Here is the data you requested."

    def _parse_llm_json(self, raw_text: str) -> dict:
        """Robustly parse JSON out of LLM output even if surrounded by markdown"""
        import re
        match = re.search(r'\{.*\}', raw_text.replace('\n', ' '), re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    def generate_general_response(self, question: str):
        prompt = f"""
You are EDIP AI.

Answer the following ERP/business/software question.

Question:
{question}

Rules:
- Use your general knowledge.
- Do not generate SQL.
- Keep the answer concise.
- Use Definition, Key Points, and Related Modules.
"""

        return self._call_ollama(prompt)

