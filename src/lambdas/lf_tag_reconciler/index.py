import json
import boto3
import yaml
import os

lf = boto3.client('lakeformation')
glue = boto3.client('glue')

def load_policy():
    """Loads tag policy configuration from local yaml file"""
    policy_path = os.path.join(os.path.dirname(__file__), '../../governance/tag_policy.yaml')
    with open(policy_path, 'r') as f:
        return yaml.safe_load(f)

def get_current_tags(db_name, table_name, column_name=None):
    """Retrieves current LF tags assigned to a table or column"""
    try:
        resource = {
            'Table': {
                'DatabaseName': db_name,
                'Name': table_name
            }
        }
        if column_name:
            resource = {
                'TableWithColumns': {
                    'DatabaseName': db_name,
                    'Name': table_name,
                    'ColumnNames': [column_name]
                }
            }
            
        response = lf.get_resource_lf_tags(Resource=resource)
        # Parse tags
        tags = {}
        tag_list = response.get('LFTagOnDatabase', []) if not column_name else response.get('LFTagsOnColumns', [{}])[0].get('LFTags', [])
        for t in tag_list:
            tags[t['TagKey']] = t['TagValues'][0]
        return tags
    except Exception as e:
        print(f"⚠️ Error getting tags for {db_name}.{table_name}: {str(e)}")
        return {}

def assign_tag(db_name, table_name, tag_key, tag_value, column_name=None):
    """Assigns an LF tag to a table or column in Lake Formation"""
    resource = {
        'Table': {
            'DatabaseName': db_name,
            'Name': table_name
        }
    }
    if column_name:
        resource = {
            'TableWithColumns': {
                'DatabaseName': db_name,
                'Name': table_name,
                'ColumnNames': [column_name]
            }
        }

    try:
        print(f"🏷️ Assigning LF Tag {tag_key}={tag_value} to {db_name}.{table_name}" + (f" (column: {column_name})" if column_name else ""))
        lf.add_lftags_to_resource(
            Resource=resource,
            LFTags=[{
                'TagKey': tag_key,
                'TagValues': [tag_value]
            }]
        )
    except Exception as e:
        print(f"❌ Error adding tag to {db_name}.{table_name}: {str(e)}")

def lambda_handler(event, context):
    print("🚀 Lake Formation Tag Reconciler Lambda Triggered")
    policy = load_policy()
    db_policies = policy.get('database_policies', {})
    
    drifts_detected = []
    
    for db_name, db_policy in db_policies.items():
        print(f"🔍 Analyzing Database: {db_name}")
        tables_policy = db_policy.get('tables', {})
        
        # List tables in Glue catalog database
        try:
            paginator = glue.get_paginator('get_tables')
            pages = paginator.paginate(DatabaseName=db_name)
            
            for page in pages:
                for table in page['TableList']:
                    table_name = table['Name']
                    print(f"   📊 Scanning Table: {table_name}")
                    
                    # Fetch expected policy
                    t_policy = tables_policy.get(table_name, {})
                    expected_bu = t_policy.get('bu', db_policy.get('bu', 'operations'))
                    expected_sensitivity = t_policy.get('sensitivity', db_policy.get('default_sensitivity', 'internal'))
                    
                    # Fetch current tags
                    current_tags = get_current_tags(db_name, table_name)
                    
                    # Reconcile BU Tag
                    if current_tags.get('BU') != expected_bu:
                        assign_tag(db_name, table_name, 'BU', expected_bu)
                        drifts_detected.append({
                            'database': db_name, 'table': table_name, 'tag': 'BU',
                            'old': current_tags.get('BU'), 'new': expected_bu
                        })
                        
                    # Reconcile Sensitivity Tag
                    if current_tags.get('Sensitivity') != expected_sensitivity:
                        assign_tag(db_name, table_name, 'Sensitivity', expected_sensitivity)
                        drifts_detected.append({
                            'database': db_name, 'table': table_name, 'tag': 'Sensitivity',
                            'old': current_tags.get('Sensitivity'), 'new': expected_sensitivity
                        })
                        
                    # Reconcile Columns PII
                    columns_policy = t_policy.get('columns', {})
                    for col_obj in table.get('StorageDescriptor', {}).get('Columns', []):
                        col_name = col_obj['Name']
                        c_policy = columns_policy.get(col_name, {})
                        expected_pii = c_policy.get('pii', db_policy.get('default_pii', 'none'))
                        
                        col_tags = get_current_tags(db_name, table_name, col_name)
                        if col_tags.get('PII') != expected_pii:
                            assign_tag(db_name, table_name, 'PII', expected_pii, col_name)
                            drifts_detected.append({
                                'database': db_name, 'table': table_name, 'column': col_name,
                                'tag': 'PII', 'old': col_tags.get('PII'), 'new': expected_pii
                            })
                            
        except Exception as e:
            print(f"❌ Error scanning Glue DB {db_name}: {str(e)}")
            
    print(f"🏁 Reconciler complete. Drifts resolved: {len(drifts_detected)}")
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Reconciliation Complete',
            'drifts_resolved': drifts_detected
        })
    }
