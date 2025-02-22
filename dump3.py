#!/usr/bin/env python3

import os
import sys
import fnmatch
import json
from typing import List, Set, Optional

##############################################################################
# 1. CHUNKED WRITER
##############################################################################

CHUNK_READ_SIZE = 4096  # used if reading large files in chunks

class ChunkedFileWriter:
    """
    Writes content to multiple output files when the size exceeds chunk_size_bytes.
    Useful for handling large output that needs to be split into manageable files.
    """
    def __init__(self, base_filename: str, chunk_size_bytes: int):
        self.base_filename = base_filename
        self.chunk_size_bytes = chunk_size_bytes
        self.current_file_index = 1
        self.current_file = None
        self.current_file_path = None
        self.current_size = 0
        self._open_new_file()

    def _open_new_file(self):
        """Creates a new file with incrementing index when chunk size is reached."""
        if self.current_file:
            self.current_file.close()

        file_name, file_ext = os.path.splitext(self.base_filename)
        self.current_file_path = f"{file_name}_part_{self.current_file_index}{file_ext}"
        self.current_file_index += 1

        self.current_file = open(self.current_file_path, 'w', encoding='utf-8')
        self.current_size = 0

    def write(self, text: str):
        """Writes text to current file, opening new file if chunk size is exceeded."""
        text_bytes = text.encode('utf-8', errors='replace')
        if self.current_size + len(text_bytes) > self.chunk_size_bytes:
            self._open_new_file()
        self.current_file.write(text)
        self.current_size += len(text_bytes)

    def close(self):
        """Closes the current file if open."""
        if self.current_file:
            self.current_file.close()
            self.current_file = None

##############################################################################
# 2. EXCLUSION PATTERN FUNCTIONS
##############################################################################

def get_excluded_extensions() -> Set[str]:
    """
    Returns a normalized set of file extensions that should always be excluded.
    Extensions are stored without the dot and in lowercase.
    """
    return {
        # Images
        'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico', 'tif', 'tiff', 'bmp',
        # Audio/Video
        'mp4', 'mp3', 'wav', 'ogg', 'flac', 'webm', 'mov', 'avi',
        # Archives
        'rar', '7z', 'tar', 'gz', 'bz2', 'zip', 'xz',
        # Data/Config
        'csv', 'json', 'yaml', 'yml',
        # JavaScript/TypeScript
        'js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs', 'mts', 'cts',
        # Python
        'pyc', 'pyo', 'pyd',
        # Other
        'jar', 'pem', 'log'
    }

def parse_exclusion_files(file_paths: List[str]) -> Set[str]:
    """
    Enhanced exclusion pattern parser that handles various pattern formats.
    Normalizes patterns and handles comments properly.
    """
    patterns = set()
    excluded_extensions = get_excluded_extensions()
    
    # Add standard extension patterns
    for ext in excluded_extensions:
        patterns.add(f"*.{ext}")
        patterns.add(f"**/*.{ext}")
    
    # Add common version control and environment patterns
    common_paths = {
        '.git', '.idea', '.venv', 'venv', 'node_modules',
        'build', 'dist', '.tox', 'coverage', 'htmlcov',
        '.mypy_cache', '.ruff_cache'
    }
    for path in common_paths:
        patterns.add(path)
        patterns.add(f"{path}/**")
        patterns.add(f"**/{path}/**")
    
    # Process exclusion files
    for file_path in file_paths:
        if not file_path or not os.path.exists(file_path):
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Remove comments and whitespace
                line = line.split('#')[0].strip()
                if not line:
                    continue
                
                # Normalize path separators and remove leading/trailing slashes
                pattern = line.replace('\\', '/').strip('/')
                
                # Skip empty patterns after normalization
                if not pattern:
                    continue
                
                # Handle different pattern types
                if pattern.startswith('**/'):
                    # Global pattern, add as is
                    patterns.add(pattern)
                elif pattern.startswith('*.'):
                    # Extension pattern, add both forms
                    patterns.add(pattern)
                    patterns.add(f"**/{pattern}")
                elif any(c in pattern for c in '*?['):
                    # Other wildcard pattern, add as is
                    patterns.add(pattern)
                else:
                    # Directory/file pattern, add variations
                    patterns.add(pattern)
                    patterns.add(f"{pattern}/**")
                    patterns.add(f"**/{pattern}/**")
    
    return patterns



def should_skip_directory(dir_name: str, rel_path: str, exclusion_patterns: Set[str]) -> bool:
    """
    Determines if a directory should be skipped based on its name and relative path.
    Handles both explicit directory patterns and general exclusion patterns.
    """
    # Define protected file extensions that should prevent directory skipping
    PROTECTED_EXTENSIONS = {'.py', '.groovy', '.r', '.rmd', '.md', '.ipynb'}
    
    # Always skip these directories regardless of pattern matching
    ALWAYS_SKIP = {
        '.git', '.idea', '.venv', 'venv', 'node_modules',
        'build', 'dist', '.tox', 'coverage', 'htmlcov'
    }
    
    if dir_name in ALWAYS_SKIP:
        print(f"Skipping directory {rel_path} - in always skip list")
        return True
        
    # Normalize path for consistent matching
    normalized_path = rel_path.replace('\\', '/').lower()
    dir_name = dir_name.lower()
    
    # Skip hidden directories (starting with .) unless they contain protected files
    if dir_name.startswith('.') and dir_name != '.':  # Allow current directory
        try:
            # Try to check if directory contains protected files
            if os.path.exists(rel_path):
                for ext in PROTECTED_EXTENSIONS:
                    try:
                        if any(f.endswith(ext) for f in os.listdir(rel_path)):
                            print(f"Keeping hidden directory {normalized_path} - contains protected files")
                            return False
                    except OSError:
                        continue
            print(f"Skipping hidden directory: {normalized_path}")
            return True
        except Exception as e:
            print(f"Warning: Error checking directory {normalized_path} - {str(e)}")
            return True
        
    # Check against exclusion patterns
    for pattern in exclusion_patterns:
        pattern = pattern.lower()
        
        # Skip the overly broad .* pattern
        if pattern == '.*':
            continue
            
        # Remove any trailing '/**' for directory matching
        if pattern.endswith('/**'):
            pattern = pattern[:-3]
            
        # Check both the directory name and full path
        if fnmatch.fnmatch(dir_name, pattern) or fnmatch.fnmatch(normalized_path, pattern):
            try:
                # Check if directory exists and contains protected files
                if os.path.exists(rel_path):
                    for ext in PROTECTED_EXTENSIONS:
                        try:
                            if any(f.endswith(ext) for f in os.listdir(rel_path)):
                                print(f"Keeping directory {normalized_path} - contains protected files")
                                return False
                        except OSError:
                            continue
                print(f"Skipping directory {normalized_path} - matches pattern {pattern}")
                return True
            except Exception as e:
                print(f"Warning: Error checking directory {normalized_path} - {str(e)}")
                return True
            
    return False







def should_exclude_file(file_name: str, file_rel_path: str, exclusion_patterns: Set[str]) -> bool:
    """
    Enhanced file exclusion check with improved pattern matching.
    Handles various pattern types and normalizes paths consistently.
    """
    # Define protected extensions that should never be excluded
    PROTECTED_EXTENSIONS = {'.py', '.groovy', '.r', '.rmd', '.md', '.ipynb'}
    
    # Special case: always exclude license.md regardless of protection
    if file_name.lower() == 'license.md':
        print(f"Excluding {file_rel_path} - license.md is explicitly excluded")
        return True
    
    # Normalize paths for consistent matching
    normalized_name = file_name.lower()
    normalized_path = file_rel_path.replace('\\', '/').lower()
    
    # Check if file has a protected extension
    if any(normalized_name.endswith(ext) for ext in PROTECTED_EXTENSIONS):
        print(f"Keeping {file_rel_path} - protected file type")
        return False
    
    # Rest of the function remains the same...

def process_file(
    file_path: str,
    file_rel_path: str,
    safe_write,
    skip_substrings: Optional[List[str]] = None,
    strip_ipynb_outputs: bool = True
) -> None:
    """
    Processes a single file, handling different file types appropriately.
    """
    safe_write(f"Content of {file_rel_path}:\n")

    # Handle Jupyter notebooks specially
    _, ext = os.path.splitext(file_path)
    if ext.lower() == ".ipynb":
        try:
            with open(file_path, 'r', encoding='utf-8') as fin:
                nb_data = json.load(fin)

            # Remove outputs and image data from each cell
            cells = nb_data.get("cells", [])
            for cell in cells:
                # Remove outputs
                if "outputs" in cell:
                    # Keep text outputs but remove image data
                    filtered_outputs = []
                    for output in cell["outputs"]:
                        # Keep only text/plain outputs
                        if output.get("output_type") == "stream" or \
                           (output.get("output_type") == "execute_result" and 
                            "text/plain" in output.get("data", {})):
                            # Keep only text/plain data if it's an execute result
                            if output.get("output_type") == "execute_result":
                                output["data"] = {"text/plain": output["data"]["text/plain"]}
                            filtered_outputs.append(output)
                    cell["outputs"] = filtered_outputs
                
                # Remove execution count
                if "execution_count" in cell:
                    cell["execution_count"] = None

            # Write processed notebook
            nb_str = json.dumps(nb_data, ensure_ascii=False, indent=2)
            safe_write(nb_str)
            safe_write("\n")

        except Exception as e:
            safe_write(f"Error processing .ipynb file: {str(e)}\n")
        return

    # Handle all other files normally
    try:
        with open(file_path, 'r', encoding='utf-8') as fin:
            while True:
                chunk = fin.readline()
                if not chunk:
                    break
                if skip_substrings and any(sub in chunk for sub in skip_substrings):
                    continue
                safe_write(chunk)
    except Exception as e:
        safe_write(f"Error reading file: {str(e)}. Content skipped.\n")














##############################################################################
# 3. DIRECTORY TREE PRINTER
##############################################################################

def print_directory_structure(start_path: str, exclusion_patterns: Set[str]) -> str:
    """
    Returns a tree-like directory structure string, respecting exclusion patterns.
    Creates a visual representation of the directory hierarchy.
    """
    def _generate_tree(dir_path: str, prefix: str = ''):
        entries = os.listdir(dir_path)
        entries = sorted(entries, key=lambda x: (not os.path.isdir(os.path.join(dir_path, x)), x.lower()))
        tree = []
        for i, entry in enumerate(entries):
            rel_path = os.path.relpath(os.path.join(dir_path, entry), start_path)
            
            # Skip excluded paths
            if should_exclude_file(entry, rel_path, exclusion_patterns):
                continue

            # Determine the appropriate connector based on position
            if i == len(entries) - 1:
                connector = '└── '
                new_prefix = prefix + '    '
            else:
                connector = '├── '
                new_prefix = prefix + '│   '

            full_path = os.path.join(dir_path, entry)
            if os.path.isdir(full_path):
                if not should_skip_directory(entry, rel_path, exclusion_patterns):
                    tree.append(f"{prefix}{connector}{entry}/")
                    tree.extend(_generate_tree(full_path, new_prefix))
            else:
                tree.append(f"{prefix}{connector}{entry}")
        return tree

    tree = ['/ '] + _generate_tree(start_path)
    return '\n'.join(tree)

##############################################################################
# 4. PROCESSING FUNCTION
##############################################################################

def process_file(
    file_path: str,
    file_rel_path: str,
    safe_write,
    skip_substrings: Optional[List[str]] = None,
    strip_ipynb_outputs: bool = True
) -> None:
    """
    Processes a single file, handling different file types appropriately.
    
    For .ipynb files:
    - Removes cell outputs if strip_ipynb_outputs is True
    - Preserves notebook structure
    
    For all other files:
    - Reads and writes content line by line
    - Optionally skips lines containing specific substrings
    """
    safe_write(f"Content of {file_rel_path}:\n")

    # Handle Jupyter notebooks specially
    _, ext = os.path.splitext(file_path)
    if ext.lower() == ".ipynb" and strip_ipynb_outputs:
        try:
            with open(file_path, 'r', encoding='utf-8') as fin:
                nb_data = json.load(fin)

            # Remove outputs from each cell
            cells = nb_data.get("cells", [])
            for cell in cells:
                if "outputs" in cell:
                    cell["outputs"] = []
                if "execution_count" in cell:
                    cell["execution_count"] = None
            nb_data["cells"] = cells

            # Write processed notebook
            nb_str = json.dumps(nb_data, ensure_ascii=False, indent=2)
            for line in nb_str.splitlines(True):
                if not (skip_substrings and any(sub in line for sub in skip_substrings)):
                    safe_write(line)

        except Exception as e:
            safe_write(f"Error processing .ipynb file: {str(e)}\n")
        return

    # Handle all other files
    try:
        with open(file_path, 'r', encoding='utf-8') as fin:
            while True:
                chunk = fin.readline()
                if not chunk:
                    break
                if skip_substrings and any(sub in chunk for sub in skip_substrings):
                    continue
                safe_write(chunk)
    except Exception as e:
        safe_write(f"Error reading file: {str(e)}. Content skipped.\n")

##############################################################################
# 5. SCAN FOLDER
##############################################################################

def scan_folder(
    start_path: str,
    file_types: Optional[List[str]],
    output_file: str,
    exclusion_patterns: Set[str],
    max_chunk_size_mb: Optional[int] = None,
    skip_substrings: Optional[List[str]] = None,
    strip_ipynb_outputs: bool = True
) -> None:
    """
    Main function that scans a folder and processes its contents.
    Handles file exclusions, chunking, and writing output.
    """
    # Initialize the appropriate writer
    if max_chunk_size_mb is not None and max_chunk_size_mb > 0:
        chunk_size_bytes = max_chunk_size_mb * 1024 * 1024
        writer = ChunkedFileWriter(output_file, chunk_size_bytes)
    else:
        writer = open(output_file, 'w', encoding='utf-8')

    def safe_write(text: str):
        """Wrapper to handle writing to either chunked or regular writer."""
        if isinstance(writer, ChunkedFileWriter):
            writer.write(text)
        else:
            writer.write(text)

    try:
        # Write directory structure
        safe_write("Directory Structure:\n")
        safe_write("-------------------\n")
        safe_write(print_directory_structure(start_path, exclusion_patterns))
        safe_write("\n\n")

        safe_write("File Contents:\n")
        safe_write("--------------\n")

        # Walk through directory tree
        for root, dirs, files in os.walk(start_path, topdown=True):
            rel_path = os.path.relpath(root, start_path)
            
            # Filter directories before traversing
            dirs[:] = [d for d in dirs 
                      if not should_skip_directory(d, os.path.join(rel_path, d), exclusion_patterns)]
            
            # Process each file in current directory
            for file in files:
                file_rel_path = os.path.join(rel_path, file).replace('\\', '/')
                
                # Skip excluded files
                if should_exclude_file(file, file_rel_path, exclusion_patterns):
                    # print(f"🚨 Excluded: {file_rel_path} due to {exclusion_patterns}")
                    continue
                
                # Apply file type filtering if specified
                if file_types and not any(file.lower().endswith(ext.lower()) for ext in file_types):
                    continue
                
                # Process the file
                file_path = os.path.join(root, file)
                print(f"Processing: {file_rel_path}")
                safe_write(f"\nFile: {file_rel_path}\n")
                safe_write("-" * 50 + "\n")
                
                process_file(
                    file_path=file_path,
                    file_rel_path=file_rel_path,
                    safe_write=safe_write,
                    skip_substrings=skip_substrings,
                    strip_ipynb_outputs=strip_ipynb_outputs
                )
                safe_write("\n")
    finally:
        # Ensure writer is properly closed
        if isinstance(writer, ChunkedFileWriter):
            writer.close()
        else:
            writer.close()

##############################################################################
# 6. MAIN CLI
##############################################################################

def main():
    """
    Command-line interface for the script.
    
    Usage:
        python dump3.py <start_path> <output_file> [exclusion_files...] [file_extensions...]
                       [--max-chunk-size <MB>] [--skip-substring <SUB> ...] [--no-ipynb-strip]
    
    Arguments:
        start_path: Directory to start scanning from
        output_file: Where to write the output
        exclusion_files: One or more files containing exclusion patterns
        file_extensions: Optional list of file extensions to include
        
    Options:
        --max-chunk-size <MB>: Split output into chunks of this size
        --skip-substring <SUB>: Skip lines containing this substring
        --no-ipynb-strip: Don't strip outputs from Jupyter notebooks
    """
    if len(sys.argv) < 3:
        print("Usage: python dump3.py <start_path> <output_file> [exclusion_files...] [file_extensions...] "
              "[--max-chunk-size <MB>] [--skip-substring <SUB> ...] [--no-ipynb-strip]")
        sys.exit(1)

    # Parse basic arguments
    start_path = sys.argv[1]
    output_file = sys.argv[2]

    # Initialize optional parameters
    exclusion_files: List[str] = []
    file_types: Optional[List[str]] = None
    max_chunk_size_mb: Optional[int] = None
    skip_substrings: List[str] = []
    strip_ipynb_outputs = True

    # Parse remaining arguments
    remaining_args = sys.argv[3:]
    i = 0
    while i < len(remaining_args):
        arg = remaining_args[i]
        
        # Handle file extensions
        if arg.startswith('.'):
            file_types = remaining_args[i:]
            break
            
        # Handle chunk size
        elif arg == '--max-chunk-size':
            if i + 1 < len(remaining_args):
                try:
                    max_chunk_size_mb = int(remaining_args[i+1])
                    i += 2
                except ValueError:
                    print("Error: --max-chunk-size requires an integer value (MB).")
                    sys.exit(1)
            else:
                print("Error: --max-chunk-size requires an integer value (MB).")
                sys.exit(1)
                
        # Handle skip substring
        elif arg == '--skip-substring':
            if i + 1 < len(remaining_args):
                skip_substrings.append(remaining_args[i+1])
                i += 2
            else:
                print("Error: --skip-substring requires a substring argument.")
                sys.exit(1)
                
        # Handle notebook output stripping
        elif arg == '--no-ipynb-strip':
            strip_ipynb_outputs = False
            i += 1
            
        # Treat as exclusion file
        else:
            exclusion_files.append(arg)
            i += 1

    # Parse exclusion patterns from files
    exclusion_patterns = parse_exclusion_files(exclusion_files)

    # Print summary of settings
    if exclusion_files:
        print(f"Exclusion patterns: {exclusion_patterns}")
    if file_types:
        print(f"Filtering for these file types: {file_types}")
    if skip_substrings:
        print(f"Skipping lines containing: {skip_substrings}")
    if strip_ipynb_outputs:
        print("Will strip outputs from .ipynb files.")

    # Execute main scanning function
    try:
        scan_folder(
            start_path=start_path,
            file_types=file_types,
            output_file=output_file,
            exclusion_patterns=exclusion_patterns,
            max_chunk_size_mb=max_chunk_size_mb,
            skip_substrings=skip_substrings,
            strip_ipynb_outputs=strip_ipynb_outputs
        )
        print(f"Completed. Output written to file(s) starting with '{output_file}'")
    except Exception as e:
        print(f"Error during execution: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
            