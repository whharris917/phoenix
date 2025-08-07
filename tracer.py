import functools
import inspect
import re
import os

def _sanitize_repr(value):
    """
    Cleans the string representation of an object by removing memory addresses
    and other volatile information.
    """
    # Get the initial representation
    rep = repr(value)
    # Remove memory addresses (e.g., ' at 0x...')
    rep = re.sub(r'\s+at\s+0x[0-9a-fA-F]+', '', rep)
    return rep

class Tracer:
    """
    A simple tracer to log the execution flow of decorated functions.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        """Clears the current trace log."""
        self.log = []
        self.call_id = 0

    def add_record(self, record_type, module, func_name, bound_args, return_value=None):
        """Adds a record to the trace log."""
        self.call_id += 1
        
        # Sanitize args and kwargs to be clean and JSON serializable
        sanitized_args = {name: _sanitize_repr(val) for name, val in bound_args.items()}
        
        record = {
            "id": self.call_id,
            "module": module,
            "type": record_type,
            "function": func_name,
            "args": sanitized_args,
        }
        if return_value:
            record["return_value"] = _sanitize_repr(return_value)
            
        self.log.append(record)

    def get_trace(self):
        """Returns the current trace log."""
        return self.log

# Global instance of the tracer
global_tracer = Tracer()

def log_event(event_name: str, details: dict):
    """
    Manually logs a custom event to the global tracer.
    This is used for tracing things other than function calls.
    """
    # Get the module where this function was called from
    caller_frame = inspect.stack()[1]
    module_name = os.path.basename(caller_frame.filename)
    
    # The 'function' will be the custom event name.
    global_tracer.add_record(
        record_type='EVENT',
        module=module_name,
        func_name=event_name,
        bound_args=details
    )


def trace(func):
    """
    A decorator that logs the entry and exit of a function call
    to the global_tracer, including named arguments and module info.
    """
    # --- Refinement 4: Exclude the tracer's own functions ---
    if func.__module__ == 'tracer':
        return func

    func_sig = inspect.signature(func)
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__qualname__
        module_name = os.path.basename(inspect.getfile(func))

        # --- Refinement 3: Bind args and kwargs to their names ---
        bound_args = func_sig.bind(*args, **kwargs).arguments
        
        # Log the function entry
        global_tracer.add_record('CALL', module_name, func_name, bound_args)
        
        try:
            # Execute the actual function
            result = func(*args, **kwargs)
            
            # Log the function exit
            global_tracer.add_record('RETURN', module_name, func_name, bound_args, return_value=result)
            
            return result
        except Exception as e:
            # Log any exceptions that occur
            global_tracer.add_record('EXCEPTION', module_name, func_name, bound_args, return_value=e)
            raise # Re-raise the exception
            
    return wrapper
