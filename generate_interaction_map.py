import ast
import os
from collections import defaultdict

# --- Configuration ---
# The files we want to analyze to build the map.
FILES_TO_ANALYZE = [
    "orchestrator.py",
    "app.py",
    "tool_agent.py",
    "memory_manager.py",
    "proxies.py",
    "haven.py",
    "response_parser.py",
]

# The output file for the Mermaid graph.
OUTPUT_FILE = "sdlc/System_Interaction_Map.md"

# Heuristic mapping of key function names to their conceptual module "owner".
# This is the core of our analysis. It tells the script which module a
# function call belongs to.
FUNCTION_OWNER_MAP = {
    "connect_to_haven": "Haven",
    "send_message": "Haven",
    "prepare_augmented_prompt": "Memory Manager",
    "add_turn": "Memory Manager",
    "parse_agent_response": "Response Parser",
    "execute_tool_command": "Tool Agent",
    "get_or_create_session": "Haven",
    "delete_session": "Haven",
    "emit": "SocketIO Client" # To show interaction with the UI
}

# Mapping of filenames to their clean names for the graph nodes.
MODULE_NODE_MAP = {
    "orchestrator.py": "Orchestrator",
    "app.py": "Web App",
    "tool_agent.py": "Tool Agent",
    "memory_manager.py": "Memory Manager",
    "proxies.py": "Haven Proxy",
    "haven.py": "Haven",
    "response_parser.py": "Response Parser",
}

class InteractionVisitor(ast.NodeVisitor):
    """
    An AST visitor that finds function calls within other functions
    to map out the interactions between modules.
    """
    def __init__(self, current_module_name):
        self.current_module_name = current_module_name
        self.current_function = None
        self.interactions = set()

    def visit_FunctionDef(self, node):
        """Record the current function we are inside."""
        self.current_function = node.name
        # Continue traversing into the function's body
        self.generic_visit(node)
        self.current_function = None

    def visit_Call(self, node):
        """Identify a function call and record the interaction."""
        if not self.current_function:
            # We only care about calls made from within another function.
            return

        # ast.unparse is a simple way to get the string representation of the call target
        # e.g., 'chat.send_message' or 'execute_tool_command'
        call_name = ast.unparse(node.func)

        # Find the base function name (e.g., 'send_message' from 'chat.send_message')
        base_func_name = call_name.split('.')[-1]

        if base_func_name in FUNCTION_OWNER_MAP:
            caller_module = self.current_module_name
            callee_module = FUNCTION_OWNER_MAP[base_func_name]

            if caller_module != callee_module:
                # We have a cross-module interaction. Record it.
                interaction = (caller_module, callee_module, base_func_name)
                self.interactions.add(interaction)
        
        # Continue visiting in case of nested calls
        self.generic_visit(node)

def generate_interaction_map():
    """
    Main function to analyze source files and generate the Mermaid graph.
    """
    print("Generating System Interaction Map...")
    all_interactions = set()

    for filename in FILES_TO_ANALYZE:
        if not os.path.exists(filename):
            print(f"WARNING: File '{filename}' not found. Skipping.")
            continue
        
        print(f"Analyzing '{filename}'...")
        with open(filename, "r", encoding="utf-8") as source_file:
            source_code = source_file.read()
            tree = ast.parse(source_code)
            
            module_node_name = MODULE_NODE_MAP.get(filename, filename)
            visitor = InteractionVisitor(module_node_name)
            visitor.visit(tree)
            all_interactions.update(visitor.interactions)

    # --- Write the output file ---
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# System Interaction Map\n\n")
        f.write("This diagram illustrates the primary interactions and call flows between the major components of the Phoenix Agent system. It is generated automatically from the source code.\n\n")
        f.write("```mermaid\n")
        f.write("graph TD\n\n")
        
        # Define styles for nodes
        for node in set(MODULE_NODE_MAP.values()) | set(FUNCTION_OWNER_MAP.values()):
             f.write(f"    classDef {node.replace(' ', '')} fill:#f9f,stroke:#333,stroke-width:2px\n")

        # Write the interactions as graph edges
        sorted_interactions = sorted(list(all_interactions))
        for caller, callee, func_name in sorted_interactions:
            # Make node names safe for Mermaid syntax
            caller_id = caller.replace(' ', '')
            callee_id = callee.replace(' ', '')
            f.write(f"    {caller_id}[{caller}] -->|{func_name}| {callee_id}[{callee}]\n")

        f.write("\n")
        # Apply styles
        for node in set(MODULE_NODE_MAP.values()) | set(FUNCTION_OWNER_MAP.values()):
             f.write(f"    class {node.replace(' ', '')} {node.replace(' ', '')}\n")


        f.write("```\n")

    print(f"\nSuccessfully generated interaction map at '{OUTPUT_FILE}'")

if __name__ == "__main__":
    generate_interaction_map()
