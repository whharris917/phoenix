import argparse
import difflib
import sys
import os

def create_diff(file_a_path, file_b_path):
    """
    Reads two files and prints a unified diff to standard output.

    Args:
        file_a_path (str): The path to the first file (the "original" file).
        file_b_path (str): The path to the second file (the "new" file).
    """
    try:
        # Read the contents of file A
        with open(file_a_path, 'r', encoding='utf-8') as file_a:
            file_a_lines = file_a.readlines()

        # Read the contents of file B
        with open(file_b_path, 'r', encoding='utf-8') as file_b:
            file_b_lines = file_b.readlines()

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred while reading the files: {e}", file=sys.stderr)
        sys.exit(1)

    # Get the relative filenames for the diff header
    fromfile = os.path.relpath(file_a_path)
    tofile = os.path.relpath(file_b_path)

    # Generate the unified diff
    # fromfile and tofile arguments are used to create the --- a/ and +++ b/ headers
    diff = difflib.unified_diff(
        file_a_lines,
        file_b_lines,
        fromfile=fromfile,
        tofile=tofile
    )

    # Print the diff to standard output
    for line in diff:
        sys.stdout.write(line)

def main():
    """
    Parses command-line arguments and initiates the diff creation.
    """
    parser = argparse.ArgumentParser(
        description="Generate a unified diff for two files.",
        epilog="Example: python create_diff.py -a original.txt -b modified.txt > my_patch.diff"
    )
    parser.add_argument(
        '-a', '--file_a',
        required=True,
        help="The path to the original file (file 'a')."
    )
    parser.add_argument(
        '-b', '--file_b',
        required=True,
        help="The path to the modified file (file 'b')."
    )

    args = parser.parse_args()

    create_diff(args.file_a, args.file_b)

if __name__ == "__main__":
    main()
