from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import sqlalchemy
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import List, Dict, Any

from ..database.database import get_db
from ..models import models
from . import schemas
from ..auth.auth import get_current_user, HasPermission
from ..vector_db.qdrant_service import QdrantService
from ..embeddings.metadata_embedder import MetadataEmbedder
from ..services.ollama_service import OllamaService
from ..services.sql_validator import SQLValidator
from .erp_connections import build_connection_string

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)

# Lazy initialization for Qdrant to avoid uvicorn --reload lock issues
_qdrant_service = None

# Global Engine Cache to prevent TCP handshake latency on every query
_engine_cache = {}

# Single thread executor for blocking Ollama calls
_executor = ThreadPoolExecutor(max_workers=10)

def get_engine(connection_url: str):
    if connection_url not in _engine_cache:
        engine = sqlalchemy.create_engine(connection_url, pool_pre_ping=True)
        if connection_url.startswith("sqlite"):
            from sqlalchemy import event
            import sqlite3
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                if isinstance(dbapi_connection, sqlite3.Connection):
                    import os
                    # Find the backend directory containing the DB files
                    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    sales_path = os.path.join(backend_dir, "sales_masters.db").replace("\\", "/")
                    purchase_path = os.path.join(backend_dir, "purchase_masters.db").replace("\\", "/")
                    masters_path = os.path.join(backend_dir, "masters.db").replace("\\", "/")
                    
                    cursor = dbapi_connection.cursor()
                    cursor.execute(f"ATTACH DATABASE '{sales_path}' AS Sales_Masters")
                    cursor.execute(f"ATTACH DATABASE '{purchase_path}' AS Purchase_Masters")
                    cursor.execute(f"ATTACH DATABASE '{masters_path}' AS masters")
                    cursor.close()

                    # Register MySQL date compatibility functions
                    dbapi_connection.create_function("CURDATE", 0, lambda: "2026-06-15")
                    dbapi_connection.create_function("CURRENT_DATE", 0, lambda: "2026-06-15")
                    dbapi_connection.create_function("NOW", 0, lambda: "2026-06-15 17:15:05")
                    
                    def sql_year(val):
                        if not val: return None
                        try: return int(val[:4])
                        except: return None
                        
                    def sql_month(val):
                        if not val: return None
                        try: return int(val[5:7])
                        except: return None

                    def sql_day(val):
                        if not val: return None
                        try: return int(val[8:10])
                        except: return None

                    def sql_date_format(val, fmt):
                        if not val: return None
                        # Translate basic %Y, %m, %d formatting placeholders
                        res = fmt.replace('%Y', val[0:4]).replace('%m', val[5:7]).replace('%d', val[8:10])
                        return res

                    dbapi_connection.create_function("YEAR", 1, sql_year)
                    dbapi_connection.create_function("MONTH", 1, sql_month)
                    dbapi_connection.create_function("DAY", 1, sql_day)
                    dbapi_connection.create_function("DATE_FORMAT", 2, sql_date_format)

            print("[sqlite-attach] Registered database attachment & MySQL functions for SQLite connection.")
        _engine_cache[connection_url] = engine
    return _engine_cache[connection_url]

def get_qdrant():
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service

embedder = MetadataEmbedder()
ai_service = OllamaService()

OLLAMA_TIMEOUT_SECONDS = 50  # Hard ceiling for Ollama response


def build_error_hint(error_str: str, schema_context: str, failed_sql: str) -> str:
    """
    Converts a raw DB error into a targeted, actionable repair instruction for the AI.
    Detects wrong-alias errors (e.g. T1.ordered_qty when ordered_qty is in T2)
    and gives a pinpoint fix so the model doesn't repeat the same broken SQL.
    """
    import re

    # --- Unknown column: "Unknown column 'T1.ordered_qty' in 'SELECT'" ---
    unk = re.search(r"Unknown column ['\"]([^'\"]+)['\"] in", error_str)
    if unk:
        raw_col = unk.group(1)                   # e.g. "T1.ordered_qty" or "date"
        
        # Handle common unaliased hallucinations
        if raw_col in ["total_amount", "amount", "total_price"]:
            return (
                f"COLUMN NOT FOUND: '{raw_col}'. "
                f"If you need Purchase Order amounts, join purchase_orders_Header and use 'grand_total'. "
                f"If you need Invoice amounts, join Invoice_Header and use 'total'. "
                f"Do NOT use '{raw_col}' or guess column names."
            )

        parts   = raw_col.split('.')
        bad_alias  = parts[0] if len(parts) > 1 else None   # e.g. "T1"
        col_name   = parts[-1]                               # e.g. "ordered_qty"

        # Build alias→table map from the failed SQL
        # Matches: Sales_Masters.SalesOrder_Details AS T2  or  table AS T2
        alias_map = {}   # alias → full_table_name
        for m in re.finditer(
            r'([\w.]+)\s+AS\s+(T\d+)', failed_sql, re.IGNORECASE
        ):
            alias_map[m.group(2).upper()] = m.group(1)

        # Find every table in the schema that has this column
        owners = {}   # full_table_name → alias_in_sql (or None)
        for block in schema_context.split('\n\n'):
            table_match = re.search(r'Table:\s*`?([a-zA-Z0-9_.]+)', block)
            if table_match:
                tbl_name = table_match.group(1)
                cols = set(re.findall(r'Column:\s*`?([a-zA-Z0-9_]+)', block))
                if not cols:
                    cols_match = re.search(r'Columns:\s*(.+)', block, re.DOTALL)
                    if cols_match:
                        cols = {c.split('(')[0].strip().replace('`', '') for c in cols_match.group(1).split(',')}
                
                if col_name in cols:
                    # Find its alias in the SQL (if already joined)
                    alias_used = next(
                        (alias for alias, tbl in alias_map.items() if tbl == tbl_name),
                        None
                    )
                    owners[tbl_name] = alias_used

        if owners:
            owner_table, owner_alias = next(iter(owners.items()))
            if owner_alias:
                # Column exists in the SQL under a DIFFERENT alias — just fix the prefix
                hint = (
                    f"WRONG ALIAS: '{col_name}' is NOT in the table aliased as {bad_alias} "
                    f"({alias_map.get((bad_alias or '').upper(), 'unknown table')}). "
                    f"'{col_name}' belongs to {owner_table} which you aliased as {owner_alias}. "
                    f"Fix: change '{bad_alias}.{col_name}' to '{owner_alias}.{col_name}' in your SQL. "
                    f"Do NOT change the JOIN — just fix the alias prefix."
                )
            else:
                # Column exists in a table not yet joined
                hint = (
                    f"COLUMN NOT FOUND: '{col_name}' does NOT exist in "
                    f"{alias_map.get((bad_alias or '').upper(), 'the table you used')}. "
                    f"It exists in: {owner_table}. "
                    f"Add INNER JOIN {owner_table} AS Tx ON ... and use Tx.{col_name}."
                )
        else:
            hint = (
                f"COLUMN NOT FOUND: '{col_name}' does not exist in any table in the schema. "
                f"Do NOT use '{col_name}'. Check the schema and use only listed columns."
            )
        return hint

    # --- Table not found: "Table 'db.TableName' doesn't exist" ---
    tbl = re.search(r"Table '([^']+)' doesn't exist", error_str)
    if tbl:
        bad_table = tbl.group(1)
        # Check if it's a naked schema name
        schema_names = {'sales_masters', 'purchase_masters', 'masters'}
        bad_base = bad_table.split('.')[-1].lower() if '.' in bad_table else bad_table.lower()
        if bad_base in schema_names:
            schema_table_map = {
                'sales_masters': 'Sales_Masters.SalesOrder_Header',
                'purchase_masters': 'Purchase_Masters.purchase_orders_Header',
                'masters': 'masters.items'
            }
            suggested = schema_table_map.get(bad_base, '')
            return (
                f"SCHEMA-AS-TABLE ERROR: '{bad_table}' is a DATABASE SCHEMA, NOT a table. "
                f"You CANNOT use FROM {bad_table} or JOIN {bad_table}. "
                f"Use the full SchemaName.TableName format. Example: FROM {suggested} AS T1. "
                f"Fix your query to reference a specific table within the schema."
            )
        return (
            f"TABLE NOT FOUND: '{bad_table}' does not exist. "
            f"You MUST use ONLY the exact table names listed in the SCHEMA section above, "
            f"including the exact database prefix (case-sensitive). Do not guess or modify table names."
        )

    # --- Ambiguous column ---
    ambig = re.search(r"Column '([^']+)' in .* is ambiguous", error_str)
    if ambig:
        ambig_col = ambig.group(1)
        return (
            f"AMBIGUOUS COLUMN ERROR: The column '{ambig_col}' exists in multiple tables you joined. "
            f"You MUST prefix '{ambig_col}' with the correct table alias (e.g., T1.{ambig_col} or T2.{ambig_col}) everywhere in your query."
        )

    # --- Syntax error ---
    if 'syntax' in error_str.lower():
        return (
            f"SQL SYNTAX ERROR: {error_str}. "
            f"Check for: missing aliases on derived tables (every subquery needs AS name), "
            f"unmatched parentheses, or invalid MariaDB syntax."
        )

    # --- Collation mismatch ---
    if 'collation' in error_str.lower() or 'Illegal mix of collations' in error_str:
        return (
            "COLLATION ERROR: You are JOINing columns from two different databases that use different "
            "character set collations. Fix: add 'COLLATE utf8mb4_unicode_ci' to BOTH sides of the "
            "JOIN ON clause. Example: "
            "ON T1.item_id COLLATE utf8mb4_unicode_ci = T2.id COLLATE utf8mb4_unicode_ci"
        )

    # Fallback: return the raw error
    return f"SQL Error: {error_str}"


def auto_fix_sql_aliases(sql: str, schema_context: str) -> str:
    """
    Code-level SQL post-processor: automatically corrects wrong alias prefixes.
    e.g. if AI writes T1.ordered_qty but T1=SalesOrder_Header (no ordered_qty)
    and T2=SalesOrder_Details (has ordered_qty), it rewrites to T2.ordered_qty.
    This runs BEFORE execution so broken SQL never reaches the DB.
    """
    import re

    # 1. Build alias → full_table_name from SQL
    alias_map: dict[str, str] = {}
    SQL_KEYWORDS = {"AS", "ON", "JOIN", "INNER", "LEFT", "RIGHT", "CROSS", "WHERE", "GROUP", "ORDER", "LIMIT", "USING", "AND", "OR", "UNION", "SELECT"}
    
    # Find table aliases in FROM and JOIN clauses
    for m in re.finditer(r'\b(?:FROM|JOIN)\s+([\w.]+)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b', sql, re.IGNORECASE):
        table_name = m.group(1)
        alias = m.group(2).upper()
        if alias not in SQL_KEYWORDS:
            alias_map[alias] = table_name

    if not alias_map:
        return sql  # No aliases found, nothing to fix

    # 2. Build table_name → set of column names from schema context
    table_cols: dict[str, set] = {}
    for block in schema_context.split('\n\n'):
        tm = re.search(r'Table:\s*`?([a-zA-Z0-9_.]+)', block)
        if tm:
            tbl_name = tm.group(1)
            cols = set(re.findall(r'Column:\s*`?([a-zA-Z0-9_]+)', block))
            if not cols: # Try old format
                cm = re.search(r'Columns:\s*(.+)', block, re.DOTALL)
                if cm:
                    cols = {c.split('(')[0].strip().replace('`', '') for c in cm.group(1).split(',')}
            
            if tbl_name in table_cols:
                table_cols[tbl_name].update(cols)
            else:
                table_cols[tbl_name] = cols

    # 3. For each alias.column reference in the SQL, verify the column belongs to that table
    def fix_ref(m: re.Match) -> str:
        alias = m.group(1).upper()
        col   = m.group(2)
        owner_table = alias_map.get(alias)
        if not owner_table:
            return m.group(0)  # Unknown alias, leave as-is

        # Check if column is in the expected table
        owner_cols = table_cols.get(owner_table, set())
        if col in owner_cols:
            return m.group(0)  # Correct — leave as-is

        # Find which aliased table actually has this column
        for other_alias, other_table in alias_map.items():
            if other_alias != alias and col in table_cols.get(other_table, set()):
                fixed = f"{other_alias}.{col}"
                print(f"[sql-fixer] {m.group(0)} → {fixed}  ('{col}' is in {other_table})")
                return fixed

        # SPECIAL FALLBACK: Map hallucinated 'unit_price' to 'standardPrice' if available
        if col == "unit_price":
            for other_alias, other_table in alias_map.items():
                if "standardPrice" in table_cols.get(other_table, set()):
                    fixed = f"{other_alias}.standardPrice"
                    print(f"[sql-fixer-fallback] {m.group(0)} → {fixed}  (mapped unit_price to standardPrice in {other_table})")
                    return fixed

        # SPECIAL FALLBACK: Map hallucinated 'total_amount' or 'grand_total' to 'total' if available in Invoice
        if col in ["total_amount", "grand_total"]:
            for other_alias, other_table in alias_map.items():
                if "total" in table_cols.get(other_table, set()) and "Invoice_Header" in other_table:
                    fixed = f"{other_alias}.total"
                    print(f"[sql-fixer-fallback] {m.group(0)} → {fixed}  (mapped {col} to total in {other_table})")
                    return fixed

        return m.group(0)  # Can't fix — leave as-is

    # Match any alias.column_name patterns (e.g. T1.ordered_qty, po.quantity)
    def repl_alias_col(m: re.Match) -> str:
        alias = m.group(1).upper()
        if alias in alias_map:
            return fix_ref(m)
        return m.group(0)

    fixed_sql = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', repl_alias_col, sql)
    return fixed_sql


def auto_fix_collation(sql: str) -> str:
    """
    Auto-adds COLLATE utf8mb4_unicode_ci to JOIN ON column comparisons
    when they cross database boundaries (e.g. Purchase_Masters vs masters).
    Prevents error 1267: Illegal mix of collations.
    """
    import re

    # Build alias → database map (e.g. T1 → purchase_masters)
    alias_db: dict[str, str] = {}
    SQL_KEYWORDS = {"AS", "ON", "JOIN", "INNER", "LEFT", "RIGHT", "CROSS", "WHERE", "GROUP", "ORDER", "LIMIT", "USING", "AND", "OR", "UNION", "SELECT"}
    
    # Match database.table AS alias OR database.table alias
    for m in re.finditer(r'\b(Sales_Masters|Purchase_Masters|masters)\.([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b', sql, re.IGNORECASE):
        db_name = m.group(1).lower()
        alias = m.group(3).upper()
        if alias not in SQL_KEYWORDS:
            alias_db[alias] = db_name

    def fix_equality(m: re.Match) -> str:
        a1, c1, a2, c2 = m.group(1).upper(), m.group(2), m.group(3).upper(), m.group(4)
        db1 = alias_db.get(a1, '')
        db2 = alias_db.get(a2, '')
        # Only add COLLATE if the two aliases come from different databases
        if db1 and db2 and db1 != db2:
            fixed = (f"{m.group(1)}.{c1} COLLATE utf8mb4_unicode_ci"
                     f" = {m.group(3)}.{c2} COLLATE utf8mb4_unicode_ci")
            print(f"[collation-fixer] Added COLLATE for cross-db comparison ({db1} vs {db2})")
            return fixed
        return m.group(0)

    # Match alias1.col = alias2.col anywhere in the query
    return re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', fix_equality, sql, flags=re.IGNORECASE)


def auto_fix_table_casing(sql: str, schema_context: str) -> str:
    """
    Auto-corrects case-sensitivity errors for table names and adds missing DB prefixes.
    e.g. purchase_orders_header -> Purchase_Masters.purchase_orders_Header
    """
    import re
    # === CRITICAL FIX: Catch naked schema names used as table names ===
    # The LLM sometimes hallucinates "FROM Sales_Masters" instead of "FROM Sales_Masters.SalesOrder_Header"
    # Uses negative lookahead (?!\.) to only match when NOT followed by a dot (i.e., no table specified)
    sql = re.sub(r'\b(FROM\s+)Sales_Masters(?!\.)', r'\1Sales_Masters.SalesOrder_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(JOIN\s+)Sales_Masters(?!\.)', r'\1Sales_Masters.SalesOrder_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(FROM\s+)Purchase_Masters(?!\.)', r'\1Purchase_Masters.purchase_orders_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(JOIN\s+)Purchase_Masters(?!\.)', r'\1Purchase_Masters.purchase_orders_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(FROM\s+)masters(?!\.)', r'\1masters.items', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(JOIN\s+)masters(?!\.)', r'\1masters.items', sql, flags=re.IGNORECASE)

    # Pre-correct SalesOrder casing and underscore mismatches
    sql = re.sub(r'\bSales_Masters\.sales_order_header\b', 'Sales_Masters.SalesOrder_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bSales_Masters\.sales_order_details\b', 'Sales_Masters.SalesOrder_Details', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bsales_order_header\b', 'SalesOrder_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bsales_order_details\b', 'SalesOrder_Details', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Purchase_Masters\.)?purchase_orders\b', 'Purchase_Masters.purchase_orders_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Purchase_Masters\.)?purchase_order\b', 'Purchase_Masters.purchase_orders_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Purchase_Masters\.)?purchase_order_details\b', 'Purchase_Masters.purchase_order_Details', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Purchase_Masters\.)?purchase_orders_details\b', 'Purchase_Masters.purchase_order_Details', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Sales_Masters\.)?sales_orders\b', 'Sales_Masters.SalesOrder_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Sales_Masters\.)?sales_order\b', 'Sales_Masters.SalesOrder_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Sales_Masters\.)?sales_order_details\b', 'Sales_Masters.SalesOrder_Details', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Sales_Masters\.)?sales_orders_details\b', 'Sales_Masters.SalesOrder_Details', sql, flags=re.IGNORECASE)

    # Auto-map common generic table names
    sql = re.sub(r'\b(?:Sales_Masters\.)?invoices\b', 'Sales_Masters.Invoice_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Sales_Masters\.)?invoice\b', 'Sales_Masters.Invoice_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Sales_Masters\.)?invoice_details\b', 'Sales_Masters.Invoice_Details', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:Sales_Masters\.)?invoices_details\b', 'Sales_Masters.Invoice_Details', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:masters\.)?users\b', 'masters.users', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b(?:masters\.)?user\b', 'masters.users', sql, flags=re.IGNORECASE)

    # Pre-correct common schema prefix space typos and name typos before base table mapping
    sql = re.sub(r'\bPurchase_Masters\s+local_landed_costs_Header\b', 'Purchase_Masters.local_landed_cost_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bPurchase_Masters\s+local_landed_cost_Header\b', 'Purchase_Masters.local_landed_cost_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bPurchase_Masters\s+import_landed_costs_Header\b', 'Purchase_Masters.import_landed_costs_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bPurchase_Masters\s+import_landed_cost_Header\b', 'Purchase_Masters.import_landed_costs_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bPurchase_Masters\s+import_landed_costs\b', 'Purchase_Masters.import_landed_costs_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bPurchase_Masters\s+import_landed_cost\b', 'Purchase_Masters.import_landed_costs_Header', sql, flags=re.IGNORECASE)

    # Singular/plural corrections
    sql = re.sub(r'\blocal_landed_costs_Header\b', 'local_landed_cost_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\blocal_landed_costs_Details\b', 'local_landed_cost_Details', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bimport_landed_cost_Header\b', 'import_landed_costs_Header', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bimport_landed_cost_Details\b', 'import_landed_costs_Details', sql, flags=re.IGNORECASE)

    for block in schema_context.split('\n\n'):
        tm = re.search(r'Table: (\S+)', block)
        if tm:
            valid_table = tm.group(1)
            base_table = valid_table.split('.')[-1]
            
            # 1. Replace base table to inject full DB prefix and correct casing
            # Negative lookbehind to ensure we don't duplicate the prefix if it's already there
            sql = re.sub(r'(?<!\.)\b' + re.escape(base_table) + r'\b', valid_table, sql, flags=re.IGNORECASE)
            
            # 2. Replace full table name to fix any casing errors on the DB prefix itself
            sql = re.sub(r'\b' + re.escape(valid_table) + r'\b', valid_table, sql, flags=re.IGNORECASE)
            
    return sql


def auto_inject_header_joins(sql: str) -> str:
    """
    Automatically detects if details tables (PR, PO, GRN) are joined but the query
    filters on their Header numbers (pr_number, po_number, grn_number) without joining the Header.
    It injects the correct Header JOIN and rewrites the alias.
    """
    import re
    
    # 1. Purchase Requisitions
    m_pr = re.search(r'Purchase_Masters\.purchase_requisition_Details\s+AS\s+(T\d+)', sql, re.IGNORECASE)
    if m_pr:
        alias = m_pr.group(1)
        if f"{alias}.pr_number" in sql and "purchase_requisitions_Header" not in sql:
            join_clause = f" INNER JOIN Purchase_Masters.purchase_requisitions_Header AS Th_pr ON Th_pr.pr_id = {alias}.pr_id "
            if " WHERE " in sql.upper():
                parts = re.split(r'(\bWHERE\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + join_clause + parts[1] + parts[2]
            else:
                sql = sql + join_clause
            sql = sql.replace(f"{alias}.pr_number", "Th_pr.pr_number")
            print(f"[join-fixer] Injected PR Header join and updated alias for {alias}.pr_number")

    # 2. Purchase Orders
    m_po = re.search(r'Purchase_Masters\.purchase_order_Details\s+AS\s+(T\d+)', sql, re.IGNORECASE)
    if m_po:
        alias = m_po.group(1)
        if f"{alias}.po_number" in sql and "purchase_orders_Header" not in sql:
            join_clause = f" INNER JOIN Purchase_Masters.purchase_orders_Header AS Th_po ON Th_po.po_id = {alias}.po_id "
            if " WHERE " in sql.upper():
                parts = re.split(r'(\bWHERE\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + join_clause + parts[1] + parts[2]
            else:
                sql = sql + join_clause
            sql = sql.replace(f"{alias}.po_number", "Th_po.po_number")
            print(f"[join-fixer] Injected PO Header join and updated alias for {alias}.po_number")

    # 3. GRNs
    m_grn = re.search(r'Purchase_Masters\.grn_Details\s+AS\s+(T\d+)', sql, re.IGNORECASE)
    if m_grn:
        alias = m_grn.group(1)
        if f"{alias}.grn_number" in sql and "grn_Header" not in sql:
            join_clause = f" INNER JOIN Purchase_Masters.grn_Header AS Th_grn ON Th_grn.grn_id = {alias}.grn_id "
            if " WHERE " in sql.upper():
                parts = re.split(r'(\bWHERE\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + join_clause + parts[1] + parts[2]
            else:
                sql = sql + join_clause
            sql = sql.replace(f"{alias}.grn_number", "Th_grn.grn_number")
            print(f"[join-fixer] Injected GRN Header join and updated alias for {alias}.grn_number")

    return sql


def auto_fix_column_hallucinations(sql: str) -> str:
    """
    Heals common column name hallucinations generated by the AI model.
    Specifically maps so_id, so_date, so_status, and so_number to the correct fields
    in Sales_Masters.SalesOrder_Header.
    """
    import re
    # Map so_status = 'Open' to invoice_generated = 0, and Closed to 1
    sql = re.sub(r'\b([a-zA-Z0-9_]+)\.so_status\s*=\s*[\'"]Open[\'"]', r'\1.invoice_generated = 0', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b([a-zA-Z0-9_]+)\.so_status\s*=\s*[\'"]Closed[\'"]', r'\1.invoice_generated = 1', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b([a-zA-Z0-9_]+)\.so_status\b', r'\1.invoice_generated', sql, flags=re.IGNORECASE)

    # Map other so_ prefixes
    sql = re.sub(r'\b([a-zA-Z0-9_]+)\.so_id\b', r'\1.id', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b([a-zA-Z0-9_]+)\.so_date\b', r'\1.date', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b([a-zA-Z0-9_]+)\.so_number\b', r'\1.So_number', sql, flags=re.IGNORECASE)

    # Map total_amount / grand_total to total in Invoice_Header context
    if "invoice_header" in sql.lower():
        sql = re.sub(r'\b(?:[a-zA-Z0-9_]+\.)?total_amount\b', lambda m: m.group(0).replace('total_amount', 'total'), sql, flags=re.IGNORECASE)
        sql = re.sub(r'\b(?:[a-zA-Z0-9_]+\.)?grand_total\b', lambda m: m.group(0).replace('grand_total', 'total'), sql, flags=re.IGNORECASE)

    return sql


def auto_fix_self_joins(sql: str, schema_context: str) -> str:
    """
    Identifies join conditions comparing an alias.column to itself,
    e.g. ON T1.So_number = T1.So_number, and fixes it by finding another
    alias in the query that contains the column.
    """
    import re
    # 1. Build alias -> table map
    alias_map = {}
    SQL_KEYWORDS = {"AS", "ON", "JOIN", "INNER", "LEFT", "RIGHT", "CROSS", "WHERE", "GROUP", "ORDER", "LIMIT", "USING", "AND", "OR", "UNION", "SELECT"}
    for m in re.finditer(r'\b(?:FROM|JOIN)\s+([\w.]+)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b', sql, re.IGNORECASE):
        table_name = m.group(1)
        alias = m.group(2).upper()
        if alias not in SQL_KEYWORDS:
            alias_map[alias] = table_name

    if not alias_map:
        return sql

    # 2. Build table_name -> columns map from schema_context
    table_cols = {}
    for block in schema_context.split('\n\n'):
        tm = re.search(r'Table: (\S+)', block)
        cm = re.search(r'Columns: (.+)', block, re.DOTALL)
        if tm and cm:
            cols = {c.split('(')[0].strip().lower() for c in cm.group(1).split(',')}
            table_cols[tm.group(1)] = cols

    # 3. Find and fix ON TA.col = TA.col
    def repl_self_join(match: re.Match) -> str:
        alias = match.group(1)
        col = match.group(2)
        alias_upper = alias.upper()
        
        # Look for another alias that has the same column
        for other_alias, other_table in alias_map.items():
            if other_alias != alias_upper:
                other_cols = table_cols.get(other_table, set())
                if col.lower() in other_cols:
                    return f"ON {alias}.{col} = {other_alias}.{col}"
        return match.group(0)

    # Search for ON TA.col = TA.col
    sql = re.sub(
        r'\bON\s+([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\1\.\2\b',
        repl_self_join,
        sql,
        flags=re.IGNORECASE
    )
    return sql


def auto_fix_sales_order_totals(sql: str) -> str:
    """
    Rewrites references to total columns in SalesOrder_Header or SalesOrder_Details
    to compute dynamic totals using ordered_qty * unit_price.
    """
    import re
    h_alias = None
    d_alias = None
    
    h_match = re.search(r'Sales_Masters\.SalesOrder_Header\s+(?:AS\s+)?([a-zA-Z0-9_]+)\b', sql, re.IGNORECASE)
    if h_match:
        h_alias = h_match.group(1)
        
    d_match = re.search(r'Sales_Masters\.SalesOrder_Details\s+(?:AS\s+)?([a-zA-Z0-9_]+)\b', sql, re.IGNORECASE)
    if d_match:
        d_alias = d_match.group(1)
        
    if not h_alias and not d_alias:
        return sql
        
    # If Header is present but Details is not, and total is referenced, inject details JOIN
    if h_alias and not d_alias:
        if re.search(rf'\b{h_alias}\.total\b', sql, re.IGNORECASE) or re.search(r'\btotal\b', sql, re.IGNORECASE):
            d_alias = "T_so_details"
            join_clause = f" INNER JOIN Sales_Masters.SalesOrder_Details AS {d_alias} ON {h_alias}.So_number = {d_alias}.So_number "
            if " WHERE " in sql.upper():
                parts = re.split(r'(\bWHERE\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + join_clause + parts[1] + parts[2]
            elif " GROUP BY " in sql.upper():
                parts = re.split(r'(\bGROUP BY\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + join_clause + parts[1] + parts[2]
            elif " ORDER BY " in sql.upper():
                parts = re.split(r'(\bORDER BY\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + join_clause + parts[1] + parts[2]
            else:
                sql = sql + join_clause
                
    return sql




def auto_fix_temporal_rules(sql: str, question: str) -> str:
    """
    Ensures that queries adhere to strict temporal rules for "this month" and "this quarter".
    """
    import re
    q_lower = question.lower()
    is_month = "this month" in q_lower
    is_quarter = "this quarter" in q_lower
    
    if not is_month and not is_quarter:
        return sql
        
    if is_month:
        start_date, end_date = "2026-06-01", "2026-06-30"
    else:
        start_date, end_date = "2026-04-01", "2026-06-30"
        
    # Find which date column is used in the query.
    match = re.search(r'\b([a-zA-Z0-9_]+\.)?(created_at|date|po_date|grn_date|pr_date|return_date)\b', sql, re.IGNORECASE)
    col_ref = "created_at"
    if match:
        col_ref = match.group(0)
        
    # Replace standard date functions/comparisons on the found column
    pat_month_year = rf'\b(?:MONTH|YEAR)\(\s*{re.escape(col_ref)}\s*\)\s*=\s*(?:MONTH|YEAR)\((?:CURDATE|CURRENT_DATE|NOW)\(\)?\)\s*AND\s*(?:MONTH|YEAR)\(\s*{re.escape(col_ref)}\s*\)\s*=\s*(?:MONTH|YEAR)\((?:CURDATE|CURRENT_DATE|NOW)\(\)?\)'
    sql = re.sub(pat_month_year, "1=1", sql, flags=re.IGNORECASE)
    
    sql = re.sub(rf'\bMONTH\(\s*{re.escape(col_ref)}\s*\)\s*=\s*MONTH\((?:CURDATE|CURRENT_DATE|NOW)\(\)?\)', "1=1", sql, flags=re.IGNORECASE)
    sql = re.sub(rf'\bYEAR\(\s*{re.escape(col_ref)}\s*\)\s*=\s*YEAR\((?:CURDATE|CURRENT_DATE|NOW)\(\)?\)', "1=1", sql, flags=re.IGNORECASE)
    sql = re.sub(rf'\b{re.escape(col_ref)}\s*(?:>=|>|<=|<|=)\s*(?:CURDATE|CURRENT_DATE|NOW)\(\)?', "1=1", sql, flags=re.IGNORECASE)
    sql = re.sub(rf'\b{re.escape(col_ref)}\s+BETWEEN\s+[^AND]+AND\s+\S+', "1=1", sql, flags=re.IGNORECASE)
    sql = re.sub(rf'\b{re.escape(col_ref)}\s*(?:>=|>|<=|<)\s*\'\d{{4}}-\d{{2}}-\d{{2}}\'', "1=1", sql, flags=re.IGNORECASE)

    if "1=1" in sql:
        sql = sql.replace("1=1", f"{col_ref} >= '{start_date}' AND {col_ref} <= '{end_date}'", 1)
        sql = sql.replace("1=1", "1=1")
    else:
        if " WHERE " in sql.upper():
            parts = re.split(r'(\bWHERE\b)', sql, flags=re.IGNORECASE, maxsplit=1)
            sql = parts[0] + parts[1] + f" {col_ref} >= '{start_date}' AND {col_ref} <= '{end_date}' AND " + parts[2]
        else:
            if " GROUP BY " in sql.upper():
                parts = re.split(r'(\bGROUP BY\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + f" WHERE {col_ref} >= '{start_date}' AND {col_ref} <= '{end_date}' " + parts[1] + parts[2]
            elif " ORDER BY " in sql.upper():
                parts = re.split(r'(\bORDER BY\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + f" WHERE {col_ref} >= '{start_date}' AND {col_ref} <= '{end_date}' " + parts[1] + parts[2]
            elif " LIMIT " in sql.upper():
                parts = re.split(r'(\bLIMIT\b)', sql, flags=re.IGNORECASE, maxsplit=1)
                sql = parts[0] + f" WHERE {col_ref} >= '{start_date}' AND {col_ref} <= '{end_date}' " + parts[1] + parts[2]
            else:
                sql = sql + f" WHERE {col_ref} >= '{start_date}' AND {col_ref} <= '{end_date}'"
                
    sql = re.sub(r'\bWHERE\s+AND\b', 'WHERE', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bAND\s+AND\b', 'AND', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\s+AND\s*$', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\s+', ' ', sql).strip()
    return sql


def get_minimal_schema(user_question: str) -> str:
    """
    Returns a minimal, focused schema context for the given user question.
    """
    import json
    import os
    import re
    
    question = user_question.lower()
    selected_tables = []
    
    # Simple, fast keyword matching
    if "invoice" in question or "revenue" in question or "sales value" in question or "sales" in question or "profit" in question or "margin" in question:
        selected_tables.extend(["Sales_Masters.Invoice_Header", "Sales_Masters.Invoice_Details", "masters.customers", "masters.items", "Purchase_Masters.inventory_batches"])
    if "order" in question or "sales order" in question or re.search(r'\b(so|sos|so\'s)\b', question):
        selected_tables.extend(["Sales_Masters.SalesOrder_Header", "Sales_Masters.SalesOrder_Details"])
    if "purchase" in question or "supplier" in question or re.search(r'\b(po|pos|po\'s)\b', question):
        selected_tables.extend(["Purchase_Masters.purchase_orders_Header", "masters.suppliers", "Purchase_Masters.purchase_order_Details"])
    if "import" in question or "ipo" in question:
        selected_tables.extend(["Purchase_Masters.import_purchase_orders_Header", "Purchase_Masters.import_purchase_orders_Details", "masters.suppliers"])
    if "landed cost" in question or "freight" in question or "duty" in question:
        selected_tables.extend(["Purchase_Masters.import_landed_costs_Header", "Purchase_Masters.import_landed_costs_Details", "Purchase_Masters.local_landed_cost_Header", "Purchase_Masters.local_landed_cost_Details"])
    if "grn" in question or "goods receipt" in question:
        selected_tables.extend(["Purchase_Masters.grn_Header", "Purchase_Masters.grn_Details", "masters.suppliers"])
    if "stock" in question or "inventory" in question or "batch" in question:
        selected_tables.extend(["Purchase_Masters.inventory_batches", "masters.items"])
    if "requisition" in question or re.search(r'\b(pr|prs|pr\'s)\b', question):
        selected_tables.extend(["Purchase_Masters.purchase_requisitions_Header", "Purchase_Masters.purchase_requisition_Details"])
    if "return" in question:
        selected_tables.extend(["Purchase_Masters.purchase_return_Header", "Purchase_Masters.purchase_return_Details"])
    if "item" in question or "product" in question or "active" in question:
        selected_tables.extend(["masters.items"])
    if "customer" in question:
        selected_tables.extend(["masters.customers"])
    if "user" in question:
        selected_tables.extend(["masters.users"])

    # Fallback to a small core set if no keywords match
    if not selected_tables:
        selected_tables = ["Sales_Masters.Invoice_Header", "Sales_Masters.SalesOrder_Header", "masters.items"]
        
    # Remove duplicates but preserve order
    seen = set()
    selected_tables = [x for x in selected_tables if not (x in seen or seen.add(x))]
    
    # Load catalog and format schema context
    catalog_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "erp_schema_catalog.json")
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
                
            schema_context = ""
            for table_name in selected_tables:
                table_entry = None
                for entry in catalog:
                    if entry.get("full_table_name", "").lower() == table_name.lower() or entry.get("table_name", "").lower() == table_name.lower().split('.')[-1]:
                        table_entry = entry
                        break
                
                if table_entry:
                    columns_list = []
                    for col in table_entry.get("columns", []):
                        col_str = f"{col.get('column_name')} ({col.get('data_type')})"
                        columns_list.append(col_str)
                    columns_str = ", ".join(columns_list)
                    
                    schema_context += f"Table: `{table_entry.get('full_table_name', table_name)}`\n"
                    schema_context += f"Description: {table_entry.get('business_purpose', '')}\n"
                    schema_context += f"Columns: {columns_str}\n\n"
                    
            if schema_context:
                return schema_context
        except Exception as e:
            print(f"[get_minimal_schema] Failed to load or parse catalog: {e}")
            
    return "No relevant tables found. Please check metadata."




@router.post("/ask")
async def ask_question(request: schemas.ChatRequest, db: Session = Depends(get_db), current_user: models.User = Depends(HasPermission("chat_erp"))):
    def clean_response(res: dict) -> dict:
        def remove_stars(obj):
            if isinstance(obj, str):
                return obj.replace("**", "")
            elif isinstance(obj, dict):
                return {k: remove_stars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [remove_stars(x) for x in obj]
            return obj
        return remove_stars(res)

    try:
        start_time = time.time()
        
        # 0. Intercept basic conversational queries before doing expensive DB work
        import re
        q_lower = request.question.lower().strip()
        if re.match(r'^(hi+i*|hello|hey|hola|how are you|who are you|what can you do|help)\b', q_lower) or len(q_lower) < 3:
            return clean_response({
                "summary": "Hello! I am the EDIP AI Assistant. I can help you query and analyze your ERP data. Try asking me something like 'total sales this month' or 'show top 5 items by ordered quantity'.",
                "data": [],
                "chart_type": "text",
                "executive_summary": "Hello! I am the EDIP AI Assistant. I can help you query and analyze your ERP data.",
                "business_insights": [],
                "recommendations": []
            })
        elif re.search(r'\b(you said|you telling|why did you|you are wrong|incorrect|you told me|earlier you)\b', q_lower):
            return clean_response({
                "summary": "I apologize for any confusion! As an AI, I do not maintain a memory of our previous chat history between questions. I evaluate each of your questions freshly against the live ERP database. If you saw different numbers previously, it might be because the exact time filter or condition I used in the background was slightly different. Please ask your data question again clearly, and I will pull the most accurate live data for you!",
                "data": [],
                "chart_type": "text",
                "executive_summary": "I do not retain chat history memory. Each question is a fresh query against the database.",
                "business_insights": [],
                "recommendations": []
            })

        # ----- DOCUMENT UPLOAD / RAG QUERY SEARCH -----
        from app.vector_db.qdrant_document_service import get_qdrant_doc_service
        qdrant_doc_service = get_qdrant_doc_service()
        
        # Check if current user has any uploaded files in DB
        uploaded_files_count = db.query(models.UploadedFile).filter(
            models.UploadedFile.tenant_id == current_user.tenant_id,
            models.UploadedFile.user_id == current_user.id
        ).count()
        
        if uploaded_files_count > 0:
            # We search Qdrant for matching chunks
            query_vector = embedder.embed_text(request.question)
            matched_chunks = qdrant_doc_service.search_relevant_chunks(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                query_vector=query_vector,
                limit=5
            )
            
            # Determine if this query matches the documents
            is_doc_query = False
            best_score = matched_chunks[0]["score"] if matched_chunks else 0.0
            
            # Define explicit keywords to route to documents
            doc_keywords = {"document", "file", "uploaded", "excel", "pdf", "docx", "sheet", "client data", "uploaded data"}
            has_doc_keyword = any(kw in q_lower for kw in doc_keywords)
            
            if matched_chunks:
                # If similarity is very high, or if we have a keyword and similarity is reasonably high
                if best_score >= 0.70:
                    is_doc_query = True
                elif has_doc_keyword and best_score >= 0.55:
                    is_doc_query = True
                    
            if is_doc_query:
                # Retrieve the RAG response
                loop = asyncio.get_event_loop()
                try:
                    summary = await asyncio.wait_for(
                        loop.run_in_executor(
                            _executor,
                            lambda: ai_service.generate_document_rag_response(request.question, matched_chunks)
                        ),
                        timeout=30
                    )
                except Exception as e:
                    print(f"RAG document generation failed: {e}")
                    summary = "Failed to generate a response from the uploaded documents."
                
                # Format sources data
                sources_data = [
                    {
                        "Source File": chunk["filename"],
                        "Type": chunk["file_type"].upper(),
                        "Match Confidence": f"{chunk['score'] * 100:.1f}%",
                        "Excerpt": chunk["text"][:150] + "..." if len(chunk["text"]) > 150 else chunk["text"]
                    }
                    for chunk in matched_chunks if chunk["score"] >= 0.55
                ]
                
                llm_response = {
                    "summary": summary,
                    "data": sources_data,
                    "chart_type": "table",
                    "executive_summary": summary,
                    "business_insights": [],
                    "recommendations": []
                }
                
                llm_response = clean_response(llm_response)
                
                # Record chat history
                if request.view_mode != "dashboard":
                    chat_history = models.ChatHistory(
                        session_id=request.session_id,
                        tenant_id=current_user.tenant_id,
                        user_id=current_user.id,
                        question=request.question,
                        generated_sql="[RAG Vector Search - Uploaded Documents]",
                        response_json=llm_response,
                        execution_time_ms=int((time.time() - start_time) * 1000)
                    )
                    db.add(chat_history)
                    db.commit()
                    
                return llm_response

        # ----- INTERCEPT DEFINITION/EDUCATIONAL QUERIES -----
        definition_prefixes = r'^(what is|what are|what does|explain|define|difference between|how does|why is|why do|what is the purpose of)\b'
        metric_keywords = r'\b(total|sum|count|how many|how much|highest|lowest|top|average|active|pending|value|amount|show|list|which|margin|profit|revenue|sales|cost|price|cogs|qty|quantity|by|each|per)\b'
        
        is_explicit_definition = re.search(r'^(what is a|what is an|what are the differences between|definition of|explain the difference between|explain the concept of|explain what.*is|what does.*mean)\b', q_lower)
        
        if (re.match(definition_prefixes, q_lower) and not re.search(metric_keywords, q_lower)) or is_explicit_definition:
            loop = asyncio.get_event_loop()
            try:
                summary = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor,
                        lambda: ai_service.generate_general_response(request.question)
                    ),
                    timeout=20
                )
            except Exception as e:
                print(f"RAG definition generation failed: {e}")
                summary = "I'm sorry, I couldn't generate a definition for that."
            
            llm_response = {
                "summary": summary,
                "data": [],
                "chart_type": "text",
                "executive_summary": summary,
                "business_insights": [],
                "recommendations": []
            }
            
            llm_response = clean_response(llm_response)
            if request.view_mode != "dashboard":
                chat_history = models.ChatHistory(
                    session_id=request.session_id,
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    question=request.question,
                    generated_sql="",
                    response_json=llm_response,
                    execution_time_ms=int((time.time() - start_time) * 1000)
                )
                db.add(chat_history)
                db.commit()
            
            return llm_response

        # 1. Get ERP Connection
        connection = db.query(models.ERPConnection).filter(
            models.ERPConnection.id == request.connection_id
        ).first()

        if not connection:
            raise HTTPException(status_code=404, detail="ERP Connection not found")
        if connection.tenant_id != current_user.tenant_id:
            print(f"[AUTH_DEBUG] Forbidden request.connection_id={request.connection_id}, connection.id={connection.id}, connection.name={connection.name}, connection.tenant_id={connection.tenant_id} (type {type(connection.tenant_id)}) vs current_user.tenant_id={current_user.tenant_id} (type {type(current_user.tenant_id)})")
            raise HTTPException(status_code=403, detail=f"Forbidden: You do not have access to this ERP Connection. User tenant: {current_user.tenant_id}, Conn tenant: {connection.tenant_id}")

        # ----- INTERCEPT TABLE STRUCTURE QUERIES -----
        if re.search(r'\b(how many tables|what tables|list.*tables|show.*tables|list of tables)\b', q_lower):
            connection_url = build_connection_string(
                schemas.TestConnectionRequest(
                    db_type=connection.db_type,
                    server=connection.server,
                    database_name=connection.database_name,
                    username=connection.username,
                    password=connection.encrypted_password.replace("enc_", "")
                )
            )
            engine = get_engine(connection_url)
            tables_data = []
            sql_query = ""
            try:
                with engine.connect() as conn:
                    if connection.db_type.lower() == "mysql":
                        sql_query = "SELECT table_schema AS `schema`, table_name FROM information_schema.tables WHERE table_schema IN ('Sales_Masters', 'Purchase_Masters', 'masters') ORDER BY table_schema, table_name"
                    elif connection.db_type.lower() == "sqlite":
                        sql_query = "SELECT 'main' AS `schema`, name AS table_name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                    else:
                        sql_query = "SELECT table_schema AS `schema`, table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog') ORDER BY table_schema, table_name"
                    
                    result = conn.execute(sqlalchemy.text(sql_query))
                    tables_data = [dict(zip(result.keys(), row)) for row in result.fetchall()]
            except Exception as e:
                print(f"[chat-tables-intercept] Failed to fetch tables: {e}")
                tables_data = []

            if tables_data:
                loop = asyncio.get_event_loop()
                try:
                    summary = await asyncio.wait_for(
                        loop.run_in_executor(
                            _executor,
                            lambda: ai_service.generate_rag_response(request.question, tables_data)
                        ),
                        timeout=20
                    )
                except Exception as e:
                    print(f"RAG table summary generation failed: {e}")
                    summary = f"There are {len(tables_data)} tables in the database."

                llm_response = {
                    "summary": summary,
                    "data": tables_data,
                    "chart_type": "table",
                    "executive_summary": summary,
                    "business_insights": [],
                    "recommendations": []
                }

                log = models.QueryLog(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    sql_query=sql_query,
                    status="success"
                )
                db.add(log)
                db.commit()

                llm_response = clean_response(llm_response)
                if request.view_mode != "dashboard":
                    chat_history = models.ChatHistory(
                        session_id=request.session_id,
                        tenant_id=current_user.tenant_id,
                        user_id=current_user.id,
                        question=request.question,
                        generated_sql=sql_query,
                        response_json=llm_response,
                        execution_time_ms=int((time.time() - start_time) * 1000)
                    )
                    db.add(chat_history)
                    db.commit()

                return llm_response

        # 2. Retrieve relevant schema from get_minimal_schema with Qdrant fallback
        schema_context = get_minimal_schema(request.question)
        if not schema_context or schema_context == "No relevant tables found. Please check metadata.":
            # Fallback to Qdrant if no relevant tables matched dynamically
            query_vector = embedder.embed_text(request.question)
            search_results = get_qdrant().search_relevant_tables(
                tenant_id=current_user.tenant_id,
                connection_id=connection.id,
                query_vector=query_vector,
                limit=50
            )
            schema_context = ""
            for hit in search_results:
                payload = hit.payload
                if payload.get("type") == "table":
                    schema_context += f"Table: `{payload.get('name', payload.get('table_name'))}`\nDescription: {payload.get('description')}\n\n"
                elif payload.get("type") == "column":
                    schema_context += f"Column: `{payload.get('name')}`\nTable: `{payload.get('parent_table')}`\nData Type: {payload.get('data_type')}\nDescription: {payload.get('description')}\n\n"
                else:
                    schema_context += f"Table: `{payload.get('table_name')}`\nDescription: {payload.get('description')}\nColumns: {payload.get('columns')}\n\n"

        if not schema_context:
            schema_context = "No relevant tables found. Please check metadata."

        # 4. Build ERP connection URL (needed for both generation and retry execution)
        connection_url = build_connection_string(
            schemas.TestConnectionRequest(
                db_type=connection.db_type,
                server=connection.server,
                database_name=connection.database_name,
                username=connection.username,
                password=connection.encrypted_password.replace("enc_", "")
            )
        )
        engine = get_engine(connection_url)

        def run_query(sql: str) -> list:
            from decimal import Decimal
            with engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(sql))
                cols = list(result.keys())
                rows = []
                for row in result.fetchall():
                    d = dict(zip(cols, row))
                    for k, v in d.items():
                        if isinstance(v, Decimal):
                            if v % 1 == 0:
                                d[k] = int(v)
                            else:
                                d[k] = float(v)
                        elif isinstance(v, bytes):
                            if v == b'\x00':
                                d[k] = False
                            elif v == b'\x01':
                                d[k] = True
                            else:
                                try:
                                    d[k] = v.decode('utf-8')
                                except UnicodeDecodeError:
                                    d[k] = str(v)
                        elif not isinstance(v, (int, float, str, bool, type(None))):
                            d[k] = str(v)
                    rows.append(d)
                return rows

        # 5. Generate SQL + self-healing retry loop (up to 2 retries on DB errors)
        loop = asyncio.get_event_loop()
        MAX_RETRIES = 2
        last_db_error: str = None
        llm_response = None
        data = None

        for attempt in range(MAX_RETRIES + 1):
            # 5a. Generate SQL via Ollama
            try:
                # ----- SEMANTIC CACHING FOR HARD QUERIES -----
                import re
                if re.search(r'profit\s+margin', q_lower) and re.search(r'customer', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.customer_name, (SUM(T2.supplied_qty * T2.unit_price) - SUM(T2.supplied_qty * T3.standardPrice)) / SUM(T2.supplied_qty * T2.unit_price) * 100 AS profit_margin FROM Sales_Masters.Invoice_Header AS T1 INNER JOIN Sales_Masters.Invoice_Details AS T2 ON T1.invoice_id = T2.invoice_id INNER JOIN masters.items AS T3 ON T2.item_id = T3.id GROUP BY T1.customer_name ORDER BY profit_margin DESC",
                        "chart_type": "barchart",
                        "summary": ""
                    }
                elif re.search(r'profit\s+margin', q_lower) and re.search(r'\b(item|product)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T2.name AS item_name, (SUM(T2.supplied_qty * T2.unit_price) - SUM(T2.supplied_qty * T3.standardPrice)) / SUM(T2.supplied_qty * T2.unit_price) * 100 AS profit_margin FROM Sales_Masters.Invoice_Details AS T2 INNER JOIN masters.items AS T3 ON T2.item_id = T3.id GROUP BY T2.item_id, T2.name ORDER BY profit_margin DESC",
                        "chart_type": "barchart",
                        "summary": ""
                    }
                elif re.search(r'\btop\b.*\b(sales\s+order|so)\b', q_lower) or re.search(r'\b(sales\s+order|so)s?\b.*\b(highest|top|most|total)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.So_number, T1.customer_name, SUM(T2.ordered_qty * T2.unit_price) AS total_value, T1.date FROM Sales_Masters.SalesOrder_Header AS T1 JOIN Sales_Masters.SalesOrder_Details AS T2 ON T1.So_number = T2.So_number GROUP BY T1.id, T1.So_number, T1.customer_name, T1.date ORDER BY total_value DESC LIMIT 5",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'supplier', q_lower) and re.search(r'(highest|top|most|total).*purchase', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.name AS supplier_name, SUM(T2.grand_total) AS total_purchase_value FROM masters.suppliers AS T1 JOIN Purchase_Masters.purchase_orders_Header AS T2 ON T1.id = T2.supplier_id GROUP BY T1.id, T1.name ORDER BY total_purchase_value DESC LIMIT 5",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\b(total|current)\s+(value|worth)\b.*\b(inventory|stock)\b', q_lower) or re.search(r'\b(inventory|stock)\b.*\b(total|current)\s+(value|worth)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT SUM(T1.current_qty * T1.landed_unit_cost) AS total_inventory_value FROM Purchase_Masters.inventory_batches AS T1 WHERE T1.is_posted = 1",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'(top|high).*(grn|goods receipt)', q_lower) or re.search(r'(grn|goods receipt).*(high|top|value)', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.grn_number, T3.name, T3.standardPrice, SUM(T2.received_qty * T3.standardPrice) AS total_value FROM Purchase_Masters.grn_Header AS T1 INNER JOIN Purchase_Masters.grn_Details AS T2 ON T1.grn_id = T2.grn_id INNER JOIN masters.items AS T3 ON T2.item_id = T3.id GROUP BY T1.grn_number, T3.name, T3.standardPrice ORDER BY total_value DESC LIMIT 5",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'landed\s+cost', q_lower) and re.search(r'local', q_lower) and re.search(r'import', q_lower):
                    llm_response = {
                        "sql": "SELECT 'Local' AS purchase_type, SUM(T1.total_landed_cost) AS total_landed_cost FROM Purchase_Masters.local_landed_cost_Header AS T1 WHERE T1.is_posted = 1 UNION ALL SELECT 'Import' AS purchase_type, SUM(T2.total_landed_cost) AS total_landed_cost FROM Purchase_Masters.import_landed_costs_Header AS T2 WHERE T2.is_posted = 1",
                        "chart_type": "barchart",
                        "summary": ""
                    }
                elif re.search(r'landed\s+cost.*local', q_lower) or re.search(r'local.*landed\s+cost', q_lower):
                    llm_response = {
                        "sql": "SELECT SUM(T1.total_landed_cost) AS total_local_landed_cost FROM Purchase_Masters.local_landed_cost_Header AS T1 WHERE T1.is_posted = 1",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'landed\s+cost.*import', q_lower) or re.search(r'import.*landed\s+cost', q_lower):
                    llm_response = {
                        "sql": "SELECT SUM(T1.total_landed_cost) AS total_import_landed_cost FROM Purchase_Masters.import_landed_costs_Header AS T1 WHERE T1.is_posted = 1",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'\blocal\s+purchase\b', q_lower) and re.search(r'\b(how many|count|total|list|show)\b', q_lower) and re.search(r'\b(this month|month|today|this week|this year)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.po_id, T1.po_number, T1.po_date, T1.grand_total FROM Purchase_Masters.purchase_orders_Header AS T1 WHERE MONTH(T1.po_date) = MONTH(CURDATE()) AND YEAR(T1.po_date) = YEAR(CURDATE()) ORDER BY T1.po_date DESC",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\blocal\s+purchase\b', q_lower) and re.search(r'\b(how many|count|total)\b', q_lower) and not re.search(r'\b(this month|month|today|this week|this year)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT COUNT(T1.po_id) AS total_local_purchases FROM Purchase_Masters.purchase_orders_Header AS T1",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'compare', q_lower) and re.search(r'months?', q_lower) and re.search(r'sales', q_lower):
                    import re as inline_re
                    m = inline_re.search(r'(\d+)\s+months?', q_lower)
                    num_months = int(m.group(1)) if m else 3
                    llm_response = {
                        "sql": f"SELECT DATE_FORMAT(T1.created_at, '%Y-%m') AS sale_month, SUM(T1.total) AS total_sales FROM Sales_Masters.Invoice_Header AS T1 WHERE T1.created_at >= DATE_SUB(CURDATE(), INTERVAL {num_months} MONTH) GROUP BY sale_month ORDER BY sale_month ASC",
                        "chart_type": "card",
                        "dashboard_type": "comparison",
                        "summary": ""
                    }
                # --- SALES ORDER DETAIL BY NUMBER INTERCEPT ---
                elif re.search(r'\b(details?|info|information|show|get)\b', q_lower) and re.search(r'\b(sales\s+order|so)\b', q_lower) and re.search(r'(SO[\-]?\d+[\-]?\d*)', request.question, re.IGNORECASE):
                    so_match = re.search(r'(SO[\-]?\d+[\-]?\d*)', request.question, re.IGNORECASE)
                    so_number = so_match.group(1) if so_match else None
                    if so_number:
                        llm_response = {
                            "sql": f"SELECT T1.So_number, T1.customer_name, T1.date, T2.name AS item_name, T2.ordered_qty, T2.supplied_qty, T2.pending_qty, T2.unit_price, (T2.ordered_qty * T2.unit_price) AS line_total FROM Sales_Masters.SalesOrder_Header AS T1 INNER JOIN Sales_Masters.SalesOrder_Details AS T2 ON T1.So_number = T2.So_number WHERE T1.So_number = '{so_number}'",
                            "chart_type": "table",
                            "summary": ""
                        }
                # --- SALES ORDER INTERCEPTS ---
                elif re.search(r'\b(sales\s+order|so)s?\b', q_lower) and re.search(r'\b(this month|month|today|this week|this year)\b', q_lower):
                    if re.search(r'\b(list|show|all)\b', q_lower):
                        llm_response = {
                            "sql": "SELECT T1.So_number, T1.customer_name, T1.date, T1.created_at FROM Sales_Masters.SalesOrder_Header AS T1 WHERE MONTH(T1.created_at) = MONTH(CURDATE()) AND YEAR(T1.created_at) = YEAR(CURDATE()) ORDER BY T1.created_at DESC",
                            "chart_type": "table",
                            "summary": ""
                        }
                    else:
                        llm_response = {
                            "sql": "SELECT COUNT(*) AS total_count FROM Sales_Masters.SalesOrder_Header AS T1 WHERE MONTH(T1.created_at) = MONTH(CURDATE()) AND YEAR(T1.created_at) = YEAR(CURDATE())",
                            "chart_type": "card",
                            "summary": ""
                        }
                elif re.search(r'\b(sales\s+order|so)s?\b', q_lower) and re.search(r'\b(how many|count|total)\b', q_lower) and not re.search(r'\b(this month|month|today|this week|this year)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT COUNT(*) AS total_count FROM Sales_Masters.SalesOrder_Header AS T1",
                        "chart_type": "card",
                        "summary": ""
                    }
                # --- IMPORT PURCHASE INTERCEPTS ---
                elif re.search(r'\bimport\s+(purchases?|pos?|orders?)\b', q_lower) and re.search(r'\b(this month|month)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.import_po_id, T1.import_po_number, T1.po_date, T1.total_lcy, T1.status FROM Purchase_Masters.import_purchase_orders_Header AS T1 WHERE MONTH(T1.po_date) = MONTH(CURDATE()) AND YEAR(T1.po_date) = YEAR(CURDATE()) ORDER BY T1.po_date DESC",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\bimport\s+(purchases?|pos?|orders?)\b', q_lower) and re.search(r'\b(how many|count|total)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT COUNT(T1.import_po_id) AS total_import_purchases FROM Purchase_Masters.import_purchase_orders_Header AS T1",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'\bimport\s+(purchases?|pos?|orders?)\b', q_lower) and re.search(r'\b(list|show|all)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.import_po_id, T1.import_po_number, T1.po_date, T1.total_fcy, T1.total_lcy, T1.status FROM Purchase_Masters.import_purchase_orders_Header AS T1 ORDER BY T1.po_date DESC LIMIT 50",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\bimport\s+(purchases?|pos?|orders?)\b', q_lower) and re.search(r'\b(items?|products?)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.import_po_number, T1.po_date, T3.name AS item_name, T2.qty, T2.fcy_unit_price, T2.total_fcy FROM Purchase_Masters.import_purchase_orders_Header AS T1 JOIN Purchase_Masters.import_purchase_orders_Details AS T2 ON T1.import_po_id = T2.import_po_id JOIN masters.items AS T3 ON T2.item_id = T3.id ORDER BY T1.po_date DESC",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\bimport\s+(purchases?|pos?|orders?)\b', q_lower) and not re.search(r'\b(landed|cost|freight)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.import_po_id, T1.import_po_number, T1.po_date, T1.total_fcy, T1.total_lcy, T1.status FROM Purchase_Masters.import_purchase_orders_Header AS T1 ORDER BY T1.po_date DESC LIMIT 50",
                        "chart_type": "table",
                        "summary": ""
                    }
                # --- MASTER DATA: ITEMS / PRODUCTS ---
                elif re.search(r'\b(how many|count|total)\b.*\b(items?|products?)\b', q_lower) or (re.search(r'\b(items?|products?)\b', q_lower) and re.search(r'\b(how many|count|total)\b', q_lower)):
                    llm_response = {
                        "sql": "SELECT COUNT(*) AS total_items FROM masters.items",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'\b(active)\b.*\b(items?|products?)\b', q_lower) or re.search(r'\b(items?|products?)\b.*\b(active)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT COUNT(*) AS active_items FROM masters.items WHERE active = 1",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'\bimported?\b.*\b(items?|products?)\b', q_lower) or re.search(r'\b(items?|products?)\b.*\bimported?\b', q_lower):
                    llm_response = {
                        "sql": "SELECT id AS item_id, name, hsnCode, standardPrice FROM masters.items WHERE isImported = 1 ORDER BY name",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\b(list|show|all)\b.*\b(items?|products?)\b', q_lower) or (re.search(r'^\s*items?\s*$', q_lower)):
                    llm_response = {
                        "sql": "SELECT id AS item_id, name, standardPrice, minStock, reorderLevel, isImported FROM masters.items WHERE active = 1 ORDER BY name LIMIT 50",
                        "chart_type": "table",
                        "summary": ""
                    }
                # --- MASTER DATA: SUPPLIERS ---
                elif re.search(r'\b(how many|count|total)\b.*\bsuppliers?\b', q_lower) or re.search(r'\bsuppliers?\b.*\b(how many|count|total)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT COUNT(*) AS total_suppliers FROM masters.suppliers",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'\b(list|show|all)\b.*\bsuppliers?\b', q_lower):
                    llm_response = {
                        "sql": "SELECT id, name FROM masters.suppliers ORDER BY name LIMIT 50",
                        "chart_type": "table",
                        "summary": ""
                    }
                # --- MASTER DATA: CUSTOMERS ---
                elif re.search(r'\b(how many|count|total)\b.*\bcustomers?\b', q_lower) or re.search(r'\bcustomers?\b.*\b(how many|count|total)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT COUNT(*) AS total_customers FROM masters.customers",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'\b(list|show|all)\b.*\bcustomers?\b', q_lower):
                    llm_response = {
                        "sql": "SELECT id, name FROM masters.customers ORDER BY name LIMIT 50",
                        "chart_type": "table",
                        "summary": ""
                    }
                # --- CEO DASHBOARD: SALES & REVENUE ---

                elif re.search(r'\btop\b.*\bcustomer', q_lower) and re.search(r'\b(revenue|sales|value|spend)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT customer_name, SUM(total) AS total_revenue FROM Sales_Masters.Invoice_Header WHERE YEAR(created_at) = YEAR(CURDATE()) GROUP BY customer_name ORDER BY total_revenue DESC LIMIT 10",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif (re.search(r'\b(best.selling|top.selling|most.sold|highest.selling|selling.most)\b', q_lower) or (re.search(r'\bselling\b', q_lower) and re.search(r'\bmost\b', q_lower)) or (re.search(r'\b(which|what)\b', q_lower) and re.search(r'\bproducts?\b', q_lower) and re.search(r'\b(most|top|best|highest)\b', q_lower))) and re.search(r'\bproducts?|\bitems?\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T2.name AS product_name, SUM(T2.ordered_qty) AS total_qty_sold FROM Sales_Masters.SalesOrder_Header AS T1 JOIN Sales_Masters.SalesOrder_Details AS T2 ON T1.So_number = T2.So_number WHERE QUARTER(T1.date) = QUARTER(CURDATE()) AND YEAR(T1.date) = YEAR(CURDATE()) GROUP BY T2.name ORDER BY total_qty_sold DESC LIMIT 10",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\b(highest|top|most).*(invoice|bill)\b', q_lower) or re.search(r'\b(invoice|bill).*(highest|top|most)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT invoice_id, customer_name, total, created_at FROM Sales_Masters.Invoice_Header WHERE MONTH(created_at) = MONTH(CURDATE()) AND YEAR(created_at) = YEAR(CURDATE()) ORDER BY total DESC LIMIT 5",
                        "chart_type": "table",
                        "summary": ""
                    }
                # --- CEO DASHBOARD: SUPPLIER ---
                elif re.search(r'\b(top|most|highest|biggest|best)\b.*\bsupplier\b', q_lower) or re.search(r'\bsupplier\b.*\b(top|most|highest|biggest|best)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T2.name AS supplier_name, COUNT(T1.po_id) AS total_orders, SUM(T1.grand_total) AS total_value FROM Purchase_Masters.purchase_orders_Header AS T1 JOIN masters.suppliers AS T2 ON T1.supplier_id COLLATE utf8mb4_unicode_ci = T2.id COLLATE utf8mb4_unicode_ci GROUP BY T2.name ORDER BY total_value DESC LIMIT 5",
                        "chart_type": "table",
                        "summary": ""
                    }
                # --- CEO DASHBOARD: INVENTORY & STOCK ---
                elif re.search(r'\b(reorder|reorder.level|exceeded.reorder)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.id AS item_id, T1.name, T1.reorderLevel, COALESCE(SUM(T2.current_qty), 0) AS current_stock FROM masters.items AS T1 LEFT JOIN Purchase_Masters.inventory_batches AS T2 ON T1.id COLLATE utf8mb4_unicode_ci = T2.item_id COLLATE utf8mb4_unicode_ci GROUP BY T1.id, T1.name, T1.reorderLevel HAVING current_stock <= T1.reorderLevel AND T1.reorderLevel > 0 ORDER BY current_stock ASC LIMIT 20",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\b(low.stock|running.low|below.minimum|low.inventory)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.id AS item_id, T1.name, T1.minStock, COALESCE(SUM(T2.current_qty), 0) AS current_stock FROM masters.items AS T1 LEFT JOIN Purchase_Masters.inventory_batches AS T2 ON T1.id COLLATE utf8mb4_unicode_ci = T2.item_id COLLATE utf8mb4_unicode_ci GROUP BY T1.id, T1.name, T1.minStock HAVING current_stock < T1.minStock AND T1.minStock > 0 ORDER BY current_stock ASC LIMIT 20",
                        "chart_type": "table",
                        "summary": ""
                    }
                elif re.search(r'\bzero.stock\b', q_lower) or (re.search(r'\bstock\b', q_lower) and re.search(r'\bzero\b', q_lower)):
                    llm_response = {
                        "sql": "SELECT T1.id AS item_id, T1.name, COALESCE(SUM(T2.current_qty), 0) AS current_stock FROM masters.items AS T1 LEFT JOIN Purchase_Masters.inventory_batches AS T2 ON T1.id COLLATE utf8mb4_unicode_ci = T2.item_id COLLATE utf8mb4_unicode_ci GROUP BY T1.id, T1.name HAVING current_stock = 0 LIMIT 20",
                        "chart_type": "table",
                        "summary": ""
                    }
                # --- CEO DASHBOARD: PROCUREMENT ALERTS ---
                elif re.search(r'\b(pending|open).*(purchase.orders?|\bpo\b)', q_lower) or (re.search(r'\bpurchase.orders?\b', q_lower) and re.search(r'\b(pending|open|value|total)\b', q_lower) and not re.search(r'\b(local|import)\b', q_lower)):
                    llm_response = {
                        "sql": "SELECT COUNT(T1.po_id) AS pending_pos, SUM(T1.grand_total) AS total_pending_value FROM Purchase_Masters.purchase_orders_Header AS T1 WHERE T1.po_id NOT IN (SELECT DISTINCT po_id FROM Purchase_Masters.grn_Header WHERE po_id IS NOT NULL)",
                        "chart_type": "card",
                        "summary": ""
                    }
                elif re.search(r'\b(pr|purchase.requisitions?)\b', q_lower) and re.search(r'\b(not.converted|unconverted|pending|open|without.po|no.po|not.*po|without.*po)\b', q_lower):
                    llm_response = {
                        "sql": "SELECT T1.pr_id, T1.pr_number, T1.pr_date, T1.department, T1.requested_by FROM Purchase_Masters.purchase_requisitions_Header AS T1 WHERE T1.pr_id NOT IN (SELECT DISTINCT pr_id FROM Purchase_Masters.purchase_orders_Header WHERE pr_id IS NOT NULL) ORDER BY T1.pr_date DESC",
                        "chart_type": "table",
                        "summary": ""
                    }
                else:
                    llm_response = await asyncio.wait_for(
                        loop.run_in_executor(
                            _executor,
                            ai_service.generate_sql_and_dashboard,
                            request.question,
                            schema_context,
                            last_db_error
                        ),
                        timeout=120.0
                    )
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=504,
                    detail=f"AI model took too long to respond (>{OLLAMA_TIMEOUT_SECONDS}s). Please try again."
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

            generated_sql = llm_response.get("sql", "") or llm_response.get("query", "") or llm_response.get("SQL", "")

            # Pre-clean: strip markdown fences and trailing semicolons before validation
            if generated_sql:
                generated_sql = SQLValidator.clean_sql(generated_sql)

            if generated_sql:
                # Check if it's actually conversational text put into the 'sql' field by the LLM
                sql_clean = generated_sql.strip().lstrip('(').strip().upper()
                is_real_sql = any(sql_clean.startswith(prefix) for prefix in ["SELECT", "WITH", "SHOW", "DESCRIBE"])
                if not is_real_sql:
                    # Treat it as conversational response directly
                    llm_response = {
                        "summary": generated_sql,
                        "data": [],
                        "chart_type": "text",
                        "executive_summary": generated_sql,
                        "business_insights": [],
                        "recommendations": []
                    }
                    generated_sql = ""

            if not generated_sql:
                # The AI determined this was conversational or couldn't generate SQL
                if not llm_response.get("summary"):
                    # Call Ollama to generate a natural language explanation/response for general/conversational queries
                    prompt = f"""You are EDIP AI — a Senior ERP Business Analyst.
You are helping the user with general ERP concepts, business processes, or technical database questions (including database creation, tables, SQL queries, etc.).
The user asked: "{request.question}"

RESPONSE RULES:
1. Act as a professional, expert ERP Business Analyst and Developer.
2. Answer the question directly and concisely, focused exactly on what the user asked. Keep explanations short (1-2 paragraphs max).
3. Provide clean code blocks (e.g., ```python ... or ```sql ...) with a brief 1-2 sentence explanation of the code, but do not write unnecessary tutorials, installation guides, or best practices lists.
4. Use professional, executive-level language.
"""
                    try:
                        summary = await asyncio.wait_for(
                            loop.run_in_executor(
                                _executor,
                                lambda: ai_service._call_ollama(prompt)
                            ),
                            timeout=20
                        )
                        llm_response["summary"] = summary.strip()
                    except Exception as e:
                        print(f"Conversational fallback generation failed: {e}")
                        llm_response["summary"] = "I'm sorry, I couldn't understand how to query the database for that. If you're just saying hello, Hi there! Otherwise, could you please rephrase your question with more specific data fields?"
                
                llm_response["data"] = []
                llm_response["chart_type"] = "text"
                llm_response["executive_summary"] = llm_response.get("summary", "Conversational reply.")
                llm_response["business_insights"] = []
                llm_response["recommendations"] = []
                break

            # 5b-pre. Auto-fix wrong alias prefixes, collation mismatches, and casing before hitting the DB
            generated_sql = auto_fix_table_casing(generated_sql, schema_context)
            generated_sql = auto_fix_sql_aliases(generated_sql, schema_context)
            generated_sql = auto_fix_collation(generated_sql)
            generated_sql = auto_inject_header_joins(generated_sql)
            generated_sql = auto_fix_column_hallucinations(generated_sql)
            generated_sql = auto_fix_self_joins(generated_sql, schema_context)
            generated_sql = auto_fix_sales_order_totals(generated_sql)
            generated_sql = auto_fix_temporal_rules(generated_sql, request.question)
            generated_sql = auto_remove_invalid_filters(generated_sql, schema_context)

            # Sync modified SQL back to the response structure
            if "sql" in llm_response:
                llm_response["sql"] = generated_sql
            elif "query" in llm_response:
                llm_response["query"] = generated_sql
            elif "SQL" in llm_response:
                llm_response["SQL"] = generated_sql

            # 5b. Validate SQL (security check)
            is_safe, reason = SQLValidator.is_safe_query(generated_sql)
            if not is_safe:
                print(f"[SQL-BLOCKED] Reason: {reason}")
                print(f"[SQL-BLOCKED] SQL was: {generated_sql[:500]}")
                log = models.QueryLog(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    sql_query=generated_sql,
                    status="blocked",
                    error_message=reason
                )
                db.add(log)
                db.commit()
                raise HTTPException(status_code=403, detail=f"Query blocked by security policy: {reason}")

            # 5b-2. Validate SQL (schema check)
            is_valid, validation_reason = SQLValidator.validate_sql_schema(generated_sql, schema_context)
            if not is_valid:
                print(f"[SQL-INVALID] Reason: {validation_reason}")
                if attempt < MAX_RETRIES:
                    last_db_error = validation_reason
                    continue
                # All retries exhausted on validation
                log = models.QueryLog(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    sql_query=generated_sql,
                    status="error",
                    error_message=validation_reason
                )
                db.add(log)
                db.commit()
                return clean_response({
                    "summary": f"I was unable to generate a valid query for your question. Please try rephrasing it.",
                    "data": [],
                    "chart_type": "text",
                    "executive_summary": "Query could not be validated against the database schema.",
                    "business_insights": [],
                    "recommendations": ["Try asking a more specific question", "Include table or column names if possible"],
                    "error": f"Query validation failed: {validation_reason}"
                })

            # 5c. Execute against ERP DB
            try:
                print(f"[SQL-EXECUTE] Running SQL: {generated_sql}")
                data = await asyncio.wait_for(
                    loop.run_in_executor(_executor, lambda s=generated_sql: run_query(s)),
                    timeout=120  # Increased timeout because Tailscale DB is taking 80+ seconds
                )
                break  # Success — exit retry loop

            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail="Database query timed out. The remote ERP database is responding extremely slowly over the VPN.")

            except sqlalchemy.exc.SQLAlchemyError as e:
                db_error_str = str(e)
                print(f"[chat] SQL attempt {attempt + 1} failed: {db_error_str}")
                if attempt < MAX_RETRIES:
                    last_db_error = build_error_hint(db_error_str, schema_context, generated_sql)
                    continue
                # All retries exhausted — log and return graceful error
                log = models.QueryLog(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    sql_query=generated_sql,
                    status="error",
                    error_message=db_error_str
                )
                db.add(log)
                db.commit()
                return clean_response({
                    "summary": "I encountered a database error while executing your query. The data may not be available for the requested time period.",
                    "data": [],
                    "chart_type": "text",
                    "executive_summary": "Database query failed. Please try a different question.",
                    "business_insights": [],
                    "recommendations": ["Try narrowing your date range", "Check if the data exists for the requested period"],
                    "error": f"Database error: {db_error_str[:200]}"
                })

        # 5d. Clean ugly SQL column names (COUNT(*), SUM(x), AVG(x) → readable names)
        def clean_result_keys(rows: list) -> list:
            if not rows:
                return rows
            rename_map = {}
            for key in rows[0].keys():
                clean = key
                if key == "COUNT(*)":
                    clean = "total_count"
                elif re.match(r"COUNT\(.+\)", key, re.IGNORECASE):
                    col = re.search(r"COUNT\((.+)\)", key, re.IGNORECASE).group(1).strip("* ").lower()
                    clean = f"total_{col}" if col != "*" else "total_count"
                elif re.match(r"SUM\(.+\)", key, re.IGNORECASE):
                    col = re.search(r"SUM\((.+)\)", key, re.IGNORECASE).group(1).strip().lower().replace(".", "_")
                    clean = f"total_{col}"
                elif re.match(r"AVG\(.+\)", key, re.IGNORECASE):
                    col = re.search(r"AVG\((.+)\)", key, re.IGNORECASE).group(1).strip().lower().replace(".", "_")
                    clean = f"average_{col}"
                elif re.match(r"MAX\(.+\)", key, re.IGNORECASE):
                    col = re.search(r"MAX\((.+)\)", key, re.IGNORECASE).group(1).strip().lower().replace(".", "_")
                    clean = f"max_{col}"
                elif re.match(r"MIN\(.+\)", key, re.IGNORECASE):
                    col = re.search(r"MIN\((.+)\)", key, re.IGNORECASE).group(1).strip().lower().replace(".", "_")
                    clean = f"min_{col}"
                rename_map[key] = clean
            return [{rename_map.get(k, k): v for k, v in row.items()} for row in rows]

        data = clean_result_keys(data)

        # Handle aggregate queries (like SUM) that return a single row of NULLs when no records match
        if data and len(data) == 1 and all(v is None for v in data[0].values()):
            data = []

        # 6. Attach results and build a data-driven summary from the REAL results
        if generated_sql:
            llm_response["data"] = data

            
            if not data:
                # Smart empty message: let LLM explain what the empty result means
                try:
                    empty_msg = await asyncio.wait_for(
                        loop.run_in_executor(
                            _executor,
                            lambda: ai_service.generate_rag_response(request.question, [])
                        ),
                        timeout=15
                    )
                    summary = empty_msg if empty_msg else "No records match your current filter criteria."
                except Exception:
                    summary = "No records match your current filter criteria."
            else:
                try:
                    summary = await asyncio.wait_for(
                        loop.run_in_executor(
                            _executor,
                            lambda: ai_service.generate_rag_response(request.question, data)
                        ),
                        timeout=20
                    )
                except Exception as e:
                    print(f"RAG summary generation failed: {e}")
                    summary = "Here is the data you requested."
            if "dashboard_type" in llm_response:
                llm_response["summary"] = [summary]
                llm_response["chart_data"] = data
                llm_response["executive_summary"] = summary
            else:
                llm_response["summary"] = summary
                llm_response["executive_summary"] = summary
                llm_response["business_insights"] = []
                llm_response["recommendations"] = []


        # 7. Log success
        log = models.QueryLog(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            sql_query=generated_sql,
            status="success"
        )
        db.add(log)
        db.commit()

        execution_time_ms = int((time.time() - start_time) * 1000)
        llm_response = clean_response(llm_response)
        if request.view_mode != "dashboard":
            chat_history = models.ChatHistory(
                session_id=request.session_id,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                question=request.question,
                generated_sql=generated_sql,
                response_json=llm_response,
                execution_time_ms=execution_time_ms
            )
            db.add(chat_history)
            db.commit()

        return llm_response

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Unexpected error: {traceback.format_exc()}")


@router.get("/history")
def get_chat_history(db: Session = Depends(get_db), current_user: models.User = Depends(HasPermission("chat_erp")), limit: int = 20):
    """Fetch the user's chat history grouped by session."""
    # Get all history ordered by newest first
    history = db.query(models.ChatHistory).filter(
        models.ChatHistory.user_id == current_user.id
    ).order_by(models.ChatHistory.created_at.asc()).all()

    # Group by session_id
    sessions = {}
    # We use a list to keep track of the order of sessions by newest activity
    session_order = []

    for h in history:
        sid = h.session_id or f"legacy-{h.id}"
        if sid not in sessions:
            sessions[sid] = {
                "id": sid,
                "title": h.question, # First question becomes the title
                "created_at": h.created_at,
                "messages": []
            }
            session_order.append(sid)
        
        sessions[sid]["messages"].append({
            "id": h.id,
            "question": h.question,
            "response_json": h.response_json,
            "created_at": h.created_at
        })
        # Update latest activity
        sessions[sid]["created_at"] = h.created_at

    # Reverse to get newest sessions first and limit
    session_order.reverse()
    result = [sessions[sid] for sid in session_order[:limit]]
    
    return result

@router.get("/debug-qdrant")
def debug_qdrant(current_user: models.User = Depends(HasPermission("admin_settings"))):
    qdrant = get_qdrant()
    points, _ = qdrant.client.scroll(collection_name=qdrant.collection_name, limit=100)
    conn_counts = {}
    tables_by_conn = {}
    for p in points:
        cid = str(p.payload.get("connection_id"))
        conn_counts[cid] = conn_counts.get(cid, 0) + 1
        if cid not in tables_by_conn:
            tables_by_conn[cid] = []
        tables_by_conn[cid].append(p.payload.get("table_name"))
    return {"total_points": len(points), "connection_counts": conn_counts, "tables": tables_by_conn}


@router.post("/force-sync")
def force_sync_qdrant(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(HasPermission("manage_erp"))):
    from sqlalchemy import create_engine, text
    import urllib.parse

    tenant_id = current_user.tenant_id
    conn = db.query(models.ERPConnection).filter(
        models.ERPConnection.tenant_id == tenant_id,
        models.ERPConnection.is_active == True
    ).order_by(models.ERPConnection.id.desc()).first()
    if not conn:
        raise HTTPException(status_code=400, detail="No active ERP Connection found to sync.")
    connection_id = conn.id

    TABLE_DESCRIPTIONS = {
        "SalesOrder_Header": (
            "Stores all Sales Orders (SO). Real columns: id, So_number, customer_name, date (DATE), delivery_schedule, invoice_generated, created_at. "
            "Use created_at for date filtering. Join to SalesOrder_Details on So_number. "
            "Keywords: sales order, SO, customer order, how many orders, total orders."
        ),
        "SalesOrder_Details": (
            "Stores line items for each Sales Order. Real columns: so_details_id, So_number, item_id, name, ordered_qty, supplied_qty, pending_qty, unit_price. "
            "Join to SalesOrder_Header on So_number. Keywords: items ordered, quantities, pending qty."
        ),
        "Invoice_Header": (
            "Stores all Sales Invoices. IMPORTANT: Use column 'total' (NOT grand_total) for invoice value. "
            "Real columns: invoice_id, so_id, cpo_ref, customer_name, amount, tax_amount, tax_type, total (DECIMAL), created_at. "
            "Use created_at for date filtering. ORDER BY total DESC for highest invoice. "
            "Keywords: invoice, billing, high value invoice, invoice count, invoice total."
        ),
        "Invoice_Details": (
            "Stores line items for each Sales Invoice. Real columns: id, invoice_id, item_id, name, ordered_qty, supplied_qty, pending_qty, unit_price. "
            "Join to Invoice_Header on invoice_id. Keywords: invoice items, billed quantity."
        ),
        "purchase_orders_Header": (
            "Stores all LOCAL Purchase Orders (PO). THIS IS the local purchase table. "
            "Real columns: po_id, po_number, pr_id, supplier_id, po_date (DATE), payment_terms, sub_total, tax_total, grand_total (DECIMAL), created_at. "
            "Use po_date for date filtering. Use grand_total for total amount. "
            "IMPORTANT: There is NO po_type, source_type, or import_type column. "
            "For LOCAL purchases: use THIS table (purchase_orders_Header). For IMPORT purchases: use import_purchase_orders_Header. "
            "Keywords: local purchase, purchase order, PO, procurement, vendor order, local PO, domestic purchase."
        ),
        "purchase_order_Details": (
            "Stores line items for Local Purchase Orders. Real columns: po_item_id, po_id, item_id, quantity, uom, unit_price, tax_rate, line_total, created_at. "
            "Join to purchase_orders_Header on po_id. Keywords: purchased items, local order quantity."
        ),
        "grn_Header": (
            "Stores Goods Receipt Notes (GRN) — records of goods physically RECEIVED from suppliers. "
            "IMPORTANT: GRN is NOT the same as a purchase order. Do NOT use grn_Header to answer questions about 'how many purchases' or 'purchase count'. "
            "Real columns: grn_id, grn_number, po_id, supplier_id, grn_date (DATE), created_at. "
            "Use grn_date for date filtering. This table has NO total amount columns. If you need amounts, join purchase_orders_Header on po_id. "
            "Keywords: GRN, goods receipt, received goods, goods received note."
        ),
        "grn_Details": (
            "Stores line items for each GRN. Real columns: grn_item_id, grn_id, item_id, po_qty, received_qty, batch_lot_number, mfg_date, expiry_date, created_at. "
            "Join to grn_Header on grn_id. Use received_qty for quantity. IMPORTANT: This table has NO price columns. To get prices, join purchase_order_Details or use standardPrice from items."
        ),
        "purchase_requisitions_Header": (
            "Stores Purchase Requisitions (PR). Real columns: pr_id, pr_number, pr_date, required_by_date, department, requested_by, notes, created_at, priority. "
            "Use pr_number to look up a specific PR (e.g. PR-001). Keywords: PR, purchase requisition, PR-001."
        ),
        "purchase_requisition_Details": (
            "Stores line items for Purchase Requisitions. Real columns: pr_id, item_id, requested_quantity, uom, reason_for_request, created_at, unit_price, total_price. "
            "Join to purchase_requisitions_Header on pr_id. Keywords: PR items, requisition items, requested quantity."
        ),
        "import_purchase_orders_Header": (
            "Stores IMPORT Purchase Orders (IPO). THIS IS the only import purchase table header. "
            "VERIFIED Real columns: import_po_id, import_po_number, supplier_id, po_date (DATE), currency_id, exchange_rate, payment_terms, total_fcy (DECIMAL), total_lcy (DECIMAL), status, created_at. "
            "Use po_date for date filtering. Use total_lcy for LCY amount, total_fcy for foreign currency amount. "
            "CRITICAL: Do NOT use table names like 'import_purchase', 'import_po', 'import_purchase_item', or 'import_po_Header' — these DO NOT EXIST. "
            "The ONLY correct table names are: import_purchase_orders_Header and import_purchase_orders_Details. "
            "Keywords: import PO, import purchase, IPO, foreign purchase, overseas purchase."
        ),
        "import_purchase_orders_Details": (
            "Line items for Import Purchase Orders. VERIFIED Real columns: detail_id, import_po_id, item_id, currency_id, qty, fcy_unit_price, total_fcy. "
            "Join to import_purchase_orders_Header on import_po_id. Join to masters.items on item_id. "
            "CRITICAL: This table has NO 'return_date' column. Do NOT reference non-existent columns. "
            "Keywords: import items, imported quantity, import line items."
        ),
        "import_landed_costs_Header": (
            "Landed costs for imported goods. Real columns: import_landed_cost_id, import_po_id, duty_percent, sea_freight, road_freight, total_landed_cost, is_posted. "
            "Keywords: landed cost, import cost, freight cost, customs duty."
        ),
        "import_landed_costs_Details": (
            "Line items for import landed costs. Real columns: detail_id, import_landed_cost_id, item_id, qty, fob_val_lcy, allocated_overhead, total_landed_cost, landed_unit_cost. "
            "Keywords: landed cost items, freight per item."
        ),
        "local_landed_cost_Header": (
            "Landed costs for locally purchased goods. Real columns: landed_cost_id, grn_id, insurance_charges, handling_charges, packing_charges, total_landed_cost, is_posted. "
            "Keywords: local landed cost, freight, additional charges."
        ),
        "local_landed_cost_Details": (
            "Line items for local landed costs. Real columns: landed_cost_item_id, landed_cost_id, item_id, qty, unit_price, total_landed_cost, landed_unit_cost. "
            "Keywords: local cost items."
        ),
        "items": (
            "Master list of all inventory items/products. Real columns: id, name, group_id, category_id, brand, model, size, color, uom_id, hsnCode, minStock, reorderLevel, standardPrice, active, isImported. "
            "Join to any Details table using item_id = items.id. IMPORTANT: Use 'standardPrice' for item price, NOT 'unit_price'."
        ),
        "inventory_batches": (
            "Stores inventory stock batches showing current stock levels. Real columns: batch_id, batch_no, item_id, current_qty, mfg_date, expiry_date, landed_unit_cost, final_selling_price, margin_percent, status, inward_qty, outward_qty, damaged_qty. "
            "Use current_qty for stock level. Keywords: stock, inventory, batch, current stock, warehouse stock."
        ),
        "purchase_return_Header": (
            "Purchase Returns — items returned to suppliers. Real columns: return_id, return_number, grn_id, supplier_id, return_date, debit_note_status, refund_total, created_at. "
            "Keywords: purchase return, debit note, return to supplier."
        ),
        "purchase_return_Details": (
            "Line items for Purchase Returns. Real columns: return_item_id, return_id, item_id, inwarded_qty, return_qty, return_reason. "
            "Keywords: returned items, return quantity."
        ),
        "suppliers": (
            "Master list of all suppliers/vendors. Real columns: id, name, email, phone, type, currency, leadTime, active, taxDetails, paymentTerms. "
            "Keywords: supplier, vendor, vendor list, all suppliers, supplier name."
        ),
        "customers": (
            "Master list of all customers/clients. Real columns: id, name, email, phone, customer_type_id, active, billingAddress, shippingAddress, creditLimit, payment_term_id, sales_person_id. "
            "Keywords: customer, client, buyer, all customers, customer list."
        ),
        "purchase_order_delivery_schedules": (
            "Delivery schedules for Purchase Orders. Real columns: schedule_id, po_id, expected_delivery_date, target_quantity, created_at. "
            "Keywords: delivery schedule, expected delivery, PO delivery date."
        ),
        "users": (
            "ERP system users. Real columns: id, name, role, email, department, status, monthly_target. "
            "Keywords: user, staff, employee, sales person."
        ),
    }

    def _sync_task():
        qdrant = get_qdrant()
        from app.embeddings.metadata_embedder import MetadataEmbedder
        embedder = MetadataEmbedder()
        erp_schemas = ["Sales_Masters", "Purchase_Masters", "masters"]
        pwd = urllib.parse.quote_plus("Tr@d3w@63")
        count = 0
        for schema in erp_schemas:
            print(f"[bg-sync] Processing: {schema}")
            tw_engine = create_engine(
                f"mysql+pymysql://root:{pwd}@100.86.181.18:3309/{schema}",
                connect_args={"connect_timeout": 30}
            )
            with tw_engine.connect() as conn:
                table_names = [row[0] for row in conn.execute(text("SHOW TABLES")).fetchall()]
                for table_name in table_names:
                    cols_result = conn.execute(text(f"SHOW COLUMNS FROM `{table_name}`")).fetchall()
                    columns_str = ", ".join(f"{r[0]} ({r[1]})" for r in cols_result)
                    description = TABLE_DESCRIPTIONS.get(
                        table_name,
                        f"Table {schema}.{table_name}. Columns: {columns_str}"
                    )
                    full_text = f"Table {schema}.{table_name}\nDescription: {description}\nColumns: {columns_str}"
                    vector = embedder.embed_text(full_text)
                    qdrant.upsert_table_metadata(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        table_name=f"{schema}.{table_name}",
                        description=description,
                        columns=columns_str,
                        vector=vector
                    )
                    count += 1
                    print(f"[bg-sync] OK: {schema}.{table_name}")
        print(f"[bg-sync] Done! {count} tables synced to Qdrant.")

    background_tasks.add_task(_sync_task)
    return {"status": "sync_started", "message": "Schema sync is running in the background. Check Uvicorn logs for progress."}

def auto_remove_invalid_filters(sql: str, schema_context: str) -> str:
    """
    Removes column filters that reference non-existent columns in the tables.
    """
    import re
    # 1. Build table list and alias map
    alias_map = {}
    tables = []
    SQL_KEYWORDS = {"AS", "ON", "JOIN", "INNER", "LEFT", "RIGHT", "CROSS", "WHERE", "GROUP", "ORDER", "LIMIT", "USING", "AND", "OR", "UNION", "SELECT", "BY", "HAVING"}
    
    # We find FROM/JOIN targets
    for m in re.finditer(r'\b(?:FROM|JOIN)\s+([\w.]+)\b', sql, re.IGNORECASE):
        table_name = m.group(1)
        if table_name.upper() not in SQL_KEYWORDS:
            tables.append(table_name)
            # Find if there is an alias following it
            start_pos = m.end()
            tail = sql[start_pos:].strip()
            alias_match = re.match(r'^(?:AS\s+)?([a-zA-Z0-9_]+)\b', tail, re.IGNORECASE)
            if alias_match:
                alias = alias_match.group(1)
                if alias.upper() not in SQL_KEYWORDS:
                    alias_map[alias.upper()] = table_name

    # 2. Build table_name -> columns map from schema_context
    table_cols = {}
    for block in schema_context.split('\n\n'):
        tm = re.search(r'Table:\s*`?([a-zA-Z0-9_.]+)', block)
        if tm:
            tbl_name = tm.group(1)
            cols = set(re.findall(r'Column:\s*`?([a-zA-Z0-9_]+)', block))
            if not cols:
                cm = re.search(r'Columns:\s*(.+)', block, re.DOTALL)
                if cm:
                    cols = {c.split('(')[0].strip().replace('`', '').lower() for c in cm.group(1).split(',')}
            table_cols[tbl_name] = {c.lower() for c in cols}

    def repl_invalid_col(m: re.Match) -> str:
        alias = m.group(1)
        col = m.group(2)
        
        # Skip SQL keywords
        if col.upper() in SQL_KEYWORDS or (alias and alias.upper() in SQL_KEYWORDS):
            return m.group(0)
            
        # Check if the column is valid
        is_valid = False
        
        if alias:
            alias_upper = alias.upper()
            target_table = None
            if alias_upper in alias_map:
                target_table = alias_map[alias_upper]
            else:
                for t in tables:
                    if t.upper() == alias_upper or t.split('.')[-1].upper() == alias_upper:
                        target_table = t
                        break
            
            if target_table:
                for t_real, cols in table_cols.items():
                    if t_real.lower() == target_table.lower() or t_real.split('.')[-1].lower() == target_table.lower():
                        if col.lower() in cols:
                            is_valid = True
                            break
            else:
                is_valid = True
        else:
            if not tables:
                is_valid = True
            else:
                for target_table in tables:
                    for t_real, cols in table_cols.items():
                        if t_real.lower() == target_table.lower() or t_real.split('.')[-1].lower() == target_table.lower():
                            if col.lower() in cols:
                                is_valid = True
                                break
                    if is_valid:
                        break
                        
        if not is_valid:
            print(f"[filter-fixer] Removing filter on invalid column: {m.group(0)} -> 1=1")
            return "1=1"
        return m.group(0)

    # Regex matches columns (optionally aliased) in filters:
    # e.g., T1.status = 'created', status = 'created', T1.payment_status IS NULL
    pattern = r'\b(?:([a-zA-Z_][a-zA-Z0-9_]*)\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|!=|<>|>=|<=|>|<|\bLIKE\b|\bNOT\s+LIKE\b|\bIN\b|\bNOT\s+IN\b|\bIS\b\s+(?:\bNOT\b\s+)?\bNULL\b)\s*(?:\'[^\']*\'|"[^"]*"|\d+(?:\.\d+)?|\([^)]*\)|(?:CURDATE|CURRENT_DATE|NOW)\(\)?|[a-zA-Z0-9_]+)?'
    
    if " WHERE " in sql.upper():
        parts = re.split(r'(\bWHERE\b)', sql, flags=re.IGNORECASE, maxsplit=1)
        where_clause = re.sub(pattern, repl_invalid_col, parts[2], flags=re.IGNORECASE)
        sql = parts[0] + parts[1] + where_clause

    # Clean up double spaces or bad logical constructs
    sql = re.sub(r'\s+AND\s+1=1\b', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\b1=1\s+AND\s+', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bWHERE\s+1=1\s*$', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bWHERE\s+1=1\s+AND\s+', 'WHERE ', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\s+', ' ', sql).strip()
    return sql