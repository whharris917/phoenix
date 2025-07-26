import patch
import os
import tempfile
import shutil
import logging

def _normalize_text(text):
    """
    Normalizes text to prevent common patch failures:
    1. Replaces non-breaking spaces with regular spaces.
    2. Normalizes all line endings (CRLF, CR) to a single LF.
    3. Ensures the text ends with exactly one newline character.
    """
    if not text:
        # An empty file is represented by an empty string.
        return ""
    # Replace non-breaking spaces (U+00A0) with regular spaces
    text = text.replace('\xa0', ' ')
    # Normalize all line endings to a single LF ('\n')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Ensure text ends with exactly one newline, and no more.
    text = text.rstrip('\n') + '\n'
    return text

def apply_patch(diff_content, original_content, original_filename):
    """
    Applies a diff by creating a temporary file structure. It normalizes
    text to prevent common whitespace and line-ending issues.

    Args:
        diff_content (str): The diff content to apply.
        original_content (str): The original content.
        original_filename (str): The relative path of the original file (e.g., 'app.py').

    Returns:
        (str, str): A tuple containing (new_content, error_message).
    """
    # Create a unique temporary directory within the sandbox
    temp_dir = tempfile.mkdtemp(dir='./.sandbox')
    try:
        # --- NEW: Normalize inputs to prevent common errors ---
        normalized_diff = _normalize_text(diff_content)
        normalized_original = _normalize_text(original_content)

        # The diff file expects a specific path, so we recreate it
        full_temp_path = os.path.join(temp_dir, original_filename)
        os.makedirs(os.path.dirname(full_temp_path), exist_ok=True)

        # Write the NORMALIZED original content to the temporary file
        # Use newline='\n' to ensure consistent line endings on write
        with open(full_temp_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(normalized_original)

        # Create the patch set from the NORMALIZED diff string
        patch_set = patch.fromstring(normalized_diff.encode('utf-8'))

        if not patch_set:
            return None, "Failed to parse diff content. The patch may be malformed or empty."

        # Apply the patch using the temp directory as the root
        if patch_set.apply(root=temp_dir):
            # If successful, read the content of the patched file
            with open(full_temp_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            # The final content should match the normalized state, but we'll
            # rstrip just in case the patch library adds a final newline
            # to a file that was intended to have none.
            if not normalized_diff.endswith('\n'):
                 return new_content.rstrip('\n'), None
            return new_content, None
        else:
            # --- NEW: Provide a much more detailed error message ---
            error_details = "Patch set could not be applied. This is often due to a mismatch between the file content and the patch."
            if hasattr(patch_set, 'rejections') and patch_set.rejections:
                rejected_hunks = []
                for reject in patch_set.rejections:
                    # Provide details on which hunk failed to apply
                    rejected_hunks.append(f"  - Hunk starting at line {reject.source_start} in the original file could not be applied.")
                error_details += "\\n\\nRejected Hunks:\\n" + "\\n".join(rejected_hunks)
            else:
                error_details += " No specific hunks were rejected, which could indicate a problem with the file paths in the diff header or a malformed patch that the parser did not catch."
            
            logging.warning(f"Patch application failed for {original_filename}. Details: {error_details}")
            return None, error_details

    except Exception as e:
        logging.error(f"An exception occurred during the patching process: {e}")
        return None, f"An unexpected exception occurred: {str(e)}"
    finally:
        # Ensure the temporary directory is always removed
        shutil.rmtree(temp_dir)