import sqlite3
import random
from datetime import datetime, timedelta
import os

def create_mock_erp():
    db_path = os.path.join(os.path.dirname(__file__), "mock_erp.db")
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create Tables
    cursor.execute('''
    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY,
        name TEXT,
        region TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY,
        name TEXT,
        category TEXT,
        price REAL
    )
    ''')

    cursor.execute('''
    CREATE TABLE sales (
        sale_id INTEGER PRIMARY KEY,
        customer_id INTEGER,
        product_id INTEGER,
        quantity INTEGER,
        sale_date DATE,
        total_amount REAL,
        FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY(product_id) REFERENCES products(product_id)
    )
    ''')

    # Insert Data
    regions = ['North', 'South', 'East', 'West']
    categories = ['Electronics', 'Furniture', 'Office Supplies']
    
    for i in range(1, 21):
        cursor.execute('INSERT INTO customers (name, region) VALUES (?, ?)', 
                       (f'Customer {i}', random.choice(regions)))

    for i in range(1, 11):
        cursor.execute('INSERT INTO products (name, category, price) VALUES (?, ?, ?)', 
                       (f'Product {i}', random.choice(categories), round(random.uniform(10.0, 500.0), 2)))

    conn.commit()

    # Generate 2 months of sales data (Past 60 days)
    cursor.execute('SELECT product_id, price FROM products')
    products = cursor.fetchall()
    
    start_date = datetime.now() - timedelta(days=60)
    
    for _ in range(500):
        cust_id = random.randint(1, 20)
        prod = random.choice(products)
        prod_id, price = prod
        qty = random.randint(1, 10)
        total = round(qty * price, 2)
        
        # Random date in the last 60 days
        sale_date = start_date + timedelta(days=random.randint(0, 60))
        date_str = sale_date.strftime('%Y-%m-%d')
        
        cursor.execute('''
        INSERT INTO sales (customer_id, product_id, quantity, sale_date, total_amount)
        VALUES (?, ?, ?, ?, ?)
        ''', (cust_id, prod_id, qty, date_str, total))

    conn.commit()
    conn.close()
    print("Mock ERP database created successfully with 2 months of data in mock_erp.db!")

if __name__ == "__main__":
    create_mock_erp()
