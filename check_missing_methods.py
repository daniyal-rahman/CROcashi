"""
Comprehensive check for missing methods across the codebase.
"""
import sys
from pathlib import Path
import ast
import importlib.util

sys.path.insert(0, str(Path(__file__).parent))

def find_method_calls(file_path):
    """Find all method calls in a Python file."""
    with open(file_path, 'r') as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError:
            return []
    
    method_calls = []
    
    class MethodCallVisitor(ast.NodeVisitor):
        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute):
                method_calls.append(node.func.attr)
            self.generic_visit(node)
    
    visitor = MethodCallVisitor()
    visitor.visit(tree)
    return method_calls

def find_method_definitions(file_path):
    """Find all method definitions in a Python file."""
    with open(file_path, 'r') as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError:
            return []
    
    methods = []
    
    class MethodDefVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            methods.append(node.name)
            self.generic_visit(node)
    
    visitor = MethodDefVisitor()
    visitor.visit(tree)
    return methods

def check_file(file_path):
    """Check a file for potentially missing methods."""
    if not file_path.exists():
        return None
    
    calls = find_method_calls(file_path)
    definitions = find_method_definitions(file_path)
    
    # Filter to self. and BaseProcessor. calls
    self_calls = [c for c in calls if c.startswith('_') or c in ['normalize', 'extract', 'get', 'add', 'reset']]
    
    # Check for calls that might be missing
    potentially_missing = []
    for call in self_calls:
        if call not in definitions and call not in ['normalize_company_name', 'normalize_drug_name', 
                                                     'extract_date_from_raw', 'get_metrics', 'reset_metrics',
                                                     'add_warning', 'add_error', 'validate_extraction']:
            # Check if it's a self. call (would need class context to verify)
            potentially_missing.append(call)
    
    return {
        'file': str(file_path),
        'definitions': definitions,
        'potentially_missing': potentially_missing
    }

# Check critical files
critical_files = [
    Path('src/processors/sec_filings_processor.py'),
    Path('src/processors/clinicaltrials_processor.py'),
    Path('src/entity_resolution/relationship_builder.py'),
    Path('src/processing/pipeline.py'),
]

print("Checking for potentially missing methods:")
print("="*70)

for file_path in critical_files:
    result = check_file(file_path)
    if result:
        if result['potentially_missing']:
            print(f"\n{file_path.name}:")
            for method in result['potentially_missing'][:10]:  # Limit output
                print(f"  ⚠️  {method} (called but not defined in this file)")
        else:
            print(f"\n{file_path.name}: ✅ No obvious missing methods")

