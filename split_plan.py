import os

def split_markdown_file(file_path, output_dir="."):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Define delimiters
    delimiters = ["You said:"]

    # Split content
    parts = []
    current_part = []
    part_number = 1

    lines = content.splitlines(keepends=True)
    for line in lines:
        is_delimiter_line = False
        for delimiter in delimiters:
            if line.strip().startswith(delimiter):
                is_delimiter_line = True
                if current_part: # If there's content before this delimiter, save it as a part
                    parts.append("".join(current_part))
                    current_part = []
                current_part.append(line) # Start new part with the delimiter line
                break
        
        if not is_delimiter_line:
            current_part.append(line)
    
    # Add the last part
    if current_part:
        parts.append("".join(current_part))

    # Write parts to new files
    for i, part_content in enumerate(parts):
        output_filename = os.path.join(output_dir, f"{i + 1}.md")
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(part_content.strip()) # strip to remove leading/trailing newlines
            print(f"Created '{output_filename}'")
        except Exception as e:
            print(f"Error writing to file '{output_filename}': {e}")

if __name__ == "__main__":
    input_file = "plan_part2.md"
    output_directory = "split_plan_files" # Name of the directory for split files
    split_markdown_file(input_file, output_directory)

    # The user also asked about generating a python virtual environment.
    # This part of the request seems to be separate from the script's core function,
    # as the script itself doesn't have complex dependencies requiring a venv.
    # If the user specifically wants to create a venv for running *this* script
    # or for the project in general, they would typically do it with:
    # python3 -m venv venv
    # source venv/bin/activate
    # For now, I'm just writing the script.
