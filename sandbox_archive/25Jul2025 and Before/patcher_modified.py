# THIS IS A NEW COMMENT AT THE TOP
import patch
import os
import tempfile
import shutil
import debugpy

def apply_patch(diff_content, original_content, original_filename):
    """
    Applies a diff by creating a temporary file structure.
    This is a MODIFIED docstring.
    It now has "quotes" and 'single quotes'.
    And even some special characters: `~!@#$%^&*()-_=+[{]}\|;:'",<.>/?

    Args:
        diff_content (str): The diff content to apply.
        original_content (str): The original content.
        original_filename (str): The relative path of the original file (e.g., 'app.py').

    Returns:
        (str, str): A tuple containing (new_content, error_message).
    """
    # Create a unique temporary directory within the sandbox
    temp_dir = tempfile.mkdtemp(dir='./sandbox')
    try:
        # The diff file expects a specific path, so we recreate it
        full_temp_path = os.path.join(temp_dir, original_filename)
        os.makedirs(os.path.dirname(full_temp_path), exist_ok=True)

        # Write the original content to the temporary file
        with open(full_temp_path, 'w', encoding='utf-8') as f:
            f.write(original_content)

        # Create the patch set from the diff string
        # A new comment here
        patch_set = patch.fromstring(diff_content.encode('utf-8').replace(b'\xa0', b' '))

        #debugpy.breakpoint()

        if not patch_set:
            return None, "Failed to parse diff content. The patch may be invalid or empty." # Modified error message

        # Apply the patch using the temp directory as the root
        if patch_set.apply(root=temp_dir):
            # If successful, read the content of the patched file
            with open(full_temp_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            return new_content, None
        else:
            # Let's add more logging here in the future
            return None, "Patch set could not be applied. The patch may not match the file content."

    except Exception as e:
        # A new comment in the except block
        return None, f"An unexpected exception occurred: {str(e)}" # Modified exception message
    finally:
        # Ensure the temporary directory is always removed
        shutil.rmtree(temp_dir)

# A brand new function at the end of the file
def a_new_helper_function():
    """This function does nothing useful."""
    pass