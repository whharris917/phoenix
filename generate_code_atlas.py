import ast
import json
import os
from typing import Any, Dict, List, Set

def _get_node_id(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute):
        base = _get_node_id(node.value)
        if base: return f"{base}.{node.attr}"
    return None

IGNORED_PREFIXES = {'os.', 'csv.', 'logging.', 'json.', 're.', 'datetime.', 'uuid.'}
IGNORED_NAMES = {
    'get', 'strip', 'append', 'pop', 'loads', 'dumps', 'join', 'keys', 'values', 'items', 'startswith',
    'open', 'isinstance', 'isoformat', 'str', 'len', 'set', 'hasattr', 'repr', 'isupper', 'list', 'sorted', 'any', 'print',
    'range', 'max', 'min', 'sum', 'enumerate', 'zip', 'int', 'float', 'dict', 'tuple', 'rfind', 'group', 'replace',
    'find', 'split', 'compile', 'escape', 'sub', 'match', 'search', 'finditer', 'splitlines', 'sleep', 'now', 'fromtimestamp', 'strftime'
}

class CodeAnalyzer(ast.NodeVisitor):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.module_name = os.path.splitext(os.path.basename(filepath))[0]
        self.imports: Dict[str, str] = {}
        self.local_definitions: Set[str] = set()
        self.module_state_names: Set[str] = set()
        self.report: Dict[str, Any] = { "file_path": os.path.basename(filepath), "module_docstring": None, "imports": {}, "classes": [], "functions": [], "module_state": [] }

    def _get_value_repr(self, node: ast.AST) -> str:
        if isinstance(node, ast.Constant): return repr(node.value)
        if isinstance(node, (ast.Dict, ast.DictComp)): return "{...}"
        if isinstance(node, (ast.List, ast.ListComp, ast.Set, ast.SetComp)): return "[...]"
        if isinstance(node, ast.Call):
            call_name = _get_node_id(node.func)
            return f"{call_name}()" if call_name else "call()"
        return "<complex_value>"

    def _get_function_details(self, node: ast.FunctionDef, class_name: str = None) -> Dict[str, Any]:
        local_type_map = {}
        for arg in node.args.args:
            if arg.annotation:
                type_name = _get_node_id(arg.annotation)
                if type_name in self.imports: type_name = self.imports[type_name]
                if type_name: local_type_map[arg.arg] = type_name
        
        # FIXED: Use ast.walk to find all annotated assignments, even nested ones
        for sub_node in ast.walk(node):
            if isinstance(sub_node, ast.AnnAssign) and isinstance(sub_node.target, ast.Name):
                type_name = _get_node_id(sub_node.annotation)
                if type_name in self.imports: type_name = self.imports[type_name]
                if type_name: local_type_map[sub_node.target.id] = type_name

        class CallVisitor(ast.NodeVisitor):
            def __init__(self, module_name: str, import_map: Dict[str, str], local_defs: Set[str], type_map: Dict[str, str], state_names: Set[str], current_class_name: str = None):
                self.module_name = module_name; self.import_map = import_map; self.local_defs = local_defs
                self.type_map = type_map; self.state_names = state_names; self.current_class_name = current_class_name
                self.calls = set(); self.instantiations = set(); self.passed_args = set(); self.accessed_state = set()

            def visit_Name(self, node: ast.Name):
                if isinstance(node.ctx, ast.Load) and node.id in self.state_names:
                    self.accessed_state.add(node.id)
                self.generic_visit(node)

            def visit_Call(self, node: ast.Call):
                for arg in node.args:
                    if isinstance(arg, ast.Name): self.passed_args.add(arg.id)
                
                func = node.func; call_name_parts = []; full_call_name = ""
                
                # FIXED: More robust logic to trace back to a typed base variable
                obj_name_str = _get_node_id(func.value) if isinstance(func, ast.Attribute) else None
                resolved_from_type = False
                if obj_name_str:
                    base_var = obj_name_str.split('.')[0]
                    if base_var in self.type_map:
                        base_type = self.type_map[base_var]
                        rest_of_chain = obj_name_str.split('.')[1:]
                        all_attrs = rest_of_chain + [func.attr]
                        full_call_name = f"{base_type}.{'.'.join(all_attrs)}"
                        resolved_from_type = True

                if not resolved_from_type:
                    while isinstance(func, ast.Attribute):
                        call_name_parts.insert(0, func.attr); func = func.value
                    if isinstance(func, ast.Name):
                        base_obj = func.id
                        if base_obj == 'self' and self.current_class_name: call_name_parts.insert(0, f"{self.module_name}.{self.current_class_name}")
                        elif base_obj in self.import_map: call_name_parts.insert(0, self.import_map[base_obj])
                        elif base_obj in self.local_defs: call_name_parts.insert(0, f"{self.module_name}.{base_obj}")
                        else: call_name_parts.insert(0, base_obj)
                    full_call_name = ".".join(call_name_parts)

                if not full_call_name: self.generic_visit(node); return
                final_name_part = full_call_name.split('.')[-1]

                if any(full_call_name.startswith(p) for p in IGNORED_PREFIXES) or final_name_part in IGNORED_NAMES:
                    self.generic_visit(node); return
                
                if full_call_name.endswith(('.socketio.emit', '.socket.emit')) and node.args and isinstance(node.args[0], ast.Constant):
                    full_call_name = f"{full_call_name}('{node.args[0].value}')"
                elif full_call_name in ('socketio.emit', 'socket.emit') and node.args and isinstance(node.args[0], ast.Constant):
                    full_call_name = f"{full_call_name}('{node.args[0].value}')"

                if final_name_part and final_name_part[0].isupper(): self.instantiations.add(full_call_name)
                else: self.calls.add(full_call_name)
                self.generic_visit(node)

        call_finder = CallVisitor(self.module_name, self.imports, self.local_definitions, local_type_map, self.module_state_names, class_name)
        for stmt in node.body:
            for sub_node in ast.walk(stmt): call_finder.visit(sub_node)
        
        return {"name": node.name, "args": [arg.arg for arg in node.args.args], "docstring": ast.get_docstring(node),
                "calls": sorted(list(call_finder.calls)), "instantiations": sorted(list(call_finder.instantiations)),
                "passed_args": sorted(list(call_finder.passed_args)), "accessed_state": sorted(list(call_finder.accessed_state))}

    def analyze(self) -> Dict[str, Any]:
        with open(self.filepath, "r", encoding="utf-8") as source: source_code = source.read()
        tree = ast.parse(source_code)
        
        # Add parent pointers first for context
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node): child.parents = getattr(child, 'parents', []) + [node]

        # Pre-scan to find all local definitions and true module-level state
        self.local_definitions.clear(); self.module_state_names.clear()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef): self.local_definitions.add(node.name)
            if isinstance(node, ast.ClassDef): self.local_definitions.add(node.name)
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and hasattr(node, 'parents') and isinstance(node.parents[-1], ast.Module):
                target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
                if isinstance(target, ast.Name): self.module_state_names.add(target.id)
        
        self.visit(tree); self.report["imports"] = self.imports; return self.report

    def visit_Import(self, node: ast.Import):
        for alias in node.names: self.imports[alias.asname or alias.name] = alias.name
    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names: self.imports[alias.asname or alias.name] = f"{module}.{alias.name}"
    def visit_Module(self, node: ast.Module):
        self.report["module_docstring"] = ast.get_docstring(node); self.generic_visit(node)
    def visit_FunctionDef(self, node: ast.FunctionDef):
        if not any(isinstance(p, ast.ClassDef) for p in getattr(node, 'parents', [])): 
            self.report["functions"].append(self._get_function_details(node))
        self.generic_visit(node)
    def visit_ClassDef(self, node: ast.ClassDef):
        methods = [self._get_function_details(item, class_name=node.name) for item in node.body if isinstance(item, ast.FunctionDef)]
        self.report["classes"].append({"name": node.name, "docstring": ast.get_docstring(node), "methods": methods})
    def visit_Assign(self, node: ast.Assign):
        if hasattr(node, 'parents') and isinstance(node.parents[-1], ast.Module):
            for target in node.targets:
                if isinstance(target, ast.Name): self.report["module_state"].append({"name": target.id, "value": self._get_value_repr(node.value)})
        self.generic_visit(node)
    def visit_AnnAssign(self, node: ast.AnnAssign):
        if hasattr(node, 'parents') and isinstance(node.parents[-1], ast.Module):
            if isinstance(node.target, ast.Name) and node.value:
                self.report["module_state"].append({"name": node.target.id, "value": self._get_value_repr(node.value)})
        self.generic_visit(node)


def refine_atlas_with_passed_args(atlas: Dict[str, Any]) -> Dict[str, Any]:
    all_defined_funcs: Set[str] = set()
    for report in atlas.values():
        module_name = os.path.splitext(report['file_path'])[0]
        for func in report.get("functions", []): all_defined_funcs.add(f"{module_name}.{func['name']}")
        for class_def in report.get("classes", []):
            for method in class_def.get("methods", []): all_defined_funcs.add(f"{module_name}.{class_def['name']}.{method['name']}")
    
    for report in atlas.values():
        imports = report.get("imports", {})
        module_name = os.path.splitext(report['file_path'])[0]

        def process_func_list(func_list):
            for func in func_list:
                passed_args = func.pop("passed_args", [])
                for arg_name in passed_args:
                    resolved_name = imports.get(arg_name, f"{module_name}.{arg_name}")
                    if resolved_name in all_defined_funcs:
                        func["calls"].append(resolved_name)
                func["calls"] = sorted(list(set(func["calls"])))

        process_func_list(report.get("functions", []))
        for class_def in report.get("classes", []):
            process_func_list(class_def.get("methods", []))
    return atlas

def generate_atlas(project_dir: str) -> None:
    full_atlas: Dict[str, Any] = {}
    for filename in os.listdir(project_dir):
        if os.path.isfile(os.path.join(project_dir, filename)) and filename.endswith(".py"):
            filepath = os.path.join(project_dir, filename)
            print(f"Analyzing: {filename}")
            try:
                analyzer = CodeAnalyzer(filepath)
                full_atlas[filename] = analyzer.analyze()
            except Exception as e:
                print(f"  ERROR analyzing {filename}: {e}")

    print("\nRefining atlas for passed-as-argument calls...")
    refined_atlas = refine_atlas_with_passed_args(full_atlas)

    with open("code_atlas_report.json", "w", encoding="utf-8") as f:
        json.dump(refined_atlas, f, indent=2)
    print("\n✅ Atlas generation complete. Report saved to 'code_atlas_report.json'")

if __name__ == "__main__":
    generate_atlas(".")
