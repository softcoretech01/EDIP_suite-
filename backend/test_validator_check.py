import sys
sys.path.insert(0, '.')
from app.services.sql_validator import SQLValidator

sql = "SELECT DATE_FORMAT(T1.created_at, '%Y-%m') AS sale_month, SUM(T1.total) AS total_sales FROM Sales_Masters.Invoice_Header AS T1 WHERE T1.created_at >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH) GROUP BY sale_month ORDER BY sale_month ASC"

schema_context = """Table: Sales_Masters.Invoice_Header
Description: Sales invoices
Columns: invoice_id (int), so_id (int), cpo_ref (varchar), customer_name (varchar), amount (decimal), tax_amount (decimal), tax_type (varchar), total (decimal), created_at (datetime)"""

is_safe, reason = SQLValidator.is_safe_query(sql)
print(f'is_safe: {is_safe}, reason: {reason}')

is_valid, vreason = SQLValidator.validate_sql_schema(sql, schema_context)
print(f'is_valid: {is_valid}, vreason: {vreason}')
