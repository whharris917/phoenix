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
        # An empty file is represented by an empty string.
        return ""
    # Replace non-breaking spaces (U+00A0) with regular spaces
    text = text.replace("\xa0", " ")
    # Normalize all line endings to a single LF ('\n')
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Ensure text ends with exactly one newline, and no more.
    text = text.rstrip("\n") + "\n"
    return text


def _correct_hunk_line_numbers(diff_content, original_content):
    """
    Scans a diff and corrects both the start line and line counts in hunk headers.

    This function provides a robust correction for agent-generated patches with
    incorrect hunk headers. It works by:
    1. Finding the actual location of the hunk's context/removed lines in the original file.
    2. Recalculating the line counts for both the source and target file based on
       the lines present in the hunk body.
    3. Reconstructing the hunk header with the corrected values.

    Args:
        diff_content (str): The normalized diff content.
        original_content (str): The normalized original file content.

    Returns:
        str: The diff content with fully corrected hunk headers.
    """
    corrected_diff_lines = []
    original_lines = original_content.splitlines()
    diff_lines = diff_content.splitlines(True)

    # Create a stripped version of original_lines for whitespace-agnostic search
    stripped_original_lines = [line.strip() for line in original_lines]

    line_idx = 0
    while line_idx < len(diff_lines):
        line = diff_lines[line_idx]
        hunk_header_match = re.match(r"@@ -(\d+)(,(\d+))? \+(\d+)(,(\d+))? @@.*", line)

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

        while hunk_body_idx < len(diff_lines) and not diff_lines[hunk_body_idx].startswith("@@ "):
            hunk_line = diff_lines[hunk_body_idx]
            hunk_body_lines.append(hunk_line)

            if hunk_line.startswith((" ", "-")):
                # Strip the search pattern lines for robust matching
                hunk_search_pattern.append(hunk_line[1:].strip())

            if not hunk_line.startswith("+"):
                source_line_count += 1
            if not hunk_line.startswith("-"):
                target_line_count += 1

            hunk_body_idx += 1

        actual_start_line = -1
        if hunk_search_pattern:
            # Whitespace-agnostic search
            for i in range(len(stripped_original_lines) - len(hunk_search_pattern) + 1):
                # Compare stripped slices of the original content
                if stripped_original_lines[i : i + len(hunk_search_pattern)] == hunk_search_pattern:
                    actual_start_line = i + 1
                    break

        # If we found the context, correct the header
        if actual_start_line != -1:
            logging.info(
                f"Hunk correction: Original header was '@@ -{original_start_from_hunk},...'. Found whitespace-agnostic context at line {actual_start_line}."
            )

            # Recalculate target start line based on diff from original start
            target_start_from_hunk = int(hunk_header_match.group(4))
            start_line_diff = actual_start_line - original_start_from_hunk
            actual_target_start = target_start_from_hunk + start_line_diff

            # Reconstruct the header with corrected start lines and calculated counts
            new_header = f"@@ -{actual_start_line},{source_line_count} +{actual_target_start},{target_line_count} @@"
            header_comment_match = re.search(r"@@.*( @@.*)", line)
            if header_comment_match:
                new_header += header_comment_match.group(1)

            corrected_diff_lines.append(new_header + "\n")
            logging.info(f"Corrected Hunk Header: {new_header.strip()}")

        else:  # If context not found, keep original header but log a warning
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
    # Create a unique temporary directory within the sandbox
    temp_dir = tempfile.mkdtemp(dir="./.sandbox")
    try:
        # --- Normalize both inputs first for consistent processing ---
        normalized_original = _normalize_text(original_content)
        normalized_diff = _normalize_text(diff_content)

        # --- NEW: Correct hunk line numbers before attempting to patch ---
        corrected_diff = _correct_hunk_line_numbers(normalized_diff, normalized_original)
        if corrected_diff != normalized_diff:
            logging.info(f"Patch for {original_filename} had its hunk headers auto-corrected.")

        # The diff file expects a specific path, so we recreate it
        full_temp_path = os.path.join(temp_dir, original_filename)
        os.makedirs(os.path.dirname(full_temp_path), exist_ok=True)

        # Write the NORMALIZED original content to the temporary file
        # Use newline='\n' to ensure consistent line endings on write
        with open(full_temp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(normalized_original)

        # Create the patch set from the (potentially corrected) diff string
        patch_set = patch.fromstring(corrected_diff.encode("utf-8"))

        if not patch_set:
            return (
                None,
                "Failed to parse diff content. The patch may be malformed or empty.",
            )

        # Apply the patch using the temp directory as the root
        if patch_set.apply(root=temp_dir):
            # If successful, read the content of the patched file
            with open(full_temp_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            # The final content should match the normalized state, but we'll
            # rstrip just in case the patch library adds a final newline
            # to a file that was intended to have none.
            if not corrected_diff.endswith("\n"):
                return new_content.rstrip("\n"), None
            return new_content, None
        else:
            # --- Provide a much more detailed error message ---
            error_details = "Patch set could not be applied. This is often due to a mismatch between the file content and the patch."
            if hasattr(patch_set, "rejections") and patch_set.rejections:
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
