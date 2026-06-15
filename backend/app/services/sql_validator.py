import re
from typing import Tuple

class SQLValidator:
    """
    Validates SQL queries to ensure they only contain safe SELECT operations.
    Allows: SELECT, WITH (CTE), GROUP BY, ORDER BY, JOIN, LIMIT, subqueries
    Blocks: DELETE, UPDATE, DROP, ALTER, TRUNCATE, INSERT, EXEC, MERGE
    """

    BLOCKED_KEYWORDS = [
        "DELETE", "UPDATE", "DROP", "ALTER", "TRUNCATE", "INSERT",
        "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "EXEC", "EXECUTE",
        "MERGE", "CALL"
    ]

    @staticmethod
    def clean_sql(query: str) -> str:
        """
        Pre-cleans LLM-generated SQL before validation and execution:
        - Strips markdown code fences (```sql ... ```)
        - Strips leading SQL comments (-- and /* */)
        - Strips trailing semicolons on single statements (safe and common)
        """
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
        # Handle semicolons — extract only the first valid SELECT statement.
        # The LLM sometimes generates multiple statements; we use only the first.
        if ";" in q:
            parts = [p.strip() for p in q.split(";") if p.strip()]
            # Find first part that is a SELECT or WITH statement
            for part in parts:
                upper_part = part.upper().lstrip("(").strip()
                if upper_part.startswith("SELECT") or upper_part.startswith("WITH"):
                    q = part
                    break
            else:
                # No SELECT found — take first part anyway
                q = parts[0] if parts else q
        return q

    @staticmethod
    def is_safe_query(query: str) -> Tuple[bool, str]:
        if not query or not query.strip():
            return False, "Query is empty"

        # Pre-clean the query
        cleaned = SQLValidator.clean_sql(query)
        if not cleaned:
            return False, "Query is empty after cleaning"

        upper = cleaned.upper()

        # Must start with SELECT or WITH (CTEs)
        if not upper.startswith("SELECT") and not upper.startswith("WITH"):
            return False, f"Query must be a SELECT statement. Received: {cleaned[:30]}"

        # Check for blocked DML/DDL keywords (word boundaries avoid false matches in column names)
        for keyword in SQLValidator.BLOCKED_KEYWORDS:
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, upper):
                return False, f"Blocked keyword found: {keyword}"

        # Check for genuine multiple statements — trailing ; was stripped above,
        # so any remaining ; means 2+ actual SQL statements
        if ";" in cleaned:
            parts = [p.strip() for p in cleaned.split(";") if p.strip()]
            if len(parts) > 1:
                return False, "Multiple statements are not allowed."

        return True, "Query is safe"

    @staticmethod
    def validate_sql_schema(query: str, schema_context: str) -> Tuple[bool, str]:
        """
        Validates that the SQL query matches the schema in schema_context:
        1. Checks that all tables exist.
        2. Checks that all referenced columns exist in their respective tables.
        3. Identifies and rejects self-joins (e.g., T1.So_number = T1.So_number).
        """
        import re
        
        # Clean query first
        cleaned = SQLValidator.clean_sql(query)
        if not cleaned:
            return False, "Query is empty after cleaning"

        # 1. Strip comments and string literals
        # strip block comments
        q_no_comments = re.sub(r'/\*.*?\*/', ' ', cleaned, flags=re.DOTALL)
        # strip line comments
        q_no_comments = re.sub(r'--.*$', ' ', q_no_comments, flags=re.MULTILINE)
        # strip string literals (single/double quoted) with escape chars handled
        q_stripped = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", " ", q_no_comments)
        q_stripped = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', " ", q_stripped)

        # 2. Parse table schemas from schema_context
        table_cols = {} # full_table_name -> set of column names
        for block in schema_context.split('\n\n'):
            tm = re.search(r'Table: (\S+)', block)
            cm = re.search(r'Columns: (.+)', block, re.DOTALL)
            if tm and cm:
                cols = {c.split('(')[0].strip().lower() for c in cm.group(1).split(',')}
                table_cols[tm.group(1)] = cols

        # 3. Find CTEs (Common Table Expressions) and Select-list aliases
        ctes = set()
        for m in re.finditer(r'\bWITH\s+([a-zA-Z0-9_]+)\s+AS\s*\(', q_stripped, re.IGNORECASE):
            ctes.add(m.group(1).upper())
        for m in re.finditer(r',\s*([a-zA-Z0-9_]+)\s+AS\s*\(', q_stripped, re.IGNORECASE):
            ctes.add(m.group(1).upper())

        select_aliases = set()
        for m in re.finditer(r'\bAS\s+([a-zA-Z0-9_]+)\b', q_stripped, re.IGNORECASE):
            select_aliases.add(m.group(1).upper())

        # 4. Find tables and aliases in the query
        token_pattern = r'\b[a-zA-Z0-9_.]+\b|`[a-zA-Z0-9_.]+`|\(|\)'
        raw_tokens = re.findall(token_pattern, q_stripped)
        tokens = [t.replace('`', '') for t in raw_tokens]

        alias_map = {} # alias -> full_table_name
        tables_found = []

        SQL_KEYWORDS = {
            "SELECT", "FROM", "JOIN", "ON", "WHERE", "GROUP", "BY", "ORDER", "LIMIT",
            "HAVING", "UNION", "ALL", "AS", "INNER", "LEFT", "RIGHT", "CROSS", "WITH",
            "CASE", "WHEN", "THEN", "ELSE", "END", "BETWEEN", "IN", "LIKE", "IS", "NULL",
            "NOT", "COLLATE", "EXISTS", "USING", "AND", "OR", "DESC", "ASC", "DISTINCT", "INTERVAL",
            "ESCAPE", "INTO", "SET", "DEFAULT"
        }

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
                        # Subquery
                        depth = 1
                        j = i + 2
                        while j < len(tokens) and depth > 0:
                            if tokens[j] == "(":
                                depth += 1
                            elif tokens[j] == ")":
                                depth -= 1
                            j += 1
                        
                        if j < len(tokens):
                            sub_alias = None
                            if tokens[j].upper() == "AS":
                                if j + 1 < len(tokens):
                                    sub_alias = tokens[j+1]
                                    j += 1
                            elif tokens[j].upper() not in SQL_KEYWORDS and tokens[j] not in ("(", ")"):
                                sub_alias = tokens[j]
                            
                            if sub_alias:
                                alias_map[sub_alias.upper()] = "SUBQUERY"
                        i = j
                else:
                    i += 1
            else:
                i += 1

        # Map tables themselves as aliases to allow direct table.col references
        for t in tables_found:
            t_upper = t.upper()
            t_base = t.split('.')[-1].upper()
            alias_map[t_upper] = t
            alias_map[t_base] = t

        # Validate that all referenced physical tables exist in schema context (ignore CTEs)
        for table in tables_found:
            if table.upper() in ctes:
                continue
            found = False
            for t_name in table_cols.keys():
                if t_name.lower() == table.lower() or t_name.split('.')[-1].lower() == table.lower():
                    found = True
                    break
            if not found:
                return False, f"TABLE NOT FOUND: Table '{table}' is not present in the database schema context. Available tables: {list(table_cols.keys())}"

        # 5. Check for invalid self-join expressions in ON clause
        self_join = re.search(r'\bON\s+([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*=\s*\1\.\2\b', cleaned, re.IGNORECASE)
        if self_join:
            alias = self_join.group(1)
            col = self_join.group(2)
            return False, f"INVALID JOIN: Self-join detected: '{alias}.{col} = {alias}.{col}'. A table cannot be joined to itself on the same column. You must join different tables (e.g. T1.{col} = T2.{col})."

        # 6. Extract and Validate Column References
        cols_to_validate = [] # list of (table_name, col_name, full_ref)
        
        # Match aliased references: prefix.col
        aliased_refs = re.findall(r'\b([a-zA-Z0-9_.]+)\.([a-zA-Z0-9_]+)\b', q_stripped)
        for prefix, col in aliased_refs:
            # Skip database.table references
            prefix_lower = prefix.lower()
            col_lower = col.lower()
            is_table_ref = False
            for t_name in table_cols.keys():
                parts = t_name.lower().split('.')
                if len(parts) == 2:
                    db_part, table_part = parts
                    if prefix_lower == db_part and col_lower == table_part:
                        is_table_ref = True
                        break
            if is_table_ref:
                continue
                
            prefix_upper = prefix.upper()
            if prefix_upper in alias_map:
                table_name = alias_map[prefix_upper]
                if table_name != "SUBQUERY":
                    cols_to_validate.append((table_name, col, f"{prefix}.{col}"))
            else:
                resolved_table = None
                for t_name in table_cols.keys():
                    if t_name.upper() == prefix_upper or t_name.split('.')[-1].upper() == prefix_upper:
                        resolved_table = t_name
                        break
                if resolved_table:
                    cols_to_validate.append((resolved_table, col, f"{prefix}.{col}"))

        # Validate aliased columns
        for table_name, col_ref, full_ref in cols_to_validate:
            # Skip validation if table is a CTE
            if table_name.upper() in ctes:
                continue
            valid_cols = None
            for t_real, cols in table_cols.items():
                if t_real.lower() == table_name.lower() or t_real.split('.')[-1].lower() == table_name.lower():
                    valid_cols = cols
                    break
            if valid_cols and col_ref.lower() not in valid_cols:
                if "salesorder" in table_name.lower() and col_ref.lower() in ["total", "grand_total"]:
                    return False, (
                        f"VALIDATION ERROR: Column '{col_ref}' does NOT exist in table '{table_name}'. "
                        f"To get the total value of a Sales Order, you must join Sales_Masters.SalesOrder_Header and "
                        f"Sales_Masters.SalesOrder_Details and calculate SUM(SalesOrder_Details.ordered_qty * SalesOrder_Details.unit_price) dynamically. "
                        f"Do NOT reference '{col_ref}' directly."
                    )
                return False, f"VALIDATION ERROR: Column '{col_ref}' does not exist in table '{table_name}'. Available columns: {sorted(list(valid_cols))}"

        # Match unaliased column references
        INTERVAL_UNITS = {
            "DAY", "MONTH", "YEAR", "WEEK", "HOUR", "MINUTE", "SECOND", "QUARTER",
            "MICROSECOND", "SECOND", "MINUTE_SECOND", "HOUR_SECOND", "HOUR_MINUTE",
            "DAY_SECOND", "DAY_MINUTE", "DAY_HOUR", "YEAR_MONTH"
        }
        SQL_FUNCTIONS = {
            "SUM", "COUNT", "AVG", "MIN", "MAX", "COALESCE", "CURDATE", "CURRENT_DATE",
            "DATE_TRUNC", "NOW", "MONTH", "YEAR", "QUARTER", "WEEK", "DAY", "HOUR",
            "MINUTE", "SECOND", "CONVERT", "IFNULL", "ROUND", "ABS", "CONCAT", "LOWER",
            "UPPER", "SUBSTR", "SUBSTRING", "TRIM", "REPLACE", "DATE_SUB", "DATE_ADD",
            "DATEDIFF", "TIMESTAMPDIFF", "DATE", "ADDDATE", "SUBDATE", "EXTRACT", "LAST_DAY",
            "DATE_FORMAT", "STR_TO_DATE", "CAST", "CHAR", "CHAR_LENGTH", "CHARACTER_LENGTH",
            "INSTR", "LENGTH", "POSITION", "LOCATE", "LPAD", "RPAD", "LTRIM", "RTRIM",
            "REPEAT", "SPACE", "REVERSE", "LEFT", "RIGHT", "MID", "CURTIME", "SYSDATE",
            "UTC_DATE", "UTC_TIME", "UTC_TIMESTAMP", "LOCALTIME", "LOCALTIMESTAMP",
            "GREATEST", "LEAST", "IF", "NULLIF", "ISNULL"
        }

        unaliased_words = []
        q_unaliased_only = re.sub(r'\b[a-zA-Z0-9_.]+\.[a-zA-Z0-9_]+\b', ' ', q_stripped)
        words = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', q_unaliased_only)
        
        ignore_set = set()
        for kw in SQL_KEYWORDS:
            ignore_set.add(kw.upper())
        for f in SQL_FUNCTIONS:
            ignore_set.add(f.upper())
        for unit in INTERVAL_UNITS:
            ignore_set.add(unit.upper())
        for t in tables_found:
            ignore_set.add(t.upper())
            ignore_set.add(t.split('.')[-1].upper())
            if '.' in t:
                ignore_set.add(t.split('.')[0].upper())
        for alias in alias_map.keys():
            ignore_set.add(alias.upper())
        for sa in select_aliases:
            ignore_set.add(sa.upper())
        for cte in ctes:
            ignore_set.add(cte.upper())
            
        ignore_set.update({"SALES_MASTERS", "PURCHASE_MASTERS", "MASTERS"})
        
        for word in words:
            word_upper = word.upper()
            if word_upper not in ignore_set:
                unaliased_words.append(word)

        # Validate unaliased columns
        if unaliased_words:
            # Build union of all valid columns in queried physical tables
            all_valid_cols = set()
            for table in tables_found:
                if table.upper() in ctes:
                    continue
                for t_real, cols in table_cols.items():
                    if t_real.lower() == table.lower() or t_real.split('.')[-1].lower() == table.lower():
                        all_valid_cols.update(cols)
                        break
            
            # If no physical tables found or mapped, check all tables in context
            if not all_valid_cols:
                for cols in table_cols.values():
                    all_valid_cols.update(cols)

            for word in set(unaliased_words):
                if word.lower() not in all_valid_cols:
                    return False, f"VALIDATION ERROR: Column or word '{word}' is not a valid column name in the queried tables. Available columns: {sorted(list(all_valid_cols))}"
                    
        return True, "SQL Schema Validation Passed"


