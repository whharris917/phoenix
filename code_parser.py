import ast
import os

class FunctionCallVisitor(ast.NodeVisitor):
    """An AST visitor to find all function calls within a function."""
    def __init__(self):
        self.calls = []

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        self.generic_visit(node)

def analyze_codebase(file_paths):
    """
    Analyzes a list of Python files to map function definitions and their calls.
    Returns a dictionary representing the code structure.
    """
    structure = {}
    for file_path in file_paths:
        file_name = os.path.basename(file_path)
        structure[file_name] = []
        with open(file_path, 'r') as f:
            try:
                tree = ast.parse(f.read(), filename=file_name)
            except SyntaxError as e:
                print(f"Could not parse {file_name}: {e}")
                continue

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                visitor = FunctionCallVisitor()
                visitor.visit(node)
                function_data = {
                    'name': node.name,
                    'calls': visitor.calls
                }
                structure[file_name].append(function_data)
                
    return structure

def generate_mermaid_diagram(structure):
    """
    Generates a Mermaid.js flowchart syntax from the code structure.
    """
    mermaid_string = "graph TD\n\n"
    
    # Define subgraphs for each file
    for file_name, functions in structure.items():
        mermaid_string += f"    subgraph {os.path.splitext(file_name)[0]}\n"
        for func in functions:
            mermaid_string += f"        {func['name']}\n"
        mermaid_string += "    end\n\n"

    # Define the links between functions
    for file_name, functions in structure.items():
        for func_data in functions:
            caller_name = func_data['name']
            for called_name in func_data['calls']:
                # Check if the called function exists in our structure
                if any(called_name == f['name'] for fns in structure.values() for f in fns):
                    mermaid_string += f"    {caller_name} --> {called_name}\n"
    
    return mermaid_string

if __name__ == '__main__':
    # This part is for standalone testing of the parser
    project_files = [
        'app.py',
        'orchestrator.py',
        'tool_agent.py'
    ]
    
    # Create dummy files for testing if they don't exist
    for f in project_files:
        if not os.path.exists(f):
            with open(f, 'w') as temp_file:
                temp_file.write("def dummy_function():\n    pass\n")

    code_structure = analyze_codebase(project_files)
    mermaid_code = generate_mermaid_diagram(code_structure)
    
    print("--- Code Structure ---")
    import json
    print(json.dumps(code_structure, indent=2))
    
    print("\n--- Mermaid.js Diagram Code ---")
    print(mermaid_code)
