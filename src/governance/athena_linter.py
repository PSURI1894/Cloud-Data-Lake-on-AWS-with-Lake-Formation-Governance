import re
import sys

class AthenaQueryLinter:
    """
    Scans and evaluates Athena SQL queries against operational cost rules
    and best practice guidelines to block or alert on expensive anti-patterns.
    """
    def __init__(self, sql_query):
        self.sql = sql_query.strip().lower()
        self.warnings = []

    def lint_wildcard_selection(self):
        """Rule 1: Flag SELECT * (forces full record scanning, blowing up budgets)"""
        # Match select * or select table.*
        if re.search(r'select\s+\*\s+', self.sql) or re.search(r'select\s+\w+\.\*\s+', self.sql):
            self.warnings.append({
                'code': 'L001',
                'rule': 'Wildcard Column Projection',
                'severity': 'WARNING',
                'description': "Ad-hoc 'SELECT *' scans all columns on S3 Parquet datasets. Project only required fields to minimize scanned bytes."
            })

    def lint_partition_pruning(self):
        """Rule 2: Flag lack of partition pruning filters (e.g. event_date, transaction_time)"""
        # If it scans transaction tables, check for partitions filters
        if 'transactions' in self.sql or 'fact_transactions' in self.sql:
            if 'event_date' not in self.sql and 'transaction_time' not in self.sql:
                self.warnings.append({
                    'code': 'L002',
                    'rule': 'Missing Partition Filtering',
                    'severity': 'CRITICAL',
                    'description': "Querying transactions without 'event_date' or 'transaction_time' filters forces a full table scan. Add date constraints to leverage hidden partition indexes."
                })

    def lint_regional_isolation(self):
        """Rule 3: Flag lack of regional filters on multi-tenant tables"""
        if 'customers' in self.sql or 'dim_customers' in self.sql:
            if 'region_code' not in self.sql and 'country' not in self.sql:
                self.warnings.append({
                    'code': 'L003',
                    'rule': 'Multi-Tenant Regional Leakage',
                    'severity': 'INFO',
                    'description': "Multi-tenant tables contain mixed regional datasets. Add 'region_code' constraints to prevent redundant multi-region planning costs."
                })

    def execute(self):
        self.lint_wildcard_selection()
        self.lint_partition_pruning()
        self.lint_regional_isolation()
        return self.warnings

def run_linter_cli():
    print("🛡️ Athena Governance Linter CLI Initialized")
    print("-" * 50)
    
    # Mock some queries to demonstrate
    test_queries = [
        "SELECT * FROM conformed_db.transactions WHERE event_date = '2026-05-18'",
        "SELECT customer_id, amount FROM conformed_db.transactions",
        "SELECT first_name, email FROM consumption_db.dim_customers WHERE region_code = 'APAC'",
        "SELECT * FROM conformed_db.transactions"
    ]
    
    for idx, q in enumerate(test_queries):
        print(f"\n📝 Query #{idx+1}: \"{q}\"")
        linter = AthenaQueryLinter(q)
        violations = linter.execute()
        
        if not violations:
            print("   ✅ Compliance Pass! Perfect execution plan.")
        else:
            for v in violations:
                print(f"   [{v['severity']}] {v['code']} - {v['rule']}")
                print(f"         👉 {v['description']}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Read file or direct query string arg
        query = " ".join(sys.argv[1:])
        linter = AthenaQueryLinter(query)
        res = linter.execute()
        for r in res:
            print(f"[{r['severity']}] {r['rule']}: {r['description']}")
    else:
        run_linter_cli()
