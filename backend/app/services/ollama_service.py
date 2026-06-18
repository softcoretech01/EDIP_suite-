import os
import json
import requests
import time
import tempfile
from dotenv import load_dotenv


class OllamaService:
    def __init__(self):
        load_dotenv(override=True)
        self.model_name = os.getenv("OLLAMA_MODEL", "qwen2.5").strip().strip('"').strip("'")
        self.api_url = "http://localhost:11434/api/generate"
        self._cache_file = os.path.join(tempfile.gettempdir(), "edip_insights_cache.json")

    def _load_cache(self) -> dict:
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self, cache: dict):
        try:
            with open(self._cache_file, "w") as f:
                json.dump(cache, f)
        except Exception:
            pass

    def _call_ollama(self, prompt: str, json_format: bool = False, stop_sequences: list = None, num_predict: int = 256) -> str:
        """Helper to call Ollama API directly"""
        if stop_sequences is None:
            stop_sequences = ["```"]
            
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p": 0.1,
                "num_ctx": 8192,                         # Cap context window as requested to speed up processing
                "num_predict": num_predict,             # Caps response length so it stays fast
                "stop": stop_sequences
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

EXAMPLE 1 — "total GRN":
  Schema: Purchase_Masters.grn_Header (columns: grn_id, grn_number)
  SQL: SELECT COUNT(T1.grn_id) AS total_grn FROM Purchase_Masters.grn_Header AS T1
  chart_type: card

EXAMPLE 2 — "total purchase amount this month":
  Schema: Purchase_Masters.purchase_orders_Header (columns: po_id, po_date, grand_total)
  SQL: SELECT SUM(T1.grand_total) AS total_purchase FROM Purchase_Masters.purchase_orders_Header AS T1 WHERE T1.po_date >= '2026-06-01' AND T1.po_date <= '2026-06-30'
  chart_type: card

EXAMPLE 3 — "show all suppliers":
  Schema: masters.suppliers (columns: id, name, email)
  SQL: SELECT T1.id, T1.name, T1.email FROM masters.suppliers AS T1
  chart_type: table

EXAMPLE 4 — "which invoice has the highest value":
  Schema: Sales_Masters.Invoice_Header (columns: invoice_id, customer_name, total)
  SQL: SELECT T1.invoice_id, T1.customer_name, T1.total FROM Sales_Masters.Invoice_Header AS T1 ORDER BY T1.total DESC LIMIT 10
  chart_type: table

EXAMPLE 5 — "top selling items":
  Schema: Sales_Masters.SalesOrder_Details (columns: ordered_qty)
          masters.items (columns: id, name)
  SQL: SELECT T1.name, SUM(T1.ordered_qty) AS total_sold FROM Sales_Masters.SalesOrder_Details AS T1 GROUP BY T1.name ORDER BY total_sold DESC LIMIT 10
  chart_type: barchart

EXAMPLE 6 — "show details of sales order SO2026-001":
  Schema: Sales_Masters.SalesOrder_Header + Sales_Masters.SalesOrder_Details (join on So_number)
  SQL: SELECT T1.So_number, T1.customer_name, T2.name AS item_name, T2.ordered_qty, T2.unit_price, (T2.ordered_qty * T2.unit_price) AS line_total FROM Sales_Masters.SalesOrder_Header AS T1 INNER JOIN Sales_Masters.SalesOrder_Details AS T2 ON T1.So_number = T2.So_number WHERE T1.So_number = 'SO2026-001'
  chart_type: table

CRITICAL DISTINCTION:
- LOCAL purchases = Purchase_Masters.purchase_orders_Header (grand_total is here, line items in purchase_order_Details)
- IMPORT purchases = Purchase_Masters.import_purchase_orders_Header (total_lcy / total_fcy is here, line items in import_purchase_orders_Details)
- GRN = grn_Header (goods RECEIVED, NOT purchases — do not use for purchase counts or amounts)
- FORBIDDEN table names: import_purchase, import_po, import_purchase_item, import_po_Header

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
            response_text = self._call_ollama(prompt, json_format=True, stop_sequences=["```", "\n\n"]).strip()

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

    def generate_rag_and_insights(self, question: str, query_data: list) -> dict:
        """
        Acts as EDIP AI — Senior ERP Business Analyst.
        Takes actual database results and returns a summary, business insights, and recommendations in one pass.
        Uses a persistent file-based cache with a 60-second TTL and rule-based fast card paths.
        """
        # 1. Check cache first with 60-second Time-To-Live (TTL)
        cache_key = f"{question.lower().strip()}|{json.dumps(query_data, sort_keys=True, default=str)}"
        now = time.time()
        cache = self._load_cache()
        if cache_key in cache:
            cached_result, cached_time = cache[cache_key]
            if now - cached_time < 60:
                print(f"[OllamaService] Cache hit for RAG and Insights (Age: {now - cached_time:.1f}s)")
                return cached_result

        # 2. Rule-based fast generator for simple single-value KPI cards
        if len(query_data) == 1 and len(query_data[0]) == 1:
            col_name, val = list(query_data[0].items())[0]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                time_suffix = ""
                if "this month" in question.lower():
                    time_suffix = " this month"
                elif "this quarter" in question.lower():
                    time_suffix = " this quarter"
                
                is_currency = any(k in col_name.lower() or k in question.lower() for k in ["amount", "value", "cost", "price", "revenue", "spend", "total_lcy", "total_fcy", "grand_total"])
                if any(k in col_name.lower() for k in ["count", "sales", "items", "suppliers", "customers"]):
                    is_currency = False

                formatted_val = f"INR {val:,.2f}" if is_currency else str(val)
                metric_name = col_name.replace('total_', '').replace('_', ' ').strip()
                
                if not is_currency:
                    summary = f"There are {formatted_val} {metric_name}{time_suffix}."
                else:
                    summary = f"The total {metric_name} is {formatted_val}{time_suffix}."

                if "sales" in metric_name or "invoice" in metric_name:
                    result = {
                        "summary": summary,
                        "business_insights": [
                            f"Sales volume is steady at {formatted_val} units.",
                            "Monitor customer purchase patterns to identify potential upselling opportunities."
                        ],
                        "recommendations": [
                            "Increase promotional activities during low-sales periods.",
                            "Analyze sales data to tailor product offerings and improve inventory management."
                        ]
                    }
                elif "purchase" in metric_name or "supplier" in metric_name or "po" in metric_name:
                    result = {
                        "summary": summary,
                        "business_insights": [
                            f"Total procurement activity stands at {formatted_val}.",
                            "Evaluate vendor lead times and delivery schedules."
                        ],
                        "recommendations": [
                            "Negotiate bulk volume discounts with primary suppliers.",
                            "Optimize procurement cycles to prevent stockout events."
                        ]
                    }
                elif "landed cost" in metric_name or "freight" in metric_name or "duty" in metric_name:
                    result = {
                        "summary": summary,
                        "business_insights": [
                            f"Landed cost analysis shows a metric of {formatted_val}.",
                            "Assess freight and duty allocations to manage shipping margins."
                        ],
                        "recommendations": [
                            "Consolidate shipments to reduce average freight costs.",
                            "Re-evaluate logistics contracts periodically to ensure favorable pricing."
                        ]
                    }
                elif "inventory" in metric_name or "stock" in metric_name:
                    result = {
                        "summary": summary,
                        "business_insights": [
                            f"Current stock level stands at {formatted_val}.",
                            "Ensure reorder thresholds are set appropriately."
                        ],
                        "recommendations": [
                            "Reorder key stock items before thresholds are breached.",
                            "Perform physical audits regularly to prevent inventory shrinkage."
                        ]
                    }
                else:
                    result = {
                        "summary": summary,
                        "business_insights": [
                            f"The current recorded value is {formatted_val}.",
                            "Track metric changes over time to identify seasonal trends."
                        ],
                        "recommendations": [
                            "Maintain standard business procedures to support current metrics.",
                            "Optimize resource allocation based on current activity levels."
                        ]
                    }

                # Apply temporal note if necessary
                temporal_keywords = ["trend", "history", "historical", "quarter-over-quarter", "qoq", "year-to-date", "ytd", "year-over-year", "yoy", "compare", "comparison", "growth"]
                if any(kw in question.lower() for kw in temporal_keywords):
                    note = "Please note, the system currently only has data available for June 2026."
                    if note.lower() not in result["summary"].lower():
                        result["summary"] = f"{result['summary']} {note}"

                # Cache and return
                cache = self._load_cache()
                cache[cache_key] = (result, time.time())
                self._save_cache(cache)
                print(f"[OllamaService] Generated rule-based fast card response for: {question}")
                return result

        # 3. Dynamic RAG/Insights generation via Ollama (for list/table/chart queries)
        data_str = json.dumps(query_data[:15], default=str)
        more_note = f"\n...and {len(query_data) - 15} more records." if len(query_data) > 15 else ""

        prompt = f"""You are EDIP AI, a Senior ERP Business Analyst.

User Question:
{question}

ERP Data:
{data_str}{more_note}

Generate a concise executive summary, exactly 2 professional business insights, and exactly 2 actionable business recommendations based on the data.

=== RULES (CRITICAL) ===
1. No conversational filler or labels.
2. The summary must be exactly 1 plain-English sentence. (Example: 'There are 91 sales this month.').
3. Keep insights and recommendations short, professional, and actionable (1 sentence per point).
4. If a column is a count (e.g., SELECT COUNT(*) AS total_sales), it represents the number of transactions/sales (e.g., 91 sales), NOT currency (e.g., NOT INR 91,000). Never assume values are currency unless the column header is a total, amount, or price.
5. Use INR formatting (e.g., INR 1,23,456) for actual currency amounts ONLY.
6. Return ONLY a valid JSON object matching this structure:
{{
  "summary": "Concise executive summary.",
  "business_insights": [
    "Insight 1",
    "Insight 2"
  ],
  "recommendations": [
    "Recommendation 1",
    "Recommendation 2"
  ]
}}
"""
        try:
            # We call Ollama with a lower token limit (256) to make it extremely fast (sub-5 seconds)
            response_text = self._call_ollama(prompt, json_format=True, stop_sequences=["```"], num_predict=256).strip()
            # Extract JSON block
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start != -1 and end != -1:
                response_text = response_text[start:end + 1]
            result = json.loads(response_text)
            
            # Apply temporal note if necessary
            summary = result.get("summary", "")
            q_lower = question.lower()
            temporal_keywords = ["trend", "history", "historical", "quarter-over-quarter", "qoq", "year-to-date", "ytd", "year-over-year", "yoy", "compare", "comparison", "growth"]
            if any(kw in q_lower for kw in temporal_keywords):
                note = "Please note, the system currently only has data available for June 2026."
                if note.lower() not in summary.lower():
                    if summary.endswith('.'):
                        result["summary"] = f"{summary} {note}"
                    else:
                        result["summary"] = f"{summary}\n\n{note}"
            
            # Save to persistent cache
            cache = self._load_cache()
            cache[cache_key] = (result, time.time())
            
            # Keep cache small (clean up entries older than 1 hour)
            cleaned_cache = {}
            for k, v in cache.items():
                if now - v[1] < 3600:
                    cleaned_cache[k] = v
            self._save_cache(cleaned_cache)
            
            return result
        except Exception as e:
            print(f"Failed to generate combined RAG and insights: {e}")
            return {
                "summary": "Here is the data you requested.",
                "business_insights": ["Review the detailed records to identify potential areas of concern."],
                "recommendations": ["Optimize operations based on the current records."]
            }

    def generate_rag_response(self, question: str, query_data: list) -> str:
        """Wrapper around combined generator to match legacy API"""
        res = self.generate_rag_and_insights(question, query_data)
        return res.get("summary", "Here is the data you requested.")

    def generate_dashboard_insights(self, question: str, query_data: list) -> dict:
        """Wrapper around combined generator to match legacy API"""
        return self.generate_rag_and_insights(question, query_data)


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
        response = self._call_ollama(prompt, stop_sequences=["```"]).strip()
        q_lower = question.lower()
        temporal_keywords = ["trend", "history", "historical", "quarter-over-quarter", "qoq", "year-to-date", "ytd", "year-over-year", "yoy", "compare", "comparison", "growth"]
        if any(kw in q_lower for kw in temporal_keywords):
            note = "Please note, the system currently only has data available for June 2026."
            if note.lower() not in response.lower():
                if response.endswith('.'):
                    response += f" {note}"
                else:
                    response += f"\n\n{note}"
        return response


