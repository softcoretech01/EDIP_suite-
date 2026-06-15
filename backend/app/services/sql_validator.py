import re
from typing import Tuple

class SQLValidator:
    BLOCKED_KEYWORDS = [
        "DELETE", "UPDATE", "DROP", "ALTER", "TRUNCATE", "INSERT",
        "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "EXEC", "EXECUTE",
        "MERGE", "CALL"
    ]

    @staticmethod
    def clean_sql(query: str) -> str:
        if not query:
            return ""
        q = query.strip()
        
        # Remove markdown code fences
        q = re.sub(r'^```sql\s*', '', q, flags=re.IGNORECASE)
        q = re.sub(r'^```\s*', '', q, flags=re.IGNORECASE)
        q = re.sub(r'```\s*$', '', q).strip()
        
        # Strip leading line comments
        while q.startswith('--'):
            parts = q.split('\n', 1)
            q = parts[1].strip() if len(parts) > 1 else ""
            
        # Strip leading block comments
        while q.startswith('/*'):
            end_idx = q.find('*/')
            if end_idx != -1:
                q = q[end_idx + 2:].strip()
            else:
                break

        # Fix: Safely split by semicolon ONLY outside string literals
        # This matches semicolons that are not inside single quotes
        if ";" in q:
            parts = re.split(r';(?=(?:[^\']*\'[^\']*\')*[^\']*$)', q)
            parts = [p.strip() for p in parts if p.strip()]
            for part in parts:
                upper_part = part.upper().lstrip("(").strip()
                if upper_part.startswith("SELECT") or upper_part.startswith("WITH"):
                    q = part
                    break
            else:
                q = parts[0] if parts else q
        return q

    @staticmethod
    def is_safe_query(query: str) -> Tuple[bool, str]:
        if not query or not query.strip():
            return False, "Query is empty"

        cleaned = SQLValidator.clean_sql(query)
        if not cleaned:
            return False, "Query is empty after cleaning"

        upper = cleaned.upper()

        if not upper.startswith("SELECT") and not upper.startswith("WITH"):
            return False, f"Query must be a SELECT statement. Received: {cleaned[:30]}"

        for keyword in SQLValidator.BLOCKED_KEYWORDS:
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, upper):
                return False, f"Blocked keyword found: {keyword}"

        # Safe semicolon check (ignoring internal string literals)
        if ";" in cleaned:
            parts = re.split(r';(?=(?:[^\']*\'[^\']*\')*[^\']*$)', cleaned)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) > 1:
                return False, "Multiple statements are not allowed."

        return True, "Query is safe"

    @staticmethod
    def validate_sql_schema(query: str, schema_context: str) -> Tuple[bool, str]:
        import re
        
        cleaned = SQLValidator.clean_sql(query)
        if not cleaned:
            return False, "Query is empty after cleaning"

        # 🛑 ADD THIS BLOCK TO INTERCEPT GENERIC LLM GUESSES:
        cleaned = re.sub(r'\b(FROM\s+)invoices\b', r'\1Sales_Masters.Invoice_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(JOIN\s+)invoices\b', r'\1Sales_Masters.Invoice_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(FROM\s+)invoice\b', r'\1Sales_Masters.Invoice_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(JOIN\s+)invoice\b', r'\1Sales_Masters.Invoice_Header', cleaned, flags=re.IGNORECASE)

        # Apply database prefix standardizations
        cleaned = re.sub(r'\b(FROM\s+)Sales_Masters(?!\.)', r'\1Sales_Masters.SalesOrder_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(JOIN\s+)Sales_Masters(?!\.)', r'\1Sales_Masters.SalesOrder_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(FROM\s+)Purchase_Masters(?!\.)', r'\1Purchase_Masters.purchase_orders_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(JOIN\s+)Purchase_Masters(?!\.)', r'\1Purchase_Masters.purchase_orders_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(FROM\s+)masters(?!\.)', r'\1masters.items', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(JOIN\s+)masters(?!\.)', r'\1masters.items', cleaned, flags=re.IGNORECASE)

        # Standardize generic/naked table names to fully qualified names
        cleaned = re.sub(r'\b(?:Sales_Masters\.)?invoices\b', 'Sales_Masters.Invoice_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:Sales_Masters\.)?invoice\b', 'Sales_Masters.Invoice_Header', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:Sales_Masters\.)?invoice_details\b', 'Sales_Masters.Invoice_Details', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:Sales_Masters\.)?invoices_details\b', 'Sales_Masters.Invoice_Details', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:masters\.)?users\b', 'masters.users', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:masters\.)?user\b', 'masters.users', cleaned, flags=re.IGNORECASE)

        # Strip comments and strings to protect validation parsing
        q_no_comments = re.sub(r'/\*.*?\*/', ' ', cleaned, flags=re.DOTALL)
        q_no_comments = re.sub(r'--.*$', ' ', q_no_comments, flags=re.MULTILINE)
        q_stripped = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", " ", q_no_comments)
        q_stripped = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', " ", q_stripped)

        # Parse contexts
        table_cols = {}
        for block in schema_context.split('\n\n'):
            tm = re.search(r'Table: (\S+)', block)
            cm = re.search(r'Columns: (.+)', block, re.DOTALL)
            if tm and cm:
                t_name = tm.group(1).replace('`', '')
                cols = {c.split('(')[0].strip().lower() for c in cm.group(1).split(',')}
                table_cols[t_name] = cols

        ctes = set()
        for m in re.finditer(r'\bWITH\s+([a-zA-Z0-9_]+)\s+AS\s*\(', q_stripped, re.IGNORECASE):
            ctes.add(m.group(1).upper())
        for m in re.finditer(r',\s*([a-zA-Z0-9_]+)\s+AS\s*\(', q_stripped, re.IGNORECASE):
            ctes.add(m.group(1).upper())

        select_aliases = set()
        for m in re.finditer(r'\bAS\s+([a-zA-Z0-9_]+)\b', q_stripped, re.IGNORECASE):
            select_aliases.add(m.group(1).upper())

        token_pattern = r'\b[a-zA-Z0-9_.]+\b|`[a-zA-Z0-9_.]+`|\(|\)'
        tokens = [t.replace('`', '') for t in re.findall(token_pattern, q_stripped)]

        alias_map = {}
        tables_found = []

        SQL_KEYWORDS = {
            "SELECT", "FROM", "JOIN", "ON", "WHERE", "GROUP", "BY", "ORDER", "LIMIT",
            "HAVING", "UNION", "ALL", "AS", "INNER", "LEFT", "RIGHT", "CROSS", "WITH",
            "CASE", "WHEN", "THEN", "ELSE", "END", "BETWEEN", "IN", "LIKE", "IS", "NULL",
            "NOT", "COLLATE", "EXISTS", "USING", "AND", "OR", "DESC", "ASC", "DISTINCT", "INTERVAL"
        }

        # Fix: Keep subquery tracking but DO NOT jump over their internal tokens
        i = 0
        while i < len(tokens):
            token_upper = tokens[i].upper()
            if token_upper in ("FROM", "JOIN"):
                if i + 1 < len(tokens):
                    next_token = tokens[i+1]
                    if next_token != "(":
                        table_name = next_token
                        if table_name.upper() not in SQL_KEYWORDS:
                            tables_found.append(table_name)
                            alias = None
                            if i + 2 < len(tokens):
                                third_token = tokens[i+2]
                                third_token_upper = third_token.upper()
                                if third_token_upper == "AS":
                                    if i + 3 < len(tokens):
                                        alias = tokens[i+3]
                                        i += 3
                                elif third_token_upper not in SQL_KEYWORDS and third_token not in ("(", ")"):
                                    alias = third_token
                                    i += 2
                                else:
                                    i += 1
                            else:
                                i += 1
                            if alias:
                                alias_map[alias.upper()] = table_name
                        else:
                            i += 1
                    else:
                        # It is a subquery. Do not step skip its elements! 
                        # Just step into it naturally so internal tables register.
                        alias_map[f"SUBQUERY_{i}"] = "SUBQUERY"
                        i += 1
                else:
                    i += 1
            else:
                i += 1

        # Map base tables as direct references
        for t in tables_found:
            alias_map[t.upper()] = t
            alias_map[t.split('.')[-1].upper()] = t

        # Validate that referenced physical tables exist
        for table in tables_found:
            if table.upper() in ctes or table.upper() == "SELECT":
                continue
            found = False
            for t_name in table_cols.keys():
                if t_name.lower() == table.lower() or t_name.split('.')[-1].lower() == table.lower():
                    found = True
                    break
            if not found:
                schema_names = {'sales_masters', 'purchase_masters', 'masters'}
                if table.lower() in schema_names:
                    schema_table_map = {
                        'sales_masters': 'Sales_Masters.SalesOrder_Header',
                        'purchase_masters': 'Purchase_Masters.purchase_orders_Header',
                        'masters': 'masters.items'
                    }
                    suggested = schema_table_map.get(table.lower(), '')
                    return False, (
                        f"SCHEMA-AS-TABLE ERROR: '{table}' is a DATABASE SCHEMA, NOT a table. "
                        f"Use '{suggested}' instead."
                    )
                return False, f"TABLE NOT FOUND: Table '{table}' is missing from schema context."

        # Self-join checker
        if re.search(r'\bON\s+([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*=\s*\1\.\2\b', cleaned, re.IGNORECASE):
            return False, "INVALID JOIN: Self-join condition detected on identical table alias prefixes."

        # Validate Column References
        cols_to_validate = []
        aliased_refs = re.findall(r'\b([a-zA-Z0-9_.]+)\.([a-zA-Z0-9_]+)\b', q_stripped)
        for prefix, col in aliased_refs:
            prefix_lower = prefix.lower()
            is_table_ref = False
            for t_name in table_cols.keys():
                parts = t_name.lower().split('.')
                if len(parts) == 2 and prefix_lower == parts[0] and col.lower() == parts[1]:
                    is_table_ref = True
                    break
            if is_table_ref:
                continue
                
            prefix_upper = prefix.upper()
            if prefix_upper in alias_map:
                table_name = alias_map[prefix_upper]
                if table_name != "SUBQUERY":
                    cols_to_validate.append((table_name, col))

        for table_name, col_ref in cols_to_validate:
            if table_name.upper() in ctes:
                continue
            valid_cols = None
            for t_real, cols in table_cols.items():
                if t_real.lower() == table_name.lower() or t_real.split('.')[-1].lower() == table_name.lower():
                    valid_cols = cols
                    break
            if valid_cols and col_ref.lower() not in valid_cols:
                return False, f"VALIDATION ERROR: Column '{col_ref}' does not exist in table '{table_name}'."

        return True, "SQL Schema Validation Passed"