import json
import boto3
import re

s3 = boto3.client('s3')
glue = boto3.client('glue')
lf = boto3.client('lakeformation')

# PII Detection Heuristic Regex Patterns
PII_PATTERNS = {
    'ssn': re.compile(r'^\d{3}-\d{2}-\d{4}$'),
    'email': re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'),
    'phone': re.compile(r'^\+?1?\s*[-.]?\(?\d{3}\)?[-.]?\s*\d{3}[-.]?\s*\d{4}$'),
    'credit_card': re.compile(r'^\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}$')
}

def sample_s3_file(bucket, key, num_lines=100):
    """Downloads first few lines of an S3 file to sample for PII"""
    try:
        response = s3.get_object(Bucket=bucket, Key=key, Range='bytes=0-1048576') # read first 1MB
        content = response['Body'].read().decode('utf-8', errors='ignore')
        lines = content.split('\n')
        return lines[:num_lines]
    except Exception as e:
        print(f"⚠️ Error sampling S3 file s3://{bucket}/{key}: {str(e)}")
        return []

def evaluate_pii(sample_data, headers):
    """Analyzes header arrays and content row patterns to detect PII columns"""
    detected_pii = {}
    
    # 1. Simple heuristic: match header names
    for idx, header in enumerate(headers):
        header_clean = header.lower().replace('_', '').replace('-', '')
        if 'ssn' in header_clean or 'socialsecurity' in header_clean:
            detected_pii[header] = 'direct'
        elif 'email' in header_clean:
            detected_pii[header] = 'direct'
        elif 'phone' in header_clean or 'telephone' in header_clean:
            detected_pii[header] = 'direct'
        elif 'creditcard' in header_clean or 'ccnum' in header_clean:
            detected_pii[header] = 'direct'
            
    # 2. Heuristic: match sample records via Regex
    for row in sample_data:
        # Split by comma or tab if CSV, skip JSON parses for simplicity here
        parts = row.split(',')
        if len(parts) != len(headers):
            continue
            
        for idx, val in enumerate(parts):
            val = val.strip().strip('"').strip("'")
            header = headers[idx]
            
            # If already marked direct, skip re-check
            if detected_pii.get(header) == 'direct':
                continue
                
            for pii_type, pattern in PII_PATTERNS.items():
                if pattern.match(val):
                    print(f"🚨 PII Heuristics triggered! Field '{header}' matched pattern '{pii_type}' for value '{val}'")
                    detected_pii[header] = 'direct'
                    
    return detected_pii

def apply_lf_pii_tag(db_name, table_name, column_name, pii_type):
    """Attaches PII tag to the Glue catalog table column in Lake Formation"""
    try:
        print(f"🏷️ Tagging Column: {db_name}.{table_name}.{column_name} -> PII={pii_type}")
        lf.add_lftags_to_resource(
            Resource={
                'TableWithColumns': {
                    'DatabaseName': db_name,
                    'Name': table_name,
                    'ColumnNames': [column_name]
                }
            },
            LFTags=[{
                'TagKey': 'PII',
                'TagValues': [pii_type]
            }]
        )
    except Exception as e:
        print(f"❌ Failed to apply LF tag to {db_name}.{table_name}.{column_name}: {str(e)}")

def lambda_handler(event, context):
    """
    Lambda entrypoint triggered by Glue Crawler completion event
    """
    print("🚀 PII Auto Detector Lambda Triggered")
    
    # Extract details from event
    detail = event.get('detail', {})
    crawler_name = detail.get('crawlerName', 'raw_data_crawler')
    
    try:
        crawler = glue.get_crawler(Name=crawler_name)
        targets = crawler['Crawler']['Targets']['S3Targets']
        db_name = crawler['Crawler']['DatabaseName']
        
        for target in targets:
            path = target['Path']
            # Parse S3 Bucket & Key prefix
            s3_parts = path.replace('s3://', '').split('/', 1)
            bucket = s3_parts[0]
            prefix = s3_parts[1] if len(s3_parts) > 1 else ''
            
            # Find a sample file in S3 path
            objs = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=5)
            sample_key = None
            for obj in objs.get('Contents', []):
                key = obj['Key']
                if key.endswith('.csv') or key.endswith('.json'):
                    sample_key = key
                    break
                    
            if not sample_key:
                print(f"⚠️ No sample files found for target prefix: {prefix}")
                continue
                
            print(f"📥 Sampling file: s3://{bucket}/{sample_key}")
            sample_lines = sample_s3_file(bucket, sample_key)
            if not sample_lines:
                continue
                
            # Assume CSV with headers for raw landing
            headers = [h.strip().strip('"').strip("'") for h in sample_lines[0].split(',')]
            sample_rows = sample_lines[1:]
            
            # Detect PII
            pii_results = evaluate_pii(sample_rows, headers)
            
            # Match to Glue table names (assumes table name is folder name in S3 paths)
            table_name = prefix.strip('/').split('/')[-1]
            print(f"🔍 Mapping detections to Glue Table: {db_name}.{table_name}")
            
            # Apply tags in Lake Formation
            for col_name, pii_type in pii_results.items():
                apply_lf_pii_tag(db_name, table_name, col_name, pii_type)
                
    except Exception as e:
        print(f"❌ Lambda execution error: {str(e)}")
        
    return {
        'statusCode': 200,
        'body': json.dumps('PII Inspection Completed')
    }
