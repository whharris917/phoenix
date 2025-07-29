import difflib

# Define file paths
original_file = 'the_a_file.txt'
modified_file = 'the_b_file_goal.txt'
diff_output_file = 'generated.diff'

# Read the content of both files
with open(original_file, 'r', encoding='utf-8') as f:
    original_lines = f.readlines()

with open(modified_file, 'r', encoding='utf-8') as f:
    modified_lines = f.readlines()

# Generate the unified diff
diff = difflib.unified_diff(
    original_lines,
    modified_lines,
    fromfile=f"a/sandbox/{original_file}",
    tofile=f"b/sandbox/the_b_file.txt"
)

# Write the diff to the output file
with open(diff_output_file, 'w', encoding='utf-8') as f:
    f.writelines(diff)

print(f"Successfully generated diff file: {diff_output_file}")