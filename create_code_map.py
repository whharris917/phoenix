import ast
import os

# --- Configuration ---

# List of files to be included in the code map.
TARGET_FILES = [
    "app.py",
    "haven.py",
    "orchestrator.py",
    "tool_agent.py",
    "memory_manager.py",
    "response_parser.py",
    "proxies.py",
    "session_models.py",
    "data_models.py",
]

# The name of the output file that will be generated.
OUTPUT_FILE = "code_map_detailed.txt"

# --- Core Logic ---

class DetailedCodeVisitor(ast.NodeVisitor):
    """
    An AST node visitor that generates a detailed but high-level pseudocode
    map, including class/function signatures, docstrings, and return types.
    """

    def __init__(self, output_file):
        self.output_file = output_file
        self.indentation_level = 0

    def _write(self, content):
        """Writes a line to the output file with the current indentation."""
        indent = "    " * self.indentation_level
        self.output_file.write(f"{indent}{content}\n")

    def visit_ClassDef(self, node):
        """Handles class definitions, showing the name and docstring."""
        self._write(f"CLASS {node.name}:")
        self.indentation_level += 1

        docstring = ast.get_docstring(node)
        if docstring:
            self._write(f'"""{docstring.strip()}"""\n')

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.ClassDef)):
                self.visit(item)
        self.indentation_level -= 1
        self._write("")

    def visit_FunctionDef(self, node):
        """Handles function definitions, showing signature, return type, and docstring."""
        args = [arg.arg for arg in node.args.args]
        return_type = f" -> {ast.unparse(node.returns)}" if node.returns else ""

        prefix = "FUNCTION"
        if self.indentation_level > 0:
            prefix = "METHOD"

        self._write(f"{prefix} {node.name}({', '.join(args)}){return_type}:")
        self.indentation_level += 1

        docstring = ast.get_docstring(node)
        if docstring:
            self._write(f'"""{docstring.strip()}"""')

        self.indentation_level -= 1
        self._write("")

    def generic_visit(self, node):
        """Override to prevent traversing into function bodies."""
        pass

def generate_detailed_code_map():
    """
    Main function to generate the detailed code map from the target files.
    """
    print(f"Generating detailed code map at '{OUTPUT_FILE}'...")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# Phoenix Agent - Detailed Code Map\n")
        f.write(f"# Auto-generated on: {__import__('datetime').datetime.now()}\n")
        f.write("# This file provides a high-level architectural view of the project's logic.\n\n")

        for filename in TARGET_FILES:
            if not os.path.exists(filename):
                print(f"WARNING: File '{filename}' not found. Skipping.")
                continue

            print(f"Processing '{filename}'...")
            f.write(f"{'='*20} FILE: {filename} {'='*20}\n\n")

            with open(filename, "r", encoding="utf-8") as source_file:
                source_code = source_file.read()
                try:
                    tree = ast.parse(source_code)
                    visitor = DetailedCodeVisitor(f)
                    for node in tree.body:
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                            visitor.visit(node)
                except Exception as e:
                    f.write(f"ERROR: Could not parse {filename}. Reason: {e}\n\n")
            f.write("\n")

    print(f"\nDetailed code map successfully generated!")


if __name__ == "__main__":
    generate_detailed_code_map()
