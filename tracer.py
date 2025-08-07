import functools
import inspect
import re
import os

def _sanitize_repr(value):
    """
    Cleans the string representation of an object by removing memory addresses
    and other volatile information.
    """
    rep = repr(value)
    rep = re.sub(r'\s+at\s+0x[0-9a-fA-F]+', '', rep)
    return rep

def _clean_trace_log(log):
    """
    Recursively removes entries with empty 'nested_calls' lists from a trace log.
    """
    if isinstance(log, list):
        # Process a list of calls
        new_log = []
        for entry in log:
            cleaned_entry = _clean_trace_log(entry)
            if cleaned_entry: # Only append if it's not empty after cleaning
                new_log.append(cleaned_entry)
        return new_log
    elif isinstance(log, dict):
        # Process a single call entry
        if "nested_calls" in log:
            # Recursively clean the nested calls
            log["nested_calls"] = _clean_trace_log(log["nested_calls"])
            # If the list is now empty, remove the key
            if not log["nested_calls"]:
                del log["nested_calls"]
        return log
    return log


class Tracer:
    """
    A tracer that logs the execution flow of decorated functions into a
    hierarchical, nested structure that mirrors the call stack.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        """Clears the current trace log and resets the call stack."""
        self.trace_log = []
        self.call_stack = [] # A stack to keep track of the current execution depth

    def start_trace(self, module, func_name):
        """Starts a new trace for a function call."""
        trace_entry = {
            "function": f"{module}.{func_name}",
            "nested_calls": []
        }

        if self.call_stack:
            parent_entry = self.call_stack[-1]
            parent_entry["nested_calls"].append(trace_entry)
        else:
            self.trace_log.append(trace_entry)
        
        self.call_stack.append(trace_entry)

    def end_trace(self, return_value, is_exception=False):
        """Ends the trace for the current function, adding its return value."""
        if not self.call_stack:
            return

        last_entry = self.call_stack.pop()
        
        if "nested_calls" in last_entry and not last_entry["nested_calls"]:
            del last_entry["nested_calls"]

        if is_exception:
            last_entry["exception"] = _sanitize_repr(return_value)
        elif return_value is not None:
            is_empty_container = isinstance(return_value, (list, dict, tuple, str)) and not return_value
            if not is_empty_container:
                last_entry["return_value"] = _sanitize_repr(return_value)

    def get_trace(self):
        """
        Returns the completed trace log after performing a final cleanup pass
        to remove empty 'nested_calls' lists.
        """
        return _clean_trace_log(self.trace_log)

# Global instance of the tracer
global_tracer = Tracer()

def log_event(event_name: str, details: dict):
    """
    Manually logs a custom event to the global tracer.
    """
    caller_frame = inspect.stack()[1]
    # Remove the '.py' extension from the module name.
    module_name = os.path.basename(caller_frame.filename).replace(".py", "")
    
    event_entry = {
        "type": "EVENT",
        "event_name": f"{module_name}.{event_name}"
    }

    if global_tracer.call_stack:
        global_tracer.call_stack[-1]["nested_calls"].append(event_entry)
    else:
        global_tracer.trace_log.append(event_entry)

def trace(func):
    """
    A decorator that logs the entry and exit of a function call
    to the global_tracer in a nested format.
    """
    if func.__module__ == 'tracer':
        return func
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__qualname__
        # Remove the '.py' extension from the module name.
        module_name = os.path.basename(inspect.getfile(func)).replace(".py", "")
        
        global_tracer.start_trace(module_name, func_name)
        
        try:
            result = func(*args, **kwargs)
            global_tracer.end_trace(result)
            return result
        except Exception as e:
            global_tracer.end_trace(e, is_exception=True)
            raise
            
    return wrapper
