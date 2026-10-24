import re

file_path = 'quentin/council/manager.py'

with open(file_path, 'r') as f:
    content = f.read()

# Extract the methods
load_config_start_marker = '# ----- 配置加载 -----' 
build_fallback_start_marker = 'def _build_fallback_config(self, name: str, topic: str) -> CouncilConfig:'

load_config_start_index = content.find(load_config_start_marker)
build_fallback_start_index = content.find(build_fallback_start_marker, load_config_start_index)

# Find end of _build_fallback_config
next_def_or_eof = len(content)
# Assume end of file
build_fallback_end_idx = next_def_or_eof

load_config_and_fallback_methods_unindented = content[load_config_start_index:build_fallback_end_idx]

# Indent methods to be inserted into the class
indented_methods = "    " + "\n    ".join(load_config_and_fallback_methods_unindented.splitlines())


# Remove the methods from their original position
content_without_moved = content[:load_config_start_index]

# Find where to insert
init_end_marker = '        self._load_config()\n'
insertion_point = content_without_moved.find(init_end_marker) + len(init_end_marker)

# Construct final content
final_content = (
    content_without_moved[:insertion_point] +
    indented_methods +
    '\n' +
    content_without_moved[insertion_point:]
)

with open(file_path, 'w') as f:
    f.write(final_content)

print("Successfully moved methods into CouncilManager class.")
