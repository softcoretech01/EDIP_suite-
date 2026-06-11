import sqlalchemy
from sqlalchemy import text
import urllib.parse
import datetime
import random
import uuid

# Connection setup
pwd = urllib.parse.quote_plus('Tr@d3w@63')
sales_engine = sqlalchemy.create_engine(f'mysql+pymysql://root:{pwd}@100.86.181.18:3309/Sales_Masters')
purchase_engine = sqlalchemy.create_engine(f'mysql+pymysql://root:{pwd}@100.86.181.18:3309/Purchase_Masters')

customers = ["Alpha Corp", "Beta LLC", "Gamma Logistics", "Delta Tech"]
suppliers = ["SUPP-1", "SUPP-2", "Global Traders", "Local Supplies"]
items = [
    {"id": "ITM-101", "name": "Industrial Widget A", "price": 45.00},
    {"id": "ITM-102", "name": "Industrial Widget B", "price": 120.00},
    {"id": "ITM-103", "name": "Heavy Duty Valve", "price": 350.00},
    {"id": "ITM-104", "name": "Basic Connector", "price": 12.50},
    {"id": "ITM-105", "name": "Premium Sensor", "price": 280.00}
]

start_date = datetime.date(2026, 4, 1)
end_date = datetime.date(2026, 5, 31)
delta = datetime.timedelta(days=1)

def generate_data():
    current_date = start_date
    sales_conn = sales_engine.connect()
    purch_conn = purchase_engine.connect()
    
    transaction = sales_conn.begin()
    p_transaction = purch_conn.begin()
    
    so_counter = 100
    inv_counter = 100
    po_counter = 100
    ipo_counter = 100
    grn_counter = 100
    batch_counter = 1000

    try:
        while current_date <= end_date:
            # 1. Generate 1-2 Sales Orders per day
            for _ in range(random.randint(1, 2)):
                so_id = str(uuid.uuid4())
                so_number = f"SO-{current_date.strftime('%Y%m')}-{so_counter}"
                customer = random.choice(customers)
                delivery_date = current_date + datetime.timedelta(days=random.randint(2, 7))
                
                # Insert SO Header
                sales_conn.execute(
                    text("INSERT INTO SalesOrder_Header (id, So_number, customer_name, date, delivery_schedule, invoice_generated) VALUES (:id, :so_num, :cust, :date, :deliv, 1)"),
                    {"id": so_id, "so_num": so_number, "cust": customer, "date": current_date, "deliv": delivery_date}
                )
                
                # Insert SO Details
                total_amt = 0
                selected_items = random.sample(items, random.randint(1, 3))
                for item in selected_items:
                    qty = random.randint(5, 50)
                    total_amt += float(qty * item["price"])
                    sales_conn.execute(
                        text("INSERT INTO SalesOrder_Details (So_number, item_id, name, ordered_qty, supplied_qty, pending_qty, unit_price) VALUES (:so_num, :itm, :name, :qty, :qty, 0, :price)"),
                        {"so_num": so_number, "itm": item["id"], "name": item["name"], "qty": qty, "price": item["price"]}
                    )
                
                # Create Invoice
                inv_id = f"INV-{current_date.strftime('%Y%m')}-{inv_counter}"
                tax = float(total_amt * 0.18)
                grand = total_amt + tax
                sales_conn.execute(
                    text("INSERT INTO Invoice_Header (invoice_id, so_id, customer_name, amount, tax_amount, total) VALUES (:inv_id, :so_id, :cust, :amt, :tax, :tot)"),
                    {"inv_id": inv_id, "so_id": so_number, "cust": customer, "amt": total_amt, "tax": tax, "tot": grand}
                )
                for item in selected_items:
                    sales_conn.execute(
                        text("INSERT INTO Invoice_Details (invoice_id, item_id, name, ordered_qty, supplied_qty, unit_price) VALUES (:inv_id, :itm, :name, 1, 1, :price)"),
                        {"inv_id": inv_id, "itm": item["id"], "name": item["name"], "price": item["price"]}
                    )
                
                so_counter += 1
                inv_counter += 1

            # 2. Generate 1 Local PO per day
            po_number = f"PO-{current_date.strftime('%Y%m')}-{po_counter}"
            supplier = random.choice(suppliers)
            
            res = purch_conn.execute(
                text("INSERT INTO purchase_orders_Header (po_number, supplier_id, po_date, sub_total, tax_total, grand_total) VALUES (:po, :sup, :date, 0, 0, 0)"),
                {"po": po_number, "sup": supplier, "date": current_date}
            )
            po_id = res.lastrowid
            
            po_total = 0
            for item in random.sample(items, 2):
                qty = random.randint(20, 100)
                line_tot = float(qty * (item["price"] * 0.6)) # Buying cheaper
                po_total += line_tot
                purch_conn.execute(
                    text("INSERT INTO purchase_order_Details (po_id, item_id, quantity, unit_price, line_total) VALUES (:pid, :itm, :qty, :price, :tot)"),
                    {"pid": po_id, "itm": item["id"], "qty": qty, "price": item["price"] * 0.6, "tot": line_tot}
                )
            purch_conn.execute(text("UPDATE purchase_orders_Header SET sub_total=:tot, grand_total=:tot WHERE po_id=:pid"), {"tot": po_total, "pid": po_id})
            
            # GRN for the PO
            grn_number = f"GRN-{current_date.strftime('%Y%m')}-{grn_counter}"
            res = purch_conn.execute(
                text("INSERT INTO grn_Header (grn_number, po_id, supplier_id, grn_date) VALUES (:grn, :pid, :sup, :date)"),
                {"grn": grn_number, "pid": po_id, "sup": supplier, "date": current_date}
            )
            grn_id = res.lastrowid
            
            for item in random.sample(items, 2):
                qty = random.randint(20, 100)
                purch_conn.execute(
                    text("INSERT INTO grn_Details (grn_id, item_id, po_qty, received_qty) VALUES (:gid, :itm, :qty, :qty)"),
                    {"gid": grn_id, "itm": item["id"], "qty": qty}
                )
                # Inventory Batch
                batch_no = f"BTH-{batch_counter}"
                purch_conn.execute(
                    text("INSERT INTO inventory_batches (batch_no, item_id, current_qty, landed_unit_cost, final_selling_price, source_type, grn_reference) VALUES (:bth, :itm, :qty, :cost, :price, 'Local Purchase', :grn)"),
                    {"bth": batch_no, "itm": item["id"], "qty": qty, "cost": item["price"]*0.6, "price": item["price"], "grn": grn_number}
                )
                batch_counter += 1

            po_counter += 1
            grn_counter += 1
            
            # 3. Generate 1 Import PO every few days
            if current_date.day % 3 == 0:
                ipo_number = f"IPO-{current_date.strftime('%Y%m')}-{ipo_counter}"
                res = purch_conn.execute(
                    text("INSERT INTO import_purchase_orders_Header (import_po_number, supplier_id, po_date, exchange_rate, status) VALUES (:ipo, :sup, :date, 83.5, 'Received')"),
                    {"ipo": ipo_number, "sup": supplier, "date": current_date}
                )
                ipo_id = res.lastrowid
                
                for item in random.sample(items, 2):
                    qty = random.randint(50, 200)
                    purch_conn.execute(
                        text("INSERT INTO import_purchase_orders_Details (import_po_id, item_id, qty, fcy_unit_price) VALUES (:id, :itm, :qty, :price)"),
                        {"id": ipo_id, "itm": item["id"], "qty": qty, "price": (item["price"] * 0.5) / 83.5}
                    )
                ipo_counter += 1

            current_date += delta

        transaction.commit()
        p_transaction.commit()
        print("Successfully injected 2 months of synthetic data!")
        
    except Exception as e:
        transaction.rollback()
        p_transaction.rollback()
        print("Error generating data:", e)
    finally:
        sales_conn.close()
        purch_conn.close()

if __name__ == "__main__":
    generate_data()
