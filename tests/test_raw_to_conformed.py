import pytest
from pyspark.sql.functions import col, to_timestamp, current_timestamp
from datetime import datetime

def test_transactions_schema_conformance(spark_session):
    """
    Tests that columns are correctly typed, timestamp forms mapped,
    and snake-cased for standard Iceberg writes.
    """
    spark = spark_session
    
    # Mock some raw transaction rows
    raw_data = [
        ("TXN_101", "CUST_99", "123.45", "PROD_1", "Electronics", "US", "2026-05-18T10:30:00Z", "2026-05-18"),
        ("TXN_102", "CUST_88", "99.99", "PROD_2", "Books", "EU", "2026-05-18T12:00:00Z", "2026-05-18")
    ]
    columns = ["Transaction_ID", "Customer_ID", "Amount", "Product_ID", "Product_Category", "Region_Code", "Transaction_Time", "Event_Date"]
    
    df = spark.createDataFrame(raw_data, columns)
    
    # Run pipeline transformations
    transformed_df = df         .withColumn("amount", col("Amount").cast("double"))         .withColumn("transaction_time", to_timestamp(col("Transaction_Time")))
        
    for c in transformed_df.columns:
        transformed_df = transformed_df.withColumnRenamed(c, c.lower().strip())
        
    # Validations
    schema = transformed_df.schema
    assert "transaction_id" in transformed_df.columns
    assert schema["amount"].dataType.simpleString() == "double"
    assert schema["transaction_time"].dataType.simpleString() == "timestamp"
    
    # Confirm exact mapping
    first_row = transformed_df.collect()[0]
    assert first_row["amount"] == 123.45
    assert isinstance(first_row["transaction_time"], datetime)

def test_deduplication_and_upsert(spark_session):
    """
    Validates Spark SQL Iceberg MERGE INTO duplicates handling.
    """
    spark = spark_session
    
    # Create test Iceberg table locally
    spark.sql("DROP TABLE IF EXISTS testcatalog.test_db.transactions")
    spark.sql("CREATE DATABASE IF NOT EXISTS testcatalog.test_db")
    spark.sql("""
        CREATE TABLE testcatalog.test_db.transactions (
            transaction_id string,
            amount double,
            product_category string,
            region_code string
        )
        USING iceberg
    """)
    
    # Insert seed record
    spark.sql("INSERT INTO testcatalog.test_db.transactions VALUES ('TX_01', 50.0, 'Books', 'US')")
    
    # Prepare update record (amount change) + insert record
    incoming_data = [
        ("TX_01", 55.50, "Books", "US"),  # Update
        ("TX_02", 120.00, "Home", "EU")   # New
    ]
    incoming_df = spark.createDataFrame(incoming_data, ["transaction_id", "amount", "product_category", "region_code"])
    incoming_df.createOrReplaceTempView("incoming_view")
    
    # Perform Merge
    spark.sql("""
        MERGE INTO testcatalog.test_db.transactions t
        USING incoming_view s
        ON t.transaction_id = s.transaction_id
        WHEN MATCHED THEN
            UPDATE SET t.amount = s.amount
        WHEN NOT MATCHED THEN
            INSERT (transaction_id, amount, product_category, region_code)
            VALUES (s.transaction_id, s.amount, s.product_category, s.region_code)
    """)
    
    # Retrieve results
    results = spark.sql("SELECT * FROM testcatalog.test_db.transactions ORDER BY transaction_id").collect()
    
    assert len(results) == 2
    assert results[0]["transaction_id"] == "TX_01"
    assert results[0]["amount"] == 55.50  # Value updated
    assert results[1]["transaction_id"] == "TX_02"
    assert results[1]["amount"] == 120.00 # Record inserted
