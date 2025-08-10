#!/usr/bin/env python3
"""
Simple Hierarchical Call Tree Generator

Generates clean hierarchical call trees showing function call relationships
in a tree format with proper Unicode box-drawing characters.
"""

import ast
import os
import sys
from typing import Dict, List, Set, Optional
from pathlib import Path
from collections import defaultdict

class CallTreeAnalyzer(ast.NodeVisitor):
    """AST visitor that builds function call relationships."""
    
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.current_function = None
        self.current_class = None
        self.call_graph: Dict[str, Set[str]] = defaultdict(set)
        self.all_functions: Set[str] = set()
        
    def visit_ClassDef(self, node):
        """Handle class definitions."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class
    
    def visit_FunctionDef(self, node):
        """Track function definitions and analyze their calls."""
        # Build full function name
        if self.current_class:
            full_name = f"{self.module_name}.{self.current_class}.{node.name}"
        else:
            full_name = f"{self.module_name}.{node.name}"
        
        self.all_functions.add(full_name)
        
        # Analyze function body for calls
        old_function = self.current_function
        self.current_function = full_name
        
        if full_name not in self.call_graph:
            self.call_graph[full_name] = set()
            
        self.generic_visit(node)
        self.current_function = old_function
    
    def visit_Call(self, node):
        """Track function calls."""
        if self.current_function:
            call_name = self._extract_call_name(node)
            if call_name and call_name != self.current_function:  # Avoid self-calls
                self.call_graph[self.current_function].add(call_name)
        self.generic_visit(node)
    
    def _extract_call_name(self, node) -> Optional[str]:
        """Extract the full name of a function call."""
        if not isinstance(node, ast.Call):
            return None
            
        func = node.func
        
        # Handle different call patterns
        if isinstance(func, ast.Name):
            # Simple function call: func()
            return func.id
        elif isinstance(func, ast.Attribute):
            # Method call: obj.method() or module.func()
            return self._extract_attribute_chain(func)
        else:
            return None
    
    def _extract_attribute_chain(self, node) -> str:
        """Extract full attribute chain like module.Class.method."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._extract_attribute_chain(node.value)
            return f"{base}.{node.attr}"
        else:
            return str(type(node).__name__)

class CallTreeGenerator:
    """Generates hierarchical call trees from analyzed code."""
    
    def __init__(self):
        self.call_graph: Dict[str, Set[str]] = {}
        self.all_functions: Set[str] = set()
    
    def analyze_files(self, file_paths: List[str]) -> None:
        """Analyze multiple Python files."""
        print("🔍 Analyzing files for call relationships...")
        print(f"🔧 Debug: Files to analyze: {file_paths}")
        
        for file_path in file_paths:
            print(f"🔧 Debug: Checking file: {file_path}")
            if os.path.exists(file_path):
                print(f"🔧 Debug: File exists: {file_path}")
                if file_path.endswith('.py'):
                    print(f"🔧 Debug: File is Python: {file_path}")
                    self._analyze_file(file_path)
                    print(f"  ✓ {file_path}")
                else:
                    print(f"🔧 Debug: File is not Python: {file_path}")
            else:
                print(f"🔧 Debug: File does not exist: {file_path}")
        
        total_calls = sum(len(calls) for calls in self.call_graph.values())
        print(f"📊 Found {len(self.all_functions)} functions with {total_calls} call relationships")
        
        if len(self.all_functions) == 0:
            print("⚠️  No functions found! This might indicate:")
            print("   - Files are empty or contain syntax errors")
            print("   - Files don't contain function definitions") 
            print("   - There's an issue with the AST parsing")
    
    def _analyze_file(self, file_path: str) -> None:
        """Analyze a single Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            module_name = Path(file_path).stem
            
            analyzer = CallTreeAnalyzer(module_name)
            analyzer.visit(tree)
            
            # Merge results
            self.all_functions.update(analyzer.all_functions)
            for func, calls in analyzer.call_graph.items():
                if func not in self.call_graph:
                    self.call_graph[func] = set()
                self.call_graph[func].update(calls)
                
        except Exception as e:
            print(f"⚠️  Error analyzing {file_path}: {e}")
    
    def generate_call_tree(self, root_function: str, max_depth: int = 5) -> List[str]:
        """Generate a hierarchical call tree starting from a root function."""
        if root_function not in self.call_graph:
            return [f"{root_function} [NOT FOUND]"]
        
        lines = []
        self._build_tree_recursive(root_function, lines, "", set(), max_depth)
        return lines
    
    def _build_tree_recursive(self, function: str, lines: List[str], prefix: str, visited: Set[str], depth: int) -> None:
        """Recursively build the call tree with proper Unicode characters."""
        if depth <= 0 or function in visited:
            if function in visited:
                lines.append(f"{prefix}[CIRCULAR: {function}]")
            return
        
        visited.add(function)
        
        # Add current function
        lines.append(f"{prefix}{function}")
        
        # Get called functions
        called_functions = sorted(self.call_graph.get(function, set()))
        
        # Draw tree branches
        for i, called_func in enumerate(called_functions):
            is_last = (i == len(called_functions) - 1)
            
            if is_last:
                # Last child: └──
                child_prefix = prefix + "└── "
                continuation_prefix = prefix + "    "
            else:
                # Not last child: ├──
                child_prefix = prefix + "├── "
                continuation_prefix = prefix + "│   "
            
            # Add the called function
            if called_func in self.all_functions:
                # It's a function we know about, recurse
                lines.append(f"{child_prefix}{called_func}")
                self._build_tree_recursive(called_func, lines, continuation_prefix, visited.copy(), depth - 1)
            else:
                # External function
                lines.append(f"{child_prefix}{called_func} [EXTERNAL]")
        
        visited.remove(function)
    
    def find_entry_points(self) -> List[str]:
        """Find potential entry point functions (called by few others)."""
        call_counts = defaultdict(int)
        
        # Count how many times each function is called
        for caller, callees in self.call_graph.items():
            for callee in callees:
                call_counts[callee] += 1
        
        # Find functions that are called 0-1 times (potential entry points)
        entry_points = []
        for func in self.all_functions:
            if call_counts[func] <= 1:
                entry_points.append(func)
        
        # Sort by module and function name
        return sorted(entry_points)
    
    def generate_all_trees(self, max_depth: int = 4) -> str:
        """Generate call trees for all entry points."""
        entry_points = self.find_entry_points()
        
        lines = ["# Hierarchical Call Trees", ""]
        lines.append(f"Generated from static analysis. Found {len(entry_points)} potential entry points.")
        lines.append("")
        
        for entry_point in entry_points:
            lines.append(f"## {entry_point}")
            lines.append("```")
            tree_lines = self.generate_call_tree(entry_point, max_depth)
            lines.extend(tree_lines)
            lines.append("```")
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_specific_trees(self, functions: List[str], max_depth: int = 4) -> str:
        """Generate call trees for specific functions."""
        lines = ["# Hierarchical Call Trees", ""]
        
        for function in functions:
            lines.append(f"## {function}")
            lines.append("```")
            tree_lines = self.generate_call_tree(function, max_depth)
            lines.extend(tree_lines)
            lines.append("```")
            lines.append("")
        
        return "\n".join(lines)
    
    def print_function_list(self) -> None:
        """Print all discovered functions for reference."""
        print("\n📋 All discovered functions:")
        by_module = defaultdict(list)
        
        for func in sorted(self.all_functions):
            module = func.split('.')[0]
            by_module[module].append(func)
        
        for module in sorted(by_module.keys()):
            print(f"\n{module}.py:")
            for func in by_module[module]:
                call_count = len(self.call_graph.get(func, set()))
                print(f"  {func} ({call_count} calls)")

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python call_tree_generator.py <file1.py> <file2.py> ... [--function FUNC] [--depth N]")
        print("")
        print("Examples:")
        print("  python call_tree_generator.py phoenix.py events.py haven.py")
        print("  python call_tree_generator.py phoenix.py events.py --function events.handle_connect")
        print("  python call_tree_generator.py phoenix.py events.py --function phoenix.__main__ --depth 6")
        sys.exit(1)
    
    # Debug: Print all command line arguments
    print(f"🔧 Debug: Command line arguments: {sys.argv}")
    
    # Parse arguments
    file_paths = []
    specific_function = None
    max_depth = 4
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        print(f"🔧 Debug: Processing argument: '{arg}'")
        
        if arg == '--function':
            if i + 1 < len(sys.argv):
                specific_function = sys.argv[i + 1]
                i += 2
            else:
                print("Error: --function requires a function name")
                sys.exit(1)
        elif arg == '--depth':
            if i + 1 < len(sys.argv):
                try:
                    max_depth = int(sys.argv[i + 1])
                    i += 2
                except ValueError:
                    print("Error: --depth requires an integer")
                    sys.exit(1)
            else:
                print("Error: --depth requires an integer")
                sys.exit(1)
        elif arg.endswith('.py') or '*' in arg:
            # Handle wildcards by expanding them
            if '*' in arg:
                import glob
                expanded_files = glob.glob(arg)
                print(f"🔧 Debug: Wildcard '{arg}' expanded to: {expanded_files}")
                file_paths.extend(expanded_files)
            else:
                file_paths.append(arg)
            i += 1
        else:
            # Assume it's a file path even if it doesn't end in .py
            if os.path.exists(arg):
                file_paths.append(arg)
                print(f"🔧 Debug: Added existing file: {arg}")
            else:
                print(f"⚠️  Warning: File not found: {arg}")
            i += 1
    
    print(f"🔧 Debug: Final file paths to analyze: {file_paths}")
    
    if not file_paths:
        print("Error: No Python files found to analyze")
        print("🔧 Debug: Try specifying files explicitly:")
        print("  python call_tree_generator.py phoenix.py events.py haven.py orchestrator.py")
        sys.exit(1)
    
    # Generate call trees
    generator = CallTreeGenerator()
    generator.analyze_files(file_paths)
    
    # Show function list for reference
    generator.print_function_list()
    
    if specific_function:
        # Generate tree for specific function
        content = generator.generate_specific_trees([specific_function], max_depth)
        print(f"\n🌳 Call tree for {specific_function}:")
        print("=" * 50)
        tree_lines = generator.generate_call_tree(specific_function, max_depth)
        for line in tree_lines:
            print(line)
    else:
        # Generate trees for all entry points
        content = generator.generate_all_trees(max_depth)
        
        # Save to file
        output_file = "call_trees.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n📝 Call trees saved to: {output_file}")

if __name__ == "__main__":
    main()