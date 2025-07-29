original_file = 'orchestrator_original.py'
new_file = 'orchestrator_new.py'
patch_file = 'orchestrator_full.patch'
target_project_filename = 'orchestrator.py'

try:
    with open(original_file, 'r', encoding='utf-8') as f:
        original_lines = f.readlines()

    with open(new_file, 'r', encoding='utf-8') as f:
        new_lines = f.readlines()

    patch_content = []
    patch_content.append(f'--- a/{target_project_filename}\n')
    patch_content.append(f'+++ b/{target_project_filename}\n')
    patch_content.append(f'@@ -1,{len(original_lines)} +1,{len(new_lines)} @@\n')

    for line in original_lines:
        patch_content.append('-' + line)

    for line in new_lines:
        patch_content.append('+' + line)

    with open(patch_file, 'w', encoding='utf-8') as f:
        f.writelines(patch_content)
    
    print(f"Successfully generated full patch file: {patch_file}")

except Exception as e:
    print(f"An error occurred: {e}")