import os
import json
import requests
from dotenv import load_dotenv


class OllamaService:
    def __init__(self):
        load_dotenv(override=True)
        self.model_name = os.getenv("OLLAMA_MODEL", "llama3.2").strip().strip('"').strip("'")
        self.api_url = "http://localhost:11434/api/generate"

    def _call_ollama(self, prompt: str,json_format: bool = False) -> str:
        """Helper to call Ollama API directly"""
        
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p": 0.1,
                "num_predict": 512,             # Caps response length so it stays fast
                "stop": ["```", "\n\n"]     # Immediately cuts engine when SQL closes
            }
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

=== CRITICAL: SCHEMA vs TABLE DISTINCTION (NEVER VIOLATE) ===
'Sales_Masters', 'Purchase_Masters', and 'masters' are DATABASE SCHEMAS (namespaces), NOT tables.
NEVER query a schema name directly — this will ALWAYS fail validation.
  FORBIDDEN: FROM Sales_Masters          ← This is a SCHEMA, not a table!
  FORBIDDEN: JOIN Purchase_Masters       ← This is a SCHEMA, not a table!
  FORBIDDEN: FROM masters                ← This is a SCHEMA, not a table!
  CORRECT:   FROM Sales_Masters.SalesOrder_Header AS T1
  CORRECT:   JOIN Purchase_Masters.purchase_orders_Header AS T2
  CORRECT:   FROM masters.items AS T1

=== STRICT SQL RULES ===
1. TRANSLATION & TABLES: You are a precise Text-to-SQL translator. You must ONLY use the exact tables provided in the schema context. Never guess or use generic table names like 'invoices', 'orders', or 'users'. Always use their fully qualified names (e.g., Schema.Table_Name).

2. DATABASE TRANSFORMATION DICTIONARY:
   - "Invoices" -> Always use `Sales_Masters.Invoice_Header` (Total counts, customer names, invoice value are here).
   - "Sales Orders" -> Always use `Sales_Masters.SalesOrder_Header` for counts/dates, and join `Sales_Masters.SalesOrder_Details` for specific item arrays.
   - "Revenue" -> Calculated as SUM(total) from `Sales_Masters.Invoice_Header`.
   - "Overdue Invoices" / "Aging Analysis" -> Query the `Analytics_Masters.v_accounts_receivable_aging` view.
   - "Customers" -> Use `masters.customers`.

3. STRICT TEMPORAL RULES:
   - "This Month": Use WHERE created_at >= '2026-06-01' AND created_at <= '2026-06-30'
   - "This Quarter": Use WHERE created_at >= '2026-04-01' AND created_at <= '2026-06-30'

4. CRITICAL FILTER GUARDRAIL:
   Never add arbitrary column filters like `WHERE status = 'Valid'` or `WHERE payment_status = 'paid'` unless those exact columns are explicitly listed in the schema context.

5. TABLE NAMES: Always use FULL SchemaName.TableName as shown in schema (e.g., Sales_Masters.SalesOrder_Header). CASE-SENSITIVE.
   WRONG: FROM SalesOrder_Header
   WRONG: FROM Sales_Masters
   RIGHT: FROM Sales_Masters.SalesOrder_Header AS T1

6. COLUMNS: Only use columns explicitly listed in the schema. Never invent columns.

7. ALIASES: Every table MUST use an alias (T1, T2...). Every column MUST be prefixed with its alias.

8. JOINS: Only join on columns that exist in both tables.

9. SELECT ONLY. Never INSERT/UPDATE/DELETE/DROP/ALTER.

10. CONVERSATIONAL AND DEFINITION INPUT: If the user is greeting (hi, hello), asking for a general definition/explanation/concept, or not asking for data, return empty SQL "". Generate SQL ONLY when the user explicitly asks for data, reports, analytics, or queries.

11. DATE FILTERS: Words like "right now", "currently", "to date", or "total" mean ALL-TIME. DO NOT add any date filters for these words. ONLY add date filters (WHERE MONTH... or WHERE YEAR...) if the user explicitly mentions a strict time block (e.g., "today", "this month", "last week").

12. chart_type selection:
   - "card"      → single number result (count, sum, average)
   - "barchart"  → comparison across categories
   - "linechart" → trend over time
   - "piechart"  → proportional breakdown
   - "table"     → list of multiple records/rows

13. SELF-CHECK: Before returning SQL, scan every FROM and JOIN target. If any target does NOT contain a dot (.), it is WRONG. Rewrite it with the correct SchemaName prefix.

=== SELF-CORRECTION PROTOCOL (FOR RETRY ATTEMPTS) ===
If a previous attempt failed with a 'SCHEMA-AS-TABLE ERROR' or 'TABLE NOT FOUND' error:
1. Do NOT repeat the same query. Do NOT argue.
2. Acknowledge that you targeted a schema/namespace instead of a specific table.
3. Inspect the "Available tables" list provided in the error message.
4. Immediately rewrite the SQL using the correct full Schema.Table dot notation.
Example fix: Change 'FROM Sales_Masters' → 'FROM Sales_Masters.SalesOrder_Header AS T1'

=== EXAMPLES ===

EXAMPLE 1 — "total GRN" (no time period = no date filter):
  Schema: Purchase_Masters.grn_Header (columns: grn_id, grn_number, po_id, supplier_id, grn_date, created_at)
  SQL: SELECT COUNT(T1.grn_id) AS total_grn FROM Purchase_Masters.grn_Header AS T1
  chart_type: card

EXAMPLE 2 — "total purchase amount this month":
  Schema: Purchase_Masters.purchase_orders_Header (columns: po_id, po_number, po_date, sub_total, tax_total, grand_total)
  SQL: SELECT SUM(T1.grand_total) AS total_purchase FROM Purchase_Masters.purchase_orders_Header AS T1 WHERE T1.po_date >= '2026-06-01' AND T1.po_date <= '2026-06-30'
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
  SQL: SELECT COUNT(T1.invoice_id) AS total_invoices FROM Sales_Masters.Invoice_Header AS T1 WHERE T1.created_at >= '2026-06-01' AND T1.created_at <= '2026-06-30'
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
  SQL: SELECT T1.po_id, T1.po_number, T1.po_date, T1.grand_total FROM Purchase_Masters.purchase_orders_Header AS T1 WHERE T1.po_date >= '2026-06-01' AND T1.po_date <= '2026-06-30' ORDER BY T1.po_date DESC
  chart_type: table

EXAMPLE 14 — "how many local purchases total" OR "total count of local purchases":
  CRITICAL RULE: 'local purchases' = purchase_orders_Header (NOT grn_Header, NOT inventory_batches).
  Schema: Purchase_Masters.purchase_orders_Header (columns: po_id, po_number, po_date, grand_total)
  SQL: SELECT COUNT(T1.po_id) AS total_local_purchases FROM Purchase_Masters.purchase_orders_Header AS T1
  chart_type: card

EXAMPLE 15 — "how many import purchases this month" OR "list import purchase orders":
  CRITICAL RULE: Use ONLY 'import_purchase_orders_Header'. NEVER use 'import_purchase', 'import_po', or 'import_purchase_item' — those tables DO NOT EXIST.
  Schema: Purchase_Masters.import_purchase_orders_Header (columns: import_po_id, import_po_number, supplier_id, po_date, total_lcy, status)
  SQL: SELECT T1.import_po_id, T1.import_po_number, T1.po_date, T1.total_lcy FROM Purchase_Masters.import_purchase_orders_Header AS T1 WHERE T1.po_date >= '2026-06-01' AND T1.po_date <= '2026-06-30' ORDER BY T1.po_date DESC
  chart_type: table

EXAMPLE 16 — "import purchase items" OR "what items are in import PO":
  CRITICAL RULE: Join import_purchase_orders_Header to import_purchase_orders_Details on import_po_id. Then join masters.items on item_id.
  NEVER use: import_purchase_item, import_purchase_item_details, import_po_Header, import_po_items — NONE of these exist.
  SQL: SELECT T1.import_po_number, T3.name AS item_name, T2.qty, T2.fcy_unit_price FROM Purchase_Masters.import_purchase_orders_Header AS T1 JOIN Purchase_Masters.import_purchase_orders_Details AS T2 ON T1.import_po_id = T2.import_po_id JOIN masters.items AS T3 ON T2.item_id = T3.id LIMIT 20
  chart_type: table

EXAMPLE 17 — "give the details of sales order SO2026-001" OR "show SO SO2026-001":
  CRITICAL: NEVER write 'FROM Sales_Masters WHERE ...' — Sales_Masters is a SCHEMA, not a table!
  Schema: Sales_Masters.SalesOrder_Header (columns: id, So_number, customer_name, date, delivery_schedule, invoice_generated, created_at)
  WRONG: SELECT * FROM Sales_Masters WHERE So_number = 'SO2026-001'
  CORRECT: SELECT T1.id, T1.So_number, T1.customer_name, T1.date, T1.delivery_schedule, T1.invoice_generated, T1.created_at FROM Sales_Masters.SalesOrder_Header AS T1 WHERE T1.So_number = 'SO2026-001'
  chart_type: table

EXAMPLE 18 — "show items in sales order SO2026-001" OR "what items are in SO SO2026-001":
  Schema: Sales_Masters.SalesOrder_Details (columns: so_details_id, So_number, item_id, name, ordered_qty, supplied_qty, pending_qty, unit_price)
  SQL: SELECT T1.name, T1.ordered_qty, T1.supplied_qty, T1.pending_qty, T1.unit_price FROM Sales_Masters.SalesOrder_Details AS T1 WHERE T1.So_number = 'SO2026-001'
  chart_type: table

EXAMPLE 19 — "full details with items for sales order SO2026-001":
  Schema: Sales_Masters.SalesOrder_Header + Sales_Masters.SalesOrder_Details (join on So_number)
  SQL: SELECT T1.So_number, T1.customer_name, T1.date, T2.name AS item_name, T2.ordered_qty, T2.unit_price, (T2.ordered_qty * T2.unit_price) AS line_total FROM Sales_Masters.SalesOrder_Header AS T1 INNER JOIN Sales_Masters.SalesOrder_Details AS T2 ON T1.So_number = T2.So_number WHERE T1.So_number = 'SO2026-001'
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

            result_json = json.loads(response_text)
            sql_query = result_json.get("sql", "") or result_json.get("query", "") or result_json.get("SQL", "")
            print(f"[OllamaService] Question: '{question}'")
            print(f"[OllamaService] Generated SQL: {sql_query}")
            return result_json
        except json.JSONDecodeError:
            print(f"Ollama returned non-JSON: {response_text}")
            raise Exception(f"Ollama failed to return a valid JSON response. Raw: {response_text}")
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

=== STRICT REPORTING RULES (CRITICAL) ===

1. NO CONVERSATIONAL FILLER:
   - NEVER say "Here is the data," "Based on the records provided," "I found the following," or "To answer your question."
   - NEVER introduce yourself. Start the very first word with the actual data.

2. ABSOLUTE LENGTH LIMITS (Choose ONE format):
   - FORMAT A (Single Number/Count): Write EXACTLY ONE plain-English sentence. (Example: 'There are 44 active items in the system.')
   - FORMAT B (List/Multiple Records): Write MAXIMUM 2 summary sentences, followed by MAXIMUM 5 bullet points.

3. HANDLING EMPTY DATA []:
   - If ERP Data is [], output EXACTLY ONE sentence stating no records were found.
   - Example: 'No purchase orders were found for this month.'
   - DO NOT explain the concept or suggest alternative actions.

4. FORMATTING & STYLE:
   - Use INR formatting for currency (e.g., INR 1,23,456).
   - NEVER output raw JSON arrays like [{{...}}] or SQL column names like 'COUNT(*)'.
   - DO NOT use emojis, markdown bolding, or special Unicode symbols.
   - Never create fictional company statistics.
   - Do NOT repeat the question.

Response Format for Lists:
Summary:
- [Fact 1]
- [Fact 2]

Top records:
- [Name]: [Value]
- [Name]: [Value]
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

    def generate_document_rag_response(self, question: str, chunks: list) -> str:
        context = "\n\n".join(f"[Source: {chunk.get('filename')}]\n{chunk.get('text')}" for chunk in chunks)
        prompt = f"""You are EDIP AI, an ERP Business Assistant.

Answer the user's question based strictly on the provided context of uploaded documents/spreadsheets.
If the context does not contain enough information to answer, state clearly that you cannot find the answer in the uploaded files.

=== Uploaded Documents Context ===
{context}

=== Question ===
{question}

=== Rules ===
- Be concise and clear.
- Do not make up any facts.
- Answer directly based on the context.
- Use bullet points if listing items.
"""
        return self._call_ollama(prompt)


