#!/usr/bin/env python3
"""
Programmatic Function Atlas Generator

Generates a concise function-level navigation atlas by parsing Python files
for docstrings, type hints, and call relationships. Designed to create an
AI-agent-friendly codebase map automatically.
"""

import ast
import os
import sys
import inspect
from typing import Dict, List, Set, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import json
import re

@dataclass
class FunctionData:
    """Data structure for a single function's information."""
    name: str
    full_name: str  # module.function or module.Class.function
    file_path: str
    line_number: int
    docstring: Optional[str] = None
    type_hints: Dict[str, str] = field(default_factory=dict)
    calls_made: Set[str] = field(default_factory=set)
    called_by: Set[str] = field(default_factory=set)
    complexity_score: int = 0
    is_entry_point: bool = False
    is_critical: bool = False
    parameters: List[str] = field(default_factory=list)
    returns: Optional[str] = None
    decorators: List[str] = field(default_factory=list)

@dataclass
class CallHierarchy:
    """Represents a hierarchical call tree."""
    function_name: str
    calls: List['CallHierarchy'] = field(default_factory=list)
    depth: int = 0

class StaticAtlasGenerator:
    """Generates function atlas through static code analysis."""
    
    def __init__(self):
        self.functions: Dict[str, FunctionData] = {}
        self.modules: Dict[str, str] = {}  # module_name -> file_path
        self.call_graph: Dict[str, Set[str]] = {}  # caller -> callees
        self.reverse_call_graph: Dict[str, Set[str]] = {}  # callee -> callers
        
    def analyze_files(self, file_paths: List[str]) -> None:
        """Analyze multiple Python files and build the complete function database."""
        print("📊 Analyzing Python files...")
        
        for file_path in file_paths:
            if os.path.exists(file_path) and file_path.endswith('.py'):
                self._analyze_single_file(file_path)
                print(f"  ✓ {file_path}")
        
        self._build_call_relationships()
        self._calculate_complexity_scores()
        self._identify_entry_points_and_critical_functions()
        
        print(f"📈 Analysis complete: {len(self.functions)} functions found")
    
    def _analyze_single_file(self, file_path: str) -> None:
        """Analyze a single Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            module_name = Path(file_path).stem
            self.modules[module_name] = file_path
            
            analyzer = FileAnalyzer(module_name, file_path, self.functions, self.call_graph)
            analyzer.visit(tree)
            
        except Exception as e:
            print(f"⚠️  Error analyzing {file_path}: {e}")
    
    def _build_call_relationships(self) -> None:
        """Build reverse call graph and update function call relationships."""
        for caller, callees in self.call_graph.items():
            if caller in self.functions:
                self.functions[caller].calls_made.update(callees)
            
            for callee in callees:
                if callee not in self.reverse_call_graph:
                    self.reverse_call_graph[callee] = set()
                self.reverse_call_graph[callee].add(caller)
                
                if callee in self.functions:
                    self.functions[callee].called_by.add(caller)
    
    def _calculate_complexity_scores(self) -> None:
        """Calculate complexity scores based on calls made/received."""
        for func_name, func_data in self.functions.items():
            # Base complexity on number of calls made and received
            calls_out = len(func_data.calls_made)
            calls_in = len(func_data.called_by)
            func_data.complexity_score = calls_out * 2 + calls_in
    
    def _identify_entry_points_and_critical_functions(self) -> None:
        """Identify entry points and critical functions based on call patterns."""
        # Entry points: functions with few callers but make many calls
        # Critical functions: functions called by many others
        
        for func_name, func_data in self.functions.items():
            calls_in = len(func_data.called_by)
            calls_out = len(func_data.calls_made)
            
            # Entry point heuristics
            if (calls_out > 3 and calls_in <= 1) or func_name.endswith('.__main__'):
                func_data.is_entry_point = True
            
            # Critical function heuristics  
            if calls_in >= 3 or calls_out >= 5:
                func_data.is_critical = True
    
    def generate_function_directory(self) -> str:
        """Generate the function directory section of the atlas."""
        lines = ["# FUNCTION DIRECTORY", ""]
        
        # Group functions by module
        by_module = {}
        for func_name, func_data in self.functions.items():
            module = func_name.split('.')[0]
            if module not in by_module:
                by_module[module] = []
            by_module[module].append(func_data)
        
        for module_name in sorted(by_module.keys()):
            lines.append(f"## {module_name}.py")
            lines.append("")
            
            functions = sorted(by_module[module_name], key=lambda x: x.line_number)
            
            for func in functions:
                # Function signature with indicators
                indicators = []
                if func.is_entry_point:
                    indicators.append("🚀ENTRY")
                if func.is_critical:
                    indicators.append("⚡CRITICAL")
                if func.complexity_score > 10:
                    indicators.append("🔴HIGH-RISK")
                
                indicator_str = " ".join(indicators)
                if indicator_str:
                    indicator_str = f" [{indicator_str}]"
                
                lines.append(f"**{func.full_name}**{indicator_str}")
                
                # Add docstring summary (first line only)
                if func.docstring:
                    first_line = func.docstring.split('\n')[0].strip()
                    if first_line:
                        lines.append(f"  {first_line}")
                
                # Add type signature if available
                if func.parameters or func.returns:
                    params_str = ", ".join(func.parameters)
                    return_str = f" -> {func.returns}" if func.returns else ""
                    lines.append(f"  `({params_str}){return_str}`")
                
                # Add call statistics
                calls_out = len(func.calls_made)
                calls_in = len(func.called_by)
                lines.append(f"  Calls: {calls_out} out, {calls_in} in | Complexity: {func.complexity_score}")
                
                lines.append("")
        
        return "\n".join(lines)
    
    def generate_hierarchical_call_trees(self, max_depth: int = 4) -> str:
        """Generate hierarchical call trees for entry points."""
        lines = ["# HIERARCHICAL CALL TREES", ""]
        
        # Get entry points
        entry_points = [f for f in self.functions.values() if f.is_entry_point]
        entry_points.sort(key=lambda x: x.full_name)
        
        for entry_func in entry_points:
            lines.append(f"## {entry_func.full_name}")
            if entry_func.docstring:
                first_line = entry_func.docstring.split('\n')[0].strip()
                lines.append(f"*{first_line}*")
            lines.append("```")
            
            hierarchy = self._build_call_hierarchy(entry_func.full_name, max_depth)
            tree_lines = self._format_call_hierarchy(hierarchy)
            lines.extend(tree_lines)
            
            lines.append("```")
            lines.append("")
        
        return "\n".join(lines)
    
    def _build_call_hierarchy(self, func_name: str, max_depth: int, visited: Set[str] = None) -> CallHierarchy:
        """Build hierarchical call tree for a function."""
        if visited is None:
            visited = set()
        
        if func_name in visited or max_depth <= 0:
            return CallHierarchy(func_name, [])
        
        visited.add(func_name)
        hierarchy = CallHierarchy(func_name)
        
        if func_name in self.functions:
            calls_made = self.functions[func_name].calls_made
            for called_func in sorted(calls_made):
                if called_func in self.functions:  # Only include functions we know about
                    sub_hierarchy = self._build_call_hierarchy(called_func, max_depth - 1, visited.copy())
                    hierarchy.calls.append(sub_hierarchy)
        
        return hierarchy
    
    def _format_call_hierarchy(self, hierarchy: CallHierarchy, depth: int = 0) -> List[str]:
        """Format call hierarchy into indented text."""
        lines = []
        indent = "  " * depth
        
        # Add function info
        if hierarchy.function_name in self.functions:
            func = self.functions[hierarchy.function_name]
            complexity_indicator = ""
            if func.complexity_score > 10:
                complexity_indicator = " [HIGH-RISK]"
            elif func.is_critical:
                complexity_indicator = " [CRITICAL]"
            
            lines.append(f"{indent}{hierarchy.function_name}{complexity_indicator}")
        else:
            lines.append(f"{indent}{hierarchy.function_name} [EXTERNAL]")
        
        # Add children
        for call in hierarchy.calls:
            lines.extend(self._format_call_hierarchy(call, depth + 1))
        
        return lines
    
    def generate_navigation_guide(self) -> str:
        """Generate task-based navigation guide."""
        lines = ["# NAVIGATION GUIDE", ""]
        
        # Find patterns in function names and docstrings to create categories
        categories = {
            "Bootstrap & Initialization": [],
            "Client Communication": [],
            "Core Logic & AI": [],
            "Tool Execution": [],
            "Data & Memory": [],
            "Parsing & Processing": [],
            "Utilities": []
        }
        
        for func_name, func_data in self.functions.items():
            doc = func_data.docstring or ""
            name_lower = func_name.lower()
            
            # Categorization heuristics based on naming and docstrings
            if any(word in name_lower for word in ['init', 'start', 'configure', 'connect', 'bootstrap']):
                categories["Bootstrap & Initialization"].append(func_data)
            elif any(word in name_lower for word in ['handle', 'emit', 'client', 'socket', 'event']):
                categories["Client Communication"].append(func_data)
            elif any(word in name_lower for word in ['reason', 'loop', 'process', 'model', 'agent', 'orchestrat']):
                categories["Core Logic & AI"].append(func_data)
            elif any(word in name_lower for word in ['tool', 'execute', 'handle_', 'command']):
                categories["Tool Execution"].append(func_data)
            elif any(word in name_lower for word in ['memory', 'store', 'db', 'data', 'persist']):
                categories["Data & Memory"].append(func_data)
            elif any(word in name_lower for word in ['parse', 'extract', 'format', 'clean']):
                categories["Parsing & Processing"].append(func_data)
            else:
                categories["Utilities"].append(func_data)
        
        for category, funcs in categories.items():
            if funcs:
                lines.append(f"## {category}")
                funcs.sort(key=lambda x: (x.complexity_score, x.full_name), reverse=True)
                
                for func in funcs[:5]:  # Top 5 per category
                    risk_level = "🔴" if func.complexity_score > 10 else "🟡" if func.complexity_score > 5 else "🟢"
                    lines.append(f"{risk_level} **{func.full_name}**")
                    if func.docstring:
                        first_line = func.docstring.split('\n')[0].strip()
                        lines.append(f"   {first_line}")
                    lines.append("")
        
        return "\n".join(lines)
    
    def generate_atlas(self) -> str:
        """Generate the complete function atlas."""
        sections = [
            "# Phoenix Project - Programmatically Generated Function Atlas",
            "",
            "Generated from static code analysis of docstrings, type hints, and call relationships.",
            "",
            self.generate_function_directory(),
            "",
            self.generate_hierarchical_call_trees(),
            "",
            self.generate_navigation_guide()
        ]
        
        return "\n".join(sections)
    
    def export_json(self) -> Dict[str, Any]:
        """Export atlas data as structured JSON."""
        return {
            "functions": {
                name: {
                    "full_name": func.full_name,
                    "file_path": func.file_path,
                    "line_number": func.line_number,
                    "docstring": func.docstring,
                    "type_hints": func.type_hints,
                    "calls_made": list(func.calls_made),
                    "called_by": list(func.called_by),
                    "complexity_score": func.complexity_score,
                    "is_entry_point": func.is_entry_point,
                    "is_critical": func.is_critical,
                    "parameters": func.parameters,
                    "returns": func.returns,
                    "decorators": func.decorators
                }
                for name, func in self.functions.items()
            },
            "call_graph": {k: list(v) for k, v in self.call_graph.items()},
            "modules": self.modules
        }

class FileAnalyzer(ast.NodeVisitor):
    """AST visitor that extracts function information from a single file."""
    
    def __init__(self, module_name: str, file_path: str, functions: Dict[str, FunctionData], call_graph: Dict[str, Set[str]]):
        self.module_name = module_name
        self.file_path = file_path
        self.functions = functions
        self.call_graph = call_graph
        self.current_class = None
        self.current_function = None
        
    def visit_ClassDef(self, node):
        """Handle class definitions."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class
    
    def visit_FunctionDef(self, node):
        """Extract function information."""
        # Build full function name
        if self.current_class:
            full_name = f"{self.module_name}.{self.current_class}.{node.name}"
        else:
            full_name = f"{self.module_name}.{node.name}"
        
        # Extract type hints
        type_hints = {}
        parameters = []
        
        for arg in node.args.args:
            param_name = arg.arg
            parameters.append(param_name)
            if arg.annotation:
                type_hints[param_name] = self._extract_annotation(arg.annotation)
        
        returns = None
        if node.returns:
            returns = self._extract_annotation(node.returns)
        
        # Create function data
        func_data = FunctionData(
            name=node.name,
            full_name=full_name,
            file_path=self.file_path,
            line_number=node.lineno,
            docstring=ast.get_docstring(node),
            type_hints=type_hints,
            parameters=parameters,
            returns=returns,
            decorators=[self._extract_name(dec) for dec in node.decorator_list]
        )
        
        self.functions[full_name] = func_data
        self.call_graph[full_name] = set()
        
        # Analyze function body for calls
        old_function = self.current_function
        self.current_function = full_name
        self.generic_visit(node)
        self.current_function = old_function
    
    def visit_Call(self, node):
        """Track function calls."""
        if self.current_function:
            call_name = self._extract_call_name(node)
            if call_name:
                self.call_graph[self.current_function].add(call_name)
        self.generic_visit(node)
    
    def _extract_annotation(self, node) -> str:
        """Extract type annotation as string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._extract_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            value = self._extract_name(node.value)
            slice_val = self._extract_name(node.slice)
            return f"{value}[{slice_val}]"
        else:
            return ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
    
    def _extract_name(self, node) -> str:
        """Extract name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._extract_name(node.value)}.{node.attr}"
        else:
            return str(type(node).__name__)
    
    def _extract_call_name(self, node) -> str:
        """Extract the full name of a function call."""
        if isinstance(node, ast.Call):
            return self._extract_name(node.func)
        return ""

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python atlas_generator.py <file1.py> <file2.py> ...")
        print("Example: python atlas_generator.py phoenix.py haven.py events.py orchestrator.py")
        sys.exit(1)
    
    file_paths = sys.argv[1:]
    
    # Generate atlas
    generator = StaticAtlasGenerator()
    generator.analyze_files(file_paths)
    
    # Output markdown atlas
    atlas_content = generator.generate_atlas()
    atlas_file = "function_atlas.md"
    with open(atlas_file, 'w', encoding='utf-8') as f:
        f.write(atlas_content)
    print(f"📖 Function atlas generated: {atlas_file}")
    
    # Output JSON data
    json_data = generator.export_json()
    json_file = "function_atlas.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)
    print(f"📊 JSON data exported: {json_file}")

if __name__ == "__main__":
    main()