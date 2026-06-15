import sqlite3
import os
import random
from datetime import datetime, timedelta

def create_sqlite_erp():
    db_files = ["sales_masters.db", "purchase_masters.db", "masters.db"]
    for db_file in db_files:
        if os.path.exists(db_file):
            os.remove(db_file)
            print(f"Removed existing local DB: {db_file}")

    print("Creating schemas and seeding database files...")

    # ==========================================
    # 1. MASTERS DATABASE
    # ==========================================
    m_conn = sqlite3.connect("masters.db")
    m_cur = m_conn.cursor()

    m_cur.execute("""
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        region TEXT NOT NULL,
        status TEXT DEFAULT 'Active'
    )
    """)

    m_cur.execute("""
    CREATE TABLE items (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        uom TEXT DEFAULT 'PCS',
        minStock REAL DEFAULT 0,
        reorderLevel REAL DEFAULT 0,
        standardPrice REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    m_cur.execute("""
    CREATE TABLE suppliers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        contact_person TEXT,
        email TEXT,
        status TEXT DEFAULT 'Active'
    )
    """)

    m_cur.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        department TEXT,
        status TEXT DEFAULT 'Active',
        monthly_target REAL DEFAULT 0
    )
    """)

    # Seed Masters
    regions = ["North", "South", "East", "West"]
    customers_data = [
        (1, "Alpha Corp", "North"),
        (2, "Beta LLC", "South"),
        (3, "Gamma Logistics", "East"),
        (4, "Delta Tech", "West"),
        (5, "Quantum Group", "North"),
        (6, "Nippon Sales", "South"),
        (7, "Zenith Industries", "East"),
        (8, "Apex Products", "West"),
    ]
    m_cur.executemany("INSERT INTO customers (id, name, region) VALUES (?, ?, ?)", customers_data)

    suppliers_data = [
        ("SUPP-001", "Nippon Machinery Corp", "Hiroshi Tanaka", "info@nippon-machinery.com"),
        ("SUPP-002", "Global Traders Ltd", "Sarah Jenkins", "sales@global-traders.com"),
        ("SUPP-003", "Local Supplies Inc", "John Doe", "john@localsupplies.com"),
        ("SUPP-004", "Tech Parts Germany", "Hans Mueller", "support@techparts.de"),
    ]
    m_cur.executemany("INSERT INTO suppliers (id, name, contact_person, email) VALUES (?, ?, ?, ?)", suppliers_data)

    items_data = [
        ("TN001", "Industrial Compressor A", "PCS", 100.0, 150.0, 1500.0),
        ("TN005", "Pneumatic Valve V5", "PCS", 50.0, 75.0, 250.0),
        ("ITM-101", "Industrial Widget A", "PCS", 20.0, 30.0, 45.0),
        ("ITM-102", "Industrial Widget B", "PCS", 10.0, 15.0, 120.0),
        ("ITM-103", "Heavy Duty Valve", "PCS", 5.0, 8.0, 350.0),
        ("ITM-104", "Basic Connector", "PCS", 200.0, 300.0, 12.50),
        ("ITM-105", "Premium Sensor", "PCS", 15.0, 25.0, 280.0),
        ("ITM-106", "Selendang Gasket", "PCS", 0.0, 0.0, 15.0), # Will be zero stock
    ]
    m_cur.executemany("INSERT INTO items (id, name, uom, minStock, reorderLevel, standardPrice) VALUES (?, ?, ?, ?, ?, ?)", items_data)

    users_data = [
        (1, "Kabilesh", "Administrator", "kabil@gmail.com", "Management", 100000.0),
        (2, "Alice Smith", "Sales Executive", "alice@edip.com", "Sales", 50000.0),
        (3, "Bob Johnson", "Procurement Officer", "bob@edip.com", "Purchasing", 0.0),
    ]
    m_cur.executemany("INSERT INTO users (id, name, role, email, department, monthly_target) VALUES (?, ?, ?, ?, ?, ?)", users_data)

    m_conn.commit()
    m_conn.close()


    # ==========================================
    # 2. SALES MASTERS DATABASE
    # ==========================================
    s_conn = sqlite3.connect("sales_masters.db")
    s_cur = s_conn.cursor()

    s_cur.execute("""
    CREATE TABLE Invoice_Details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        name TEXT NOT NULL,
        ordered_qty REAL DEFAULT 0,
        supplied_qty REAL DEFAULT 0,
        pending_qty REAL DEFAULT 0,
        unit_price REAL DEFAULT 0
    )
    """)

    s_cur.execute("""
    CREATE TABLE Invoice_Header (
        invoice_id TEXT PRIMARY KEY,
        so_id TEXT NOT NULL,
        cpo_ref TEXT,
        customer_name TEXT NOT NULL,
        amount REAL DEFAULT 0,
        tax_amount REAL DEFAULT 0,
        tax_type TEXT DEFAULT 'IGST',
        total REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    s_cur.execute("""
    CREATE TABLE SalesOrder_Details (
        so_details_id INTEGER PRIMARY KEY AUTOINCREMENT,
        So_number TEXT NOT NULL,
        item_id TEXT NOT NULL,
        name TEXT NOT NULL,
        ordered_qty REAL DEFAULT 1,
        supplied_qty REAL DEFAULT 1,
        pending_qty REAL DEFAULT 0,
        unit_price REAL DEFAULT 0
    )
    """)

    s_cur.execute("""
    CREATE TABLE SalesOrder_Header (
        id TEXT PRIMARY KEY,
        So_number TEXT,
        customer_name TEXT NOT NULL,
        date TEXT NOT NULL,
        delivery_schedule TEXT,
        invoice_generated INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Seed Sales Data (2026-04-01 to 2026-06-15)
    start_date = datetime(2026, 4, 1)
    end_date = datetime(2026, 6, 15)
    current_date = start_date

    so_counter = 100
    inv_counter = 100

    sales_items = [
        ("TN001", "Industrial Compressor A", 1500.0),
        ("TN005", "Pneumatic Valve V5", 250.0),
        ("ITM-101", "Industrial Widget A", 45.0),
        ("ITM-102", "Industrial Widget B", 120.0),
        ("ITM-103", "Heavy Duty Valve", 350.0),
        ("ITM-104", "Basic Connector", 12.50),
        ("ITM-105", "Premium Sensor", 280.0),
    ]

    while current_date <= end_date:
        # Create a sales order every day
        so_id = f"SO_ID_{so_counter}"
        so_number = f"SO-2026-{so_counter:03d}"
        cust = random.choice(customers_data)[1]
        date_str = current_date.strftime("%Y-%m-%d")
        created_at_str = current_date.strftime("%Y-%m-%d %H:%M:%S")
        deliv_str = (current_date + timedelta(days=5)).strftime("%Y-%m-%d")

        # Determine if invoice is generated (most are generated, some recent ones are not)
        invoice_gen = 1 if current_date < datetime(2026, 6, 10) else 0

        s_cur.execute("""
        INSERT INTO SalesOrder_Header (id, So_number, customer_name, date, delivery_schedule, invoice_generated, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (so_id, so_number, cust, date_str, deliv_str, invoice_gen, created_at_str))

        # 1-3 items per order
        total_amt = 0
        items_in_order = random.sample(sales_items, random.randint(1, 3))
        for itm_id, itm_name, itm_price in items_in_order:
            qty = random.randint(2, 20)
            line_tot = qty * itm_price
            total_amt += line_tot
            
            s_cur.execute("""
            INSERT INTO SalesOrder_Details (So_number, item_id, name, ordered_qty, supplied_qty, pending_qty, unit_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (so_number, itm_id, itm_name, qty, qty if invoice_gen else 0, 0 if invoice_gen else qty, itm_price))

        if invoice_gen:
            # Generate invoice
            inv_id = f"INV-2026-{inv_counter:03d}"
            tax = total_amt * 0.18
            grand_total = total_amt + tax
            
            s_cur.execute("""
            INSERT INTO Invoice_Header (invoice_id, so_id, customer_name, amount, tax_amount, total, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (inv_id, so_number, cust, total_amt, tax, grand_total, created_at_str))

            for itm_id, itm_name, itm_price in items_in_order:
                s_cur.execute("""
                INSERT INTO Invoice_Details (invoice_id, item_id, name, ordered_qty, supplied_qty, unit_price)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (inv_id, itm_id, itm_name, qty, qty, itm_price))
            inv_counter += 1

        so_counter += 1
        current_date += timedelta(days=1)

    s_conn.commit()
    s_conn.close()


    # ==========================================
    # 3. PURCHASE MASTERS DATABASE
    # ==========================================
    p_conn = sqlite3.connect("purchase_masters.db")
    p_cur = p_conn.cursor()

    p_cur.execute("""
    CREATE TABLE grn_Details (
        grn_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        grn_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        po_qty REAL NOT NULL,
        received_qty REAL NOT NULL,
        batch_lot_number TEXT,
        mfg_date TEXT,
        expiry_date TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    p_cur.execute("""
    CREATE TABLE grn_Header (
        grn_id INTEGER PRIMARY KEY AUTOINCREMENT,
        grn_number TEXT UNIQUE NOT NULL,
        po_id INTEGER,
        supplier_id TEXT NOT NULL,
        grn_date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    p_cur.execute("""
    CREATE TABLE import_landed_costs_Details (
        detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_landed_cost_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        qty REAL NOT NULL,
        fob_val_lcy REAL DEFAULT 0,
        allocated_overhead REAL DEFAULT 0,
        total_landed_cost REAL DEFAULT 0,
        landed_unit_cost REAL DEFAULT 0
    )
    """)

    p_cur.execute("""
    CREATE TABLE import_landed_costs_Header (
        import_landed_cost_id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_po_id INTEGER UNIQUE NOT NULL,
        duty_percent REAL DEFAULT 0,
        cess_percent REAL DEFAULT 0,
        gst_percent REAL DEFAULT 0,
        include_gst INTEGER DEFAULT 0,
        sea_freight REAL DEFAULT 0,
        road_freight REAL DEFAULT 0,
        local_transport REAL DEFAULT 0,
        liner_charges REAL DEFAULT 0,
        insurance_cost REAL DEFAULT 0,
        handling_charges REAL DEFAULT 0,
        packing_charges REAL DEFAULT 0,
        aging_charges REAL DEFAULT 0,
        total_customs_duty REAL DEFAULT 0,
        total_freight REAL DEFAULT 0,
        total_port_charges REAL DEFAULT 0,
        total_overhead REAL DEFAULT 0,
        total_landed_cost REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        is_posted INTEGER DEFAULT 0
    )
    """)

    p_cur.execute("""
    CREATE TABLE import_purchase_orders_Details (
        detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_po_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        currency_id INTEGER,
        qty REAL NOT NULL,
        fcy_unit_price REAL NOT NULL,
        total_fcy REAL DEFAULT 0
    )
    """)

    p_cur.execute("""
    CREATE TABLE import_purchase_orders_Header (
        import_po_id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_po_number TEXT UNIQUE NOT NULL,
        supplier_id TEXT NOT NULL,
        po_date TEXT NOT NULL,
        currency_id INTEGER,
        exchange_rate REAL NOT NULL,
        payment_terms TEXT,
        total_fcy REAL DEFAULT 0,
        total_lcy REAL DEFAULT 0,
        status TEXT DEFAULT 'Ordered',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    p_cur.execute("""
    CREATE TABLE inventory_batches (
        batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_no TEXT UNIQUE NOT NULL,
        item_id TEXT NOT NULL,
        current_qty REAL NOT NULL,
        mfg_date TEXT,
        expiry_date TEXT,
        landed_unit_cost REAL NOT NULL,
        final_selling_price REAL NOT NULL,
        margin_percent REAL DEFAULT 20,
        status TEXT DEFAULT 'Available',
        source_type TEXT NOT NULL,
        po_reference TEXT,
        grn_reference TEXT,
        IPO_reference TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        is_posted INTEGER DEFAULT 0,
        inward_qty REAL DEFAULT 0,
        outward_qty REAL DEFAULT 0,
        damaged_qty REAL DEFAULT 0,
        damage_remarks TEXT
    )
    """)

    p_cur.execute("""
    CREATE TABLE local_landed_cost_Details (
        landed_cost_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        landed_cost_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        qty REAL NOT NULL,
        unit_price REAL NOT NULL,
        val_lcy REAL NOT NULL,
        allocated_overhead REAL NOT NULL,
        total_landed_cost REAL NOT NULL,
        landed_unit_cost REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    p_cur.execute("""
    CREATE TABLE local_landed_cost_Header (
        landed_cost_id INTEGER PRIMARY KEY AUTOINCREMENT,
        grn_id INTEGER UNIQUE NOT NULL,
        insurance_charges REAL DEFAULT 0,
        handling_charges REAL DEFAULT 0,
        packing_charges REAL DEFAULT 0,
        aging_charges REAL DEFAULT 0,
        total_lcy REAL NOT NULL,
        total_overhead REAL NOT NULL,
        total_landed_cost REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        is_posted INTEGER DEFAULT 0
    )
    """)

    p_cur.execute("""
    CREATE TABLE purchase_order_Details (
        po_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        quantity REAL NOT NULL,
        uom TEXT DEFAULT 'PCS',
        unit_price REAL NOT NULL,
        tax_rate REAL DEFAULT 0,
        line_total REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    p_cur.execute("""
    CREATE TABLE purchase_order_delivery_schedules (
        schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_id INTEGER NOT NULL,
        expected_delivery_date TEXT NOT NULL,
        target_quantity REAL NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    p_cur.execute("""
    CREATE TABLE purchase_orders_Header (
        po_id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_number TEXT UNIQUE NOT NULL,
        pr_id INTEGER,
        supplier_id TEXT NOT NULL,
        po_date TEXT NOT NULL,
        payment_terms TEXT,
        sub_total REAL DEFAULT 0,
        tax_total REAL DEFAULT 0,
        grand_total REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    p_cur.execute("""
    CREATE TABLE purchase_requisition_Details (
        pr_id INTEGER NOT NULL,
        item_id TEXT,
        requested_quantity REAL NOT NULL,
        uom TEXT DEFAULT 'PCS',
        reason_for_request TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        unit_price REAL,
        total_price REAL DEFAULT 0
    )
    """)

    p_cur.execute("""
    CREATE TABLE purchase_requisitions_Header (
        pr_id INTEGER PRIMARY KEY AUTOINCREMENT,
        pr_number TEXT UNIQUE NOT NULL,
        pr_date TEXT NOT NULL,
        required_by_date TEXT,
        department TEXT,
        requested_by INTEGER,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        priority TEXT
    )
    """)

    p_cur.execute("""
    CREATE TABLE purchase_return_Details (
        return_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        inwarded_qty REAL NOT NULL,
        return_qty REAL NOT NULL,
        return_reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    p_cur.execute("""
    CREATE TABLE purchase_return_Header (
        return_id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_number TEXT UNIQUE NOT NULL,
        grn_id INTEGER NOT NULL,
        supplier_id TEXT NOT NULL,
        return_date TEXT NOT NULL,
        debit_note_status TEXT DEFAULT 'Pending',
        refund_total REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Seed Purchase Data
    current_date = start_date
    po_counter = 100
    grn_counter = 100
    batch_counter = 1000
    pr_counter = 100
    return_counter = 100

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        created_at_str = current_date.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Purchase Requisition (PR) every 3 days
        if current_date.day % 3 == 0:
            pr_num = f"PR-2026-{pr_counter:03d}"
            p_cur.execute("""
            INSERT INTO purchase_requisitions_Header (pr_number, pr_date, required_by_date, department, requested_by, priority)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (pr_num, date_str, (current_date + timedelta(days=10)).strftime("%Y-%m-%d"), "Production", 1, "High" if pr_counter % 2 == 0 else "Normal"))
            
            pr_id = p_cur.lastrowid
            
            # Add details
            itm = random.choice(items_data)
            qty = random.randint(10, 100)
            price = itm[5]
            total_p = qty * price
            p_cur.execute("""
            INSERT INTO purchase_requisition_Details (pr_id, item_id, requested_quantity, reason_for_request, unit_price, total_price)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (pr_id, itm[0], qty, "Restocking raw materials", price, total_p))
            pr_counter += 1

        # 2. Local Purchase Order (PO) every 2 days
        if current_date.day % 2 == 0:
            po_num = f"PO-2026-{po_counter:03d}"
            supplier_id = random.choice(suppliers_data)[0]
            
            p_cur.execute("""
            INSERT INTO purchase_orders_Header (po_number, supplier_id, po_date, grand_total, created_at)
            VALUES (?, ?, ?, 0, ?)
            """, (po_num, supplier_id, date_str, created_at_str))
            
            po_id = p_cur.lastrowid
            
            # Details
            total_po = 0
            items_to_buy = random.sample(items_data[:-1], random.randint(1, 2)) # Don't buy the zero-stock gasket
            for itm in items_to_buy:
                qty = random.randint(50, 200)
                cost = itm[5] * 0.7 # Buying cost is lower than selling
                line_total = qty * cost
                total_po += line_total
                
                p_cur.execute("""
                INSERT INTO purchase_order_Details (po_id, item_id, quantity, unit_price, line_total, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (po_id, itm[0], qty, cost, line_total, created_at_str))
                
                # Delivery schedule
                p_cur.execute("""
                INSERT INTO purchase_order_delivery_schedules (po_id, expected_delivery_date, target_quantity)
                VALUES (?, ?, ?)
                """, (po_id, (current_date + timedelta(days=7)).strftime("%Y-%m-%d"), qty))
                
            p_cur.execute("UPDATE purchase_orders_Header SET sub_total=?, grand_total=? WHERE po_id=?", (total_po, total_po, po_id))
            
            # GRN for this PO
            grn_num = f"GRN-2026-{grn_counter:03d}"
            p_cur.execute("""
            INSERT INTO grn_Header (grn_number, po_id, supplier_id, grn_date, created_at)
            VALUES (?, ?, ?, ?, ?)
            """, (grn_num, po_id, supplier_id, date_str, created_at_str))
            
            grn_id = p_cur.lastrowid
            
            for itm in items_to_buy:
                p_cur.execute("""
                INSERT INTO grn_Details (grn_id, item_id, po_qty, received_qty, created_at)
                VALUES (?, ?, ?, ?, ?)
                """, (grn_id, itm[0], qty, qty, created_at_str))
                
                # Add to inventory_batches
                b_num = f"BTH-2026-{batch_counter}"
                p_cur.execute("""
                INSERT INTO inventory_batches (batch_no, item_id, current_qty, landed_unit_cost, final_selling_price, source_type, po_reference, grn_reference, created_at)
                VALUES (?, ?, ?, ?, ?, 'Local Purchase', ?, ?, ?)
                """, (b_num, itm[0], qty, cost, itm[5], po_num, grn_num, created_at_str))
                batch_counter += 1
                
            # Local Landed Cost
            p_cur.execute("""
            INSERT INTO local_landed_cost_Header (grn_id, insurance_charges, handling_charges, total_lcy, total_overhead, total_landed_cost)
            VALUES (?, 150.0, 100.0, ?, 250.0, ?)
            """, (grn_id, total_po, total_po + 250.0))
            
            po_counter += 1
            grn_counter += 1

        # 3. Import PO every 5 days
        if current_date.day % 5 == 0:
            ipo_num = f"IPO-2026-{po_counter:03d}"
            supplier_id = "SUPP-001" # Nippon Machinery Corp
            
            p_cur.execute("""
            INSERT INTO import_purchase_orders_Header (import_po_number, supplier_id, po_date, exchange_rate, status, created_at)
            VALUES (?, ?, ?, 83.5, 'Received', ?)
            """, (ipo_num, supplier_id, date_str, created_at_str))
            
            ipo_id = p_cur.lastrowid
            
            # Details
            qty = random.randint(100, 300)
            cost_fcy = 12.0 # In foreign currency
            total_fcy = qty * cost_fcy
            total_lcy = total_fcy * 83.5
            
            p_cur.execute("""
            INSERT INTO import_purchase_orders_Details (import_po_id, item_id, qty, fcy_unit_price, total_fcy)
            VALUES (?, 'TN001', ?, ?, ?)
            """, (ipo_id, qty, cost_fcy, total_fcy))
            
            p_cur.execute("UPDATE import_purchase_orders_Header SET total_fcy=?, total_lcy=? WHERE import_po_id=?", (total_fcy, total_lcy, ipo_id))
            
            # Import Landed Cost
            p_cur.execute("""
            INSERT INTO import_landed_costs_Header (import_po_id, duty_percent, total_customs_duty, total_freight, total_overhead, total_landed_cost)
            VALUES (?, 10.0, ?, 500.0, ?, ?)
            """, (ipo_id, total_lcy * 0.1, 500.0, total_lcy * 0.1 + 500.0))
            
            # Add to inventory_batches
            b_num = f"BTH-2026-{batch_counter}"
            p_cur.execute("""
            INSERT INTO inventory_batches (batch_no, item_id, current_qty, landed_unit_cost, final_selling_price, source_type, IPO_reference, created_at)
            VALUES (?, 'TN001', ?, ?, 1500.0, 'Import Purchase', ?, ?)
            """, (b_num, qty, (total_lcy * 1.1 + 500.0)/qty, ipo_num, created_at_str))
            batch_counter += 1
            po_counter += 1

        # 4. Purchase Return every 10 days
        if current_date.day % 10 == 0 and grn_counter > 100:
            ret_num = f"PRR-2026-{return_counter:03d}"
            target_grn_id = grn_counter - 1 - 100 # Previous GRN
            p_cur.execute("""
            INSERT INTO purchase_return_Header (return_number, grn_id, supplier_id, return_date, refund_total)
            VALUES (?, ?, 'SUPP-001', ?, 750.0)
            """, (ret_num, target_grn_id, date_str))
            
            ret_id = p_cur.lastrowid
            p_cur.execute("""
            INSERT INTO purchase_return_Details (return_id, item_id, inwarded_qty, return_qty, return_reason)
            VALUES (?, 'TN005', 100.0, 3.0, 'Defective valves')
            """, (ret_id,))
            return_counter += 1

        current_date += timedelta(days=1)

    # Let's seed specific stock levels to fulfill the reorder/low stock test results!
    # Item TN001 has reorderLevel = 150, minStock = 100. Let's make sure its total current stock is 120 (low stock, exceeded reorderLevel).
    # Item TN005 has reorderLevel = 75, minStock = 50. Let's make sure its total current stock is 60 (low stock, exceeded reorderLevel).
    # Item ITM-104 has zero stock.
    # First delete existing batches for them
    p_cur.execute("DELETE FROM inventory_batches WHERE item_id IN ('TN001', 'TN005', 'ITM-104', 'ITM-106')")
    
    # Insert specific batches
    p_cur.execute("""
    INSERT INTO inventory_batches (batch_no, item_id, current_qty, landed_unit_cost, final_selling_price, source_type)
    VALUES ('BTH-SPEC-001', 'TN001', 120.0, 1050.0, 1500.0, 'Local Purchase')
    """)
    p_cur.execute("""
    INSERT INTO inventory_batches (batch_no, item_id, current_qty, landed_unit_cost, final_selling_price, source_type)
    VALUES ('BTH-SPEC-002', 'TN005', 60.0, 175.0, 250.0, 'Local Purchase')
    """)
    p_cur.execute("""
    INSERT INTO inventory_batches (batch_no, item_id, current_qty, landed_unit_cost, final_selling_price, source_type)
    VALUES ('BTH-SPEC-003', 'ITM-104', 0.0, 8.0, 12.50, 'Local Purchase')
    """)
    p_cur.execute("""
    INSERT INTO inventory_batches (batch_no, item_id, current_qty, landed_unit_cost, final_selling_price, source_type)
    VALUES ('BTH-SPEC-004', 'ITM-106', 0.0, 10.0, 15.0, 'Local Purchase')
    """)

    p_conn.commit()
    p_conn.close()

    print("Success! Created and seeded sales_masters.db, purchase_masters.db, and masters.db!")

if __name__ == "__main__":
    create_sqlite_erp()
