import json
import random
import uuid
import csv
import os
from datetime import datetime, timedelta

# Configurations
NUM_CUSTOMERS = 1000
NUM_TRANSACTIONS = 5000
OUTPUT_DIR = "mock_data"

# Create directories
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(f"{OUTPUT_DIR}/raw_customers", exist_ok=True)
os.makedirs(f"{OUTPUT_DIR}/raw_transactions", exist_ok=True)

# Lookup Tables
BUSINESS_UNITS = ["marketing", "finance", "compliance", "analytics", "operations"]
SENSITIVITIES = ["public", "internal", "confidential", "restricted"]
REGIONS = ["US", "EU", "APAC", "ME", "LATAM"]
DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "corporate.org", "startup.io"]
PRODUCT_CATEGORIES = ["Electronics", "Apparel", "Home", "Books", "Automotive", "Garden"]

# Generate Customer Data (Batch Extract with PII)
customers = []
start_date = datetime.now() - timedelta(days=365)

for i in range(NUM_CUSTOMERS):
    cust_id = f"CUST_{100000 + i}"
    first_name = random.choice(["John", "Jane", "Alice", "Bob", "Charlie", "David", "Emma", "Frank", "Grace", "Henry"])
    last_name = random.choice(["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Garcia", "Rodriguez", "Wilson"])
    email = f"{first_name.lower()}.{last_name.lower()}@{random.choice(DOMAINS)}"
    phone = f"+1-{random.randint(200,999)}-{random.randint(200,999)}-{random.randint(1000,9999)}"
    ssn = f"{random.randint(100,999)}-{random.randint(10,99)-10}-{random.randint(1000,9999)}"
    country = random.choice(["US", "DE", "IN", "JP", "BR"])
    region = "US" if country == "US" else ("EU" if country == "DE" else ("APAC" if country in ["IN", "JP"] else "LATAM"))
    
    created_at = start_date + timedelta(days=random.randint(0, 300), hours=random.randint(0, 23))
    
    customers.append({
        "customer_id": cust_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone,
        "ssn": ssn,
        "country": country,
        "region_code": region,
        "created_at": created_at.isoformat()
    })

# Write customers to JSON (simulating JSON dumps)
customers_file = f"{OUTPUT_DIR}/raw_customers/customers.json"
with open(customers_file, "w") as f:
    for cust in customers:
        f.write(json.dumps(cust) + "\n")

# Generate Transaction Data (Streaming / Landing data)
transactions = []
for i in range(NUM_TRANSACTIONS):
    tx_id = f"TXN_{uuid.uuid4().hex[:12].upper()}"
    cust = random.choice(customers)
    amount = round(random.uniform(5.0, 2500.0), 2)
    product_id = f"PROD_{random.randint(1000, 9999)}"
    category = random.choice(PRODUCT_CATEGORIES)
    
    tx_time = datetime.fromisoformat(cust["created_at"]) + timedelta(days=random.randint(1, 60), hours=random.randint(0, 23))
    
    txn_record = {
        "transaction_id": tx_id,
        "customer_id": cust["customer_id"],
        "amount": amount,
        "product_id": product_id,
        "product_category": category,
        "region_code": cust["region_code"],
        "transaction_time": tx_time.isoformat(),
        "event_date": tx_time.strftime("%Y-%m-%d")
    }
    
    # Introduce schema drift dynamically (some transactions have extra columns like promotion_code or device_id)
    if random.random() < 0.15:
        txn_record["promotion_code"] = f"SUMMER_{random.randint(10, 50)}"
    if random.random() < 0.05:
        txn_record["device_type"] = random.choice(["iOS", "Android", "Desktop", "Tablet"])
        
    transactions.append(txn_record)

# Partition transactions by event_date to simulate daily landing
for txn in transactions:
    partition_dir = f"{OUTPUT_DIR}/raw_transactions/event_date={txn['event_date']}"
    os.makedirs(partition_dir, exist_ok=True)
    
    file_path = f"{partition_dir}/transactions_{txn['transaction_id'][:8]}.csv"
    
    with open(file_path, "w", newline="") as f:
        # Standard csv fields + dynamic fields if they exist in this record
        fields = ["transaction_id", "customer_id", "amount", "product_id", "product_category", "region_code", "transaction_time", "event_date"]
        if "promotion_code" in txn:
            fields.append("promotion_code")
        if "device_type" in txn:
            fields.append("device_type")
            
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow(txn)

print(f"✅ Generated Mock Data successfully!")
print(f"   👉 Customers raw file: {customers_file} ({len(customers)} records)")
print(f"   👉 Transactions partitioned records: {NUM_TRANSACTIONS} files in '{OUTPUT_DIR}/raw_transactions/'")
