import json
from typing import Any, Dict, Set, List
import os

def generate_structural_map(atlas_data: Dict[str, Any]) -> str:
    markdown_lines = ["## 🗺️ Structural Map: Modules & State",
                      "This section provides a high-level overview of each module, its primary purpose, and the state it manages.",
                      ""]
    for filename, report in sorted(atlas_data.items()):
        markdown_lines.append(f"### 📂 `{filename}`")
        docstring = report.get("module_docstring")
        if docstring:
            markdown_lines.append(f"> *{docstring.strip()}*")
            markdown_lines.append("")
        managed_state = report.get("module_state")
        if managed_state:
            markdown_lines.append("**Managed State:**")
            for state in managed_state:
                markdown_lines.append(f"- `{state['name']}`: Assigned from `{state['value']}`.")
            markdown_lines.append("")
    return "\n".join(markdown_lines)

def build_tree_recursive(func_name: str, all_funcs_map: Dict[str, Any], prefix: str = "", is_last: bool = True, visited: Set[str] = None) -> List[str]:
    if visited is None:
        visited = set()
    lines = []
    connector = "└── " if is_last else "├── "
    func_details = all_funcs_map.get(func_name, {})
    accessed_state = func_details.get("accessed_state", [])
    access_flag = ""
    if accessed_state:
        access_flag = f" 💥 (accesses module state: {', '.join(accessed_state)})"
    lines.append(f"{prefix}{connector}{func_name}{access_flag}")
    if func_name in visited:
        lines[-1] += " (Circular Reference)"; return lines
    visited.add(func_name)
    calls = func_details.get("calls", [])
    instantiations = [f"[new] {i}" for i in func_details.get("instantiations", [])]
    
    # Use a set to de-duplicate children before sorting and displaying
    children = sorted(list(set(calls + instantiations)))
    
    new_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(children):
        is_last_child = (i == len(children) - 1)
        if child.startswith("[new]"):
            child_connector = "└── " if is_last_child else "├── "
            lines.append(f"{new_prefix}{child_connector}{child}")
        else:
            lines.extend(build_tree_recursive(child, all_funcs_map, new_prefix, is_last_child, visited.copy()))
    return lines

def generate_call_trees(atlas_data: Dict[str, Any]) -> str:
    # (This function is unchanged)
    markdown_lines = ["## 🌳 Hierarchical Call Trees",
                      "This section visualizes the application's control flow, starting from 'root' functions (e.g., event handlers) that are not called by other functions within the project.",
                      ""]
    all_funcs_map: Dict[str, Any] = {}
    all_called_funcs: Set[str] = set()
    for module_path, report in atlas_data.items():
        module_name = os.path.splitext(os.path.basename(module_path))[0]
        for func in report.get("functions", []):
            full_name = f"{module_name}.{func['name']}"
            all_funcs_map[full_name] = func
            for call in func.get("calls", []): all_called_funcs.add(call)
        for class_def in report.get("classes", []):
            for method in class_def.get("methods", []):
                full_name = f"{module_name}.{class_def['name']}.{method['name']}"
                all_funcs_map[full_name] = method
                for call in method.get("calls", []): all_called_funcs.add(call)

    all_defined_funcs = set(all_funcs_map.keys())
    root_nodes = sorted(list(all_defined_funcs - all_called_funcs))

    for root in root_nodes:
        markdown_lines.append(f"### ▶️ `{root}`")
        markdown_lines.append("```")
        tree_lines = build_tree_recursive(root, all_funcs_map)
        markdown_lines.extend(tree_lines)
        markdown_lines.append("```")
        markdown_lines.append("")
    return "\n".join(markdown_lines)


def distill_atlas(report_path: str, output_path: str) -> None:
    # (This function is unchanged)
    print(f"Reading raw atlas report from: {report_path}")
    with open(report_path, 'r', encoding='utf-8') as f:
        atlas_data = json.load(f)
    structural_map_md = generate_structural_map(atlas_data)
    call_trees_md = generate_call_trees(atlas_data)
    final_markdown = f"# Phoenix Code Atlas\n\n{structural_map_md}\n\n---\n\n{call_trees_md}"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_markdown)
    print(f"✅ Code atlas successfully distilled to: {output_path}")

if __name__ == "__main__":
    distill_atlas("code_atlas_report.json", "CODE_ATLAS.md")
