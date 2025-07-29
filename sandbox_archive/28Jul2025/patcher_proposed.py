import patch
import os
import tempfile
import shutil
import logging
import re

def _normalize_text(text):
    """
    Normalizes text to prevent common patch failures:
    1. Replaces non-breaking spaces with regular spaces.
    2. Normalizes all line endings (CRLF, CR) to a single LF.
    3. Ensures the text ends with exactly one newline character.
    """
    if not text:
        return ""
    text = text.replace('\xa0', ' ')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.rstrip('\n') + '\n'
    return text

def _correct_hunk_line_numbers(diff_content, original_content):
    """
    Scans a diff and corrects both start lines and line counts in hunk headers
    using a whitespace-agnostic context search.
    """
    corrected_diff_lines = []
    original_lines = original_content.splitlines()
    diff_lines = diff_content.splitlines(True) 

    # Create a stripped version of original_lines for whitespace-agnostic search
    stripped_original_lines = [line.strip() for line in original_lines]

    line_idx = 0
    while line_idx < len(diff_lines):
        line = diff_lines[line_idx]
        hunk_header_match = re.match(r'@@ -(\d+)(,(\d+))? \+(\d+)(,(\d+))? @@.*', line)

        if not hunk_header_match:
            corrected_diff_lines.append(line)
            line_idx += 1
            continue

        original_start_from_hunk = int(hunk_header_match.group(1))
        
        hunk_body_lines = []
        hunk_search_pattern = []
        hunk_body_idx = line_idx + 1
        
        source_line_count = 0
        target_line_count = 0

        while hunk_body_idx < len(diff_lines) and not diff_lines[hunk_body_idx].startswith('@@ '):
            hunk_line = diff_lines[hunk_body_idx]
            hunk_body_lines.append(hunk_line)
            
            if hunk_line.startswith((' ', '-')):
                # Strip the search pattern lines for robust matching
                hunk_search_pattern.append(hunk_line[1:].strip())
            
            if not hunk_line.startswith('+'):
                source_line_count += 1
            if not hunk_line.startswith('-'):
                target_line_count += 1
                
            hunk_body_idx += 1

        actual_start_line = -1
        if hunk_search_pattern:
            # Whitespace-agnostic search
            for i in range(len(stripped_original_lines) - len(hunk_search_pattern) + 1):
                # Compare stripped slices of the original content
                if stripped_original_lines[i:i+len(hunk_search_pattern)] == hunk_search_pattern:
                    actual_start_line = i + 1
                    break
        
        if actual_start_line != -1:
            logging.info(f"Hunk correction: Original header was '@@ -{original_start_from_hunk},...'. Found whitespace-agnostic context at line {actual_start_line}.")
            
            target_start_from_hunk = int(hunk_header_match.group(4))
            start_line_diff = actual_start_line - original_start_from_hunk
            actual_target_start = target_start_from_hunk + start_line_diff

            new_header = f"@@ -{actual_start_line},{source_line_count} +{actual_target_start},{target_line_count} @@"
            header_comment_match = re.search(r'@@.*( @@.*)', line)
            if header_comment_match:
                new_header += header_comment_match.group(1)
            
            corrected_diff_lines.append(new_header + '\n')
            logging.info(f"Corrected Hunk Header: {new_header.strip()}")
        else:
            logging.warning("Could not find matching context for hunk. Leaving header unchanged.")
            corrected_diff_lines.append(line)

        corrected_diff_lines.extend(hunk_body_lines)
        line_idx = hunk_body_idx

    return "".join(corrected_diff_lines)

def apply_patch(diff_content, original_content, original_filename):
    """
    Applies a diff by creating a temporary file structure. It normalizes
    text and robustly corrects hunk headers before applying the patch.
    """
    temp_dir = tempfile.mkdtemp(dir='./.sandbox')
    try:
        normalized_original = _normalize_text(original_content)
        normalized_diff = _normalize_text(diff_content)

        corrected_diff = _correct_hunk_line_numbers(normalized_diff, normalized_original)
        if corrected_diff != normalized_diff:
            logging.info(f"Patch for {original_filename} had its hunk headers auto-corrected.")

        full_temp_path = os.path.join(temp_dir, original_filename)
        os.makedirs(os.path.dirname(full_temp_path), exist_ok=True)

        with open(full_temp_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(normalized_original)

        patch_set = patch.fromstring(corrected_diff.encode('utf-8'))

        if not patch_set:
            return None, "Failed to parse diff content. The patch may be malformed or empty."

        if patch_set.apply(root=temp_dir):
            with open(full_temp_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            if not corrected_diff.endswith('\n'):
                 return new_content.rstrip('\n'), None
            return new_content, None
        else:
            error_details = "Patch set could not be applied. This is often due to a mismatch between the file content and the patch."
            if hasattr(patch_set, 'rejections') and patch_set.rejections:
                rejected_hunks = []
                for reject in patch_set.rejections:
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
        shutil.rmtree(temp_dir)