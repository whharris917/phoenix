import os
import ast
import json


class CodeVisitor(ast.NodeVisitor):
    """
    An AST visitor that extracts information about functions, classes, and imports.
    """

    def __init__(self, file_path):
        self.file_path = file_path
        self.imports = set()
        self.functions = []
        self.classes = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        # We only care about local project imports for the dependency map.
        # A simple heuristic is to check if the import is relative (starts with '.').
        if node.level > 0:  # Relative import
            # Attempt to resolve the relative path
            # For a level 1 import (from . import x), the module is in the same dir.
            # For a level 2 import (from .. import x), it's in the parent dir.
            # This is a simplified resolver.
            base_path = os.path.dirname(self.file_path)
            for _ in range(node.level - 1):
                base_path = os.path.dirname(base_path)

            module_path = os.path.join(base_path, node.module).replace(os.sep, ".") if node.module else base_path.replace(os.sep, ".")
            self.imports.add(module_path)
        # We can also add non-relative imports if they are from our own project files
        elif node.module and node.module.split(".")[0] in [os.path.splitext(f)[0] for f in os.listdir(".") if f.endswith(".py")]:
            self.imports.add(node.module)

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Extracts information from a function definition."""
        self.functions.append({"name": node.name, "args": [arg.arg for arg in node.args.args], "docstring": ast.get_docstring(node)})
        self.generic_visit(node)  # Visit nodes inside the function

    def visit_ClassDef(self, node):
        """Extracts information from a class definition."""
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append({"name": item.name, "args": [arg.arg for arg in item.args.args], "docstring": ast.get_docstring(item)})
        self.classes.append({"name": node.name, "methods": methods, "docstring": ast.get_docstring(node)})
        # Don't call generic_visit on the class body to avoid double-counting methods as functions
        # self.generic_visit(node)


def parse_module(file_path: str) -> dict | None:
    """
    Parses a single Python file and returns a dictionary of its contents.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content, filename=file_path)

        visitor = CodeVisitor(file_path)
        visitor.visit(tree)

        # Normalize paths for consistency
        normalized_path = file_path.replace(os.sep, "/")

        return {
            "path": normalized_path,
            "summary": ast.get_docstring(tree),
            "imports": sorted(list(visitor.imports)),
            "functions": visitor.functions,
            "classes": visitor.classes,
        }
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


def generate_map(root_dir: str, output_file: str):
    """
    Walks a directory, parses all Python files, and generates the code map.
    """
    code_map = {"modules": []}

    # Directories to exclude from the scan
    exclude_dirs = {".git", ".venv", "__pycache__", ".sandbox"}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Modify dirnames in-place to prevent os.walk from descending into excluded dirs
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        for filename in filenames:
            if filename.endswith(".py"):
                file_path = os.path.join(dirpath, filename)
                module_data = parse_module(file_path)
                if module_data:
                    code_map["modules"].append(module_data)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(code_map, f, indent=2)

    print(f"Successfully generated code map at '{output_file}'")


if __name__ == "__main__":
    # Assumes the script is run from the project's root directory
    generate_map(root_dir=".", output_file="code_map.json")
