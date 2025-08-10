#!/usr/bin/env python3
"""
Automatic Code Map Generator using Python AST

This tool analyzes Python files to generate structured code maps similar to 
the manual summaries, extracting functions, classes, calls, and dependencies.
"""

import ast
import os
import sys
from typing import Dict, List, Set, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import json

@dataclass
class FunctionInfo:
    name: str
    calls: Set[str] = field(default_factory=set)
    creates: Set[str] = field(default_factory=set)
    returns: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    line_number: int = 0

@dataclass
class ClassInfo:
    name: str
    methods: Dict[str, FunctionInfo] = field(default_factory=dict)
    bases: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    line_number: int = 0

@dataclass
class ModuleInfo:
    name: str
    file_path: str
    functions: Dict[str, FunctionInfo] = field(default_factory=dict)
    classes: Dict[str, ClassInfo] = field(default_factory=dict)
    imports: Set[str] = field(default_factory=set)
    module_variables: Set[str] = field(default_factory=set)
    docstring: Optional[str] = None

class CodeMapAnalyzer(ast.NodeVisitor):
    def __init__(self, module_name: str, file_path: str):
        self.module_info = ModuleInfo(module_name, file_path)
        self.current_class = None
        self.current_function = None
        
    def visit_Module(self, node):
        """Extract module-level docstring"""
        if (node.body and isinstance(node.body[0], ast.Expr) 
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
            self.module_info.docstring = node.body[0].value.value
        self.generic_visit(node)
        
    def visit_Import(self, node):
        """Track import statements"""
        for alias in node.names:
            self.module_info.imports.add(alias.name)
            
    def visit_ImportFrom(self, node):
        """Track from-import statements"""
        module = node.module or ""
        for alias in node.names:
            self.module_info.imports.add(f"{module}.{alias.name}")
            
    def visit_Assign(self, node):
        """Track module-level variable assignments and object creation"""
        # Module-level variables
        if self.current_class is None and self.current_function is None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.module_info.module_variables.add(target.id)
        
        # Track object creation (Class instantiation)
        if isinstance(node.value, ast.Call):
            self._track_object_creation(node.value)
        self.generic_visit(node)
        
    def visit_ClassDef(self, node):
        """Analyze class definitions"""
        class_info = ClassInfo(
            name=node.name,
            bases=[self._extract_name(base) for base in node.bases],
            docstring=ast.get_docstring(node),
            line_number=node.lineno
        )
        
        old_class = self.current_class
        self.current_class = class_info
        
        # Visit class body
        for item in node.body:
            self.visit(item)
            
        self.module_info.classes[node.name] = class_info
        self.current_class = old_class
        
    def visit_FunctionDef(self, node):
        """Analyze function definitions"""
        func_info = FunctionInfo(
            name=node.name,
            decorators=[self._extract_name(dec) for dec in node.decorator_list],
            docstring=ast.get_docstring(node),
            line_number=node.lineno
        )
        
        # Analyze return type hints
        if node.returns:
            func_info.returns = self._extract_name(node.returns)
            
        old_function = self.current_function
        self.current_function = func_info
        
        # Visit function body
        for item in node.body:
            self.visit(item)
            
        # Store function in appropriate location
        if self.current_class:
            self.current_class.methods[node.name] = func_info
        else:
            self.module_info.functions[node.name] = func_info
            
        self.current_function = old_function
        
    def visit_Call(self, node):
        """Track function calls and object creation"""
        if self.current_function:
            call_name = self._extract_call_name(node)
            if call_name:
                self.current_function.calls.add(call_name)
                
        self._track_object_creation(node)
        self.generic_visit(node)
        
    def _track_object_creation(self, node):
        """Detect object creation patterns"""
        if not self.current_function:
            return
            
        if isinstance(node, ast.Call):
            func_name = self._extract_call_name(node)
            
            # Common object creation patterns
            creation_patterns = [
                'dict', 'list', 'set', 'tuple', 'str', 'int', 'float',
                'threading.Event', 'uuid.uuid4', 'datetime.now',
                'Flask', 'SocketIO', 'ActiveSession', 'MemoryManager',
                'HavenProxyWrapper', 'GenerativeModel', 'Content', 'Part'
            ]
            
            for pattern in creation_patterns:
                if func_name and pattern in func_name:
                    self.current_function.creates.add(pattern)
                    break
                    
    def _extract_name(self, node):
        """Extract name from various AST node types"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._extract_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Constant):
            return str(node.value)
        else:
            return str(type(node).__name__)
            
    def _extract_call_name(self, node):
        """Extract the full name of a function call"""
        if isinstance(node, ast.Call):
            return self._extract_name(node.func)
        return None

def analyze_file(file_path: str) -> ModuleInfo:
    """Analyze a single Python file and return module information"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
            
        tree = ast.parse(source)
        module_name = Path(file_path).stem
        
        analyzer = CodeMapAnalyzer(module_name, file_path)
        analyzer.visit(tree)
        
        return analyzer.module_info
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return ModuleInfo(Path(file_path).stem, file_path)

def generate_interaction_map(modules: List[ModuleInfo]) -> Dict[str, Any]:
    """Generate cross-module interaction map"""
    interactions = {}
    
    for module in modules:
        module_interactions = []
        
        # Check all function calls for cross-module references
        all_functions = list(module.functions.values())
        for class_info in module.classes.values():
            all_functions.extend(class_info.methods.values())
            
        for func in all_functions:
            for call in func.calls:
                # Check if call references other modules
                for other_module in modules:
                    if other_module.name != module.name:
                        if (call.startswith(other_module.name + '.') or 
                            any(call.startswith(cls + '.') for cls in other_module.classes.keys())):
                            module_interactions.append({
                                'from_function': func.name,
                                'to_module': other_module.name,
                                'call': call
                            })
                            
        interactions[module.name] = module_interactions
        
    return interactions

def format_module_summary(module: ModuleInfo) -> str:
    """Format a single module summary similar to the manual format"""
    lines = [f"{module.name} - {module.docstring or 'No description'}", ""]
    
    # Module state
    if module.module_variables:
        lines.append("Module State:")
        for var in sorted(module.module_variables):
            lines.append(f"  {var}")
        lines.append("")
    
    # Functions
    if module.functions:
        lines.append("Functions:")
        for name, func in module.functions.items():
            lines.append(f"  {name}()")
            if func.calls:
                lines.append(f"    @calls: {', '.join(sorted(func.calls))}")
            if func.creates:
                lines.append(f"    @creates: {', '.join(sorted(func.creates))}")
            if func.returns:
                lines.append(f"    @returns: {func.returns}")
            lines.append("")
    
    # Classes
    if module.classes:
        lines.append("Classes:")
        for name, cls in module.classes.items():
            base_str = f"({', '.join(cls.bases)})" if cls.bases else ""
            lines.append(f"  {name}{base_str}")
            
            for method_name, method in cls.methods.items():
                lines.append(f"    {method_name}()")
                if method.calls:
                    lines.append(f"      @calls: {', '.join(sorted(method.calls))}")
                if method.creates:
                    lines.append(f"      @creates: {', '.join(sorted(method.creates))}")
            lines.append("")
    
    return "\n".join(lines)

def generate_unified_atlas(file_paths: List[str]) -> str:
    """Generate a unified code atlas from multiple Python files"""
    modules = []
    
    print("Analyzing files...")
    for file_path in file_paths:
        if os.path.exists(file_path):
            module = analyze_file(file_path)
            modules.append(module)
            print(f"✓ Analyzed {file_path}")
        else:
            print(f"✗ File not found: {file_path}")
    
    # Generate individual module summaries
    atlas_lines = ["# Unified Code Atlas - Generated Analysis", ""]
    
    for module in modules:
        atlas_lines.append("## " + "=" * 50)
        atlas_lines.append(format_module_summary(module))
        atlas_lines.append("")
    
    # Generate interaction map
    interactions = generate_interaction_map(modules)
    atlas_lines.append("## Cross-Module Interactions")
    atlas_lines.append("")
    
    for module_name, module_interactions in interactions.items():
        if module_interactions:
            atlas_lines.append(f"### {module_name} calls:")
            for interaction in module_interactions:
                atlas_lines.append(f"  {interaction['from_function']}() → {interaction['to_module']}.{interaction['call']}")
            atlas_lines.append("")
    
    return "\n".join(atlas_lines)

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python code_map_generator.py <file1.py> <file2.py> ...")
        print("Example: python code_map_generator.py phoenix.py haven.py events.py orchestrator.py")
        sys.exit(1)
    
    file_paths = sys.argv[1:]
    atlas = generate_unified_atlas(file_paths)
    
    # Write to file
    output_file = "generated_code_atlas.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(atlas)
    
    print(f"\n✓ Code atlas generated: {output_file}")
    
    # Also save as JSON for programmatic use
    modules = [analyze_file(fp) for fp in file_paths if os.path.exists(fp)]
    json_data = {
        'modules': [
            {
                'name': m.name,
                'file_path': m.file_path,
                'functions': {name: {
                    'calls': list(func.calls),
                    'creates': list(func.creates),
                    'returns': func.returns,
                    'line_number': func.line_number
                } for name, func in m.functions.items()},
                'classes': {name: {
                    'methods': {mname: {
                        'calls': list(method.calls),
                        'creates': list(method.creates),
                        'line_number': method.line_number
                    } for mname, method in cls.methods.items()},
                    'bases': cls.bases,
                    'line_number': cls.line_number
                } for name, cls in m.classes.items()},
                'imports': list(m.imports),
                'module_variables': list(m.module_variables)
            } for m in modules
        ],
        'interactions': generate_interaction_map(modules)
    }
    
    json_file = "generated_code_atlas.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"✓ JSON data saved: {json_file}")

if __name__ == "__main__":
    main()