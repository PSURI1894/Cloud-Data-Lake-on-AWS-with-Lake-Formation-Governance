import pytest
from src.lambdas.pii_auto_detector.index import evaluate_pii

def test_evaluate_pii_detections():
    """
    Validates regex engine correctly identifies SSN, email, and phone categories
    from CSV lines.
    """
    headers = ["customer_id", "email_addr", "ssn_num", "phone", "amount"]
    
    # Mock data lines
    sample_rows = [
        "C_1001,john.doe@gmail.com,123-45-6789,+1-555-555-5555,100.50",
        "C_1002,jane.smith@yahoo.com,987-65-4321,+1-444-444-4444,20.00"
    ]
    
    detections = evaluate_pii(sample_rows, headers)
    
    # Asserts
    assert detections.get("email_addr") == "direct"
    assert detections.get("ssn_num") == "direct"
    assert detections.get("phone") == "direct"
    assert "amount" not in detections # Double check non-PII column not flagged
    assert "customer_id" not in detections
