import ast
import json
import os

# --- Configuration ---
try:
    # Import the list of files directly from the project's config
    from config import ALLOWED_PROJECT_FILES
except ImportError:
    print("Error: Could not import 'ALLOWED_PROJECT_FILES' from config.py.")
    print("Please ensure config.py is in the same directory or accessible in the Python path.")
    ALLOWED_PROJECT_FILES = []

OUTPUT_FILE = "code_map.json"

class CodeMapVisitor(ast.NodeVisitor):
    """
    An AST visitor that walks the code's structure to identify classes,
    functions, variables, and their associated type information.
    """
    def __init__(self):
        self.module_map = {
            "classes": {},
            "public_functions": [],
            "private_functions": [],
            "global_variables": []
        }
        self.current_class_name = None

    def _format_arg(self, arg_node):
        """Formats an argument node into a 'name: type' string."""
        arg_name = arg_node.arg
        arg_type = "Any"
        if arg_node.annotation:
            arg_type = ast.unparse(arg_node.annotation)
        return f"{arg_name}: {arg_type}"

    def visit_ClassDef(self, node):
        """Handle class definitions, including their methods and attributes."""
        self.current_class_name = node.name
        self.module_map["classes"][self.current_class_name] = {
            "attributes": [],
            "public_methods": [],
            "private_methods": []
        }
        # Visit children to populate methods and attributes
        self.generic_visit(node)
        self.current_class_name = None

    def visit_FunctionDef(self, node):
        """Categorize functions/methods and extract their signature."""
        args = [self._format_arg(arg) for arg in node.args.args]
        returns = ast.unparse(node.returns) if node.returns else "None"

        func_info = {
            "name": node.name,
            "args": args,
            "returns": returns
        }

        # Check if it's a method within a class
        if self.current_class_name:
            if node.name.startswith('_'):
                self.module_map["classes"][self.current_class_name]["private_methods"].append(func_info)
            else:
                self.module_map["classes"][self.current_class_name]["public_methods"].append(func_info)
        # Otherwise, it's a module-level function
        else:
            if node.name.startswith('_'):
                self.module_map["private_functions"].append(func_info)
            else:
                self.module_map["public_functions"].append(func_info)

    def visit_Assign(self, node):
        """Handle untyped variable/attribute assignments."""
        var_info = {
            "name": ast.unparse(node.targets[0]),
            "type": "Any" # Type inference is unreliable, so we default to Any
        }
        if self.current_class_name:
             # This is a simple heuristic; it may capture variables inside methods too.
             # A more complex analysis would be needed to distinguish instance vs. local variables.
            self.module_map["classes"][self.current_class_name]["attributes"].append(var_info)
        else:
            self.module_map["global_variables"].append(var_info)

    def visit_AnnAssign(self, node):
        """Handle typed variable/attribute assignments (e.g., x: int = 5)."""
        var_info = {
            "name": ast.unparse(node.target),
            "type": ast.unparse(node.annotation)
        }
        if self.current_class_name:
            self.module_map["classes"][self.current_class_name]["attributes"].append(var_info)
        else:
            self.module_map["global_variables"].append(var_info)

def create_code_map():
    """
    Main function to analyze all project files and generate the code map JSON.
    """
    print(f"Generating code map for project files...")
    project_code_map = {}

    python_files = [f for f in ALLOWED_PROJECT_FILES if f.endswith(".py")]

    for filename in python_files:
        if not os.path.exists(filename):
            print(f"WARNING: File '{filename}' not found. Skipping.")
            continue

        print(f"  -> Analyzing '{filename}'...")
        with open(filename, "r", encoding="utf-8") as source_file:
            try:
                source_code = source_file.read()
                tree = ast.parse(source_code)
                
                visitor = CodeMapVisitor()
                visitor.visit(tree)
                
                # Clean up duplicate attributes that might be captured
                for class_name, class_data in visitor.module_map["classes"].items():
                    unique_attrs = {d['name']: d for d in class_data['attributes']}.values()
                    class_data['attributes'] = sorted(list(unique_attrs), key=lambda x: x['name'])

                project_code_map[filename] = visitor.module_map

            except Exception as e:
                print(f"ERROR: Could not parse {filename}. Reason: {e}")
                project_code_map[filename] = {"error": f"Could not parse file: {e}"}

    # --- Write the output file ---
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(project_code_map, f, indent=2)

    print(f"\nCode map successfully generated at '{OUTPUT_FILE}'")

if __name__ == "__main__":
    create_code_map()
