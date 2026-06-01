import subprocess
import os
import shutil

class CompilerError(Exception):
    """Exception raised for errors during compilation."""
    def __init__(self, message, stderr):
        super().__init__(message)
        self.stderr = stderr

def find_clang():
    """
    Attempts to locate the clang and clang++ compilers in the system.
    Looks in PATH first, then common default installation locations on Windows.
    """
    # 1. Search in PATH
    clang_path = shutil.which("clang")
    if clang_path:
        return clang_path

    # 2. Check common Windows install directories (e.g. LLVM installed via winget or installer)
    common_paths = [
        r"C:\Program Files\LLVM\bin\clang.exe",
        r"C:\Program Files (x86)\LLVM\bin\clang.exe",
        r"C:\msys64\mingw64\bin\clang.exe",
        r"C:\msys64\clang64\bin\clang.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
            
    return None

def find_clang_pp():
    """
    Attempts to locate clang++ using find_clang as a base.
    """
    clang = find_clang()
    if not clang:
        return None
    
    # Replace clang.exe with clang++.exe in the path
    if clang.lower().endswith("clang.exe"):
        clang_pp = clang[:-9] + "clang++.exe"
        if os.path.exists(clang_pp):
            return clang_pp
    
    # Try which
    clang_pp_path = shutil.which("clang++")
    if clang_pp_path:
        return clang_pp_path
        
    return None

def compile_to_ir(source_path, output_ll_path, opt_level="-O0", extra_flags=None, clang_path=None):
    """
    Compiles a C or C++ source file to LLVM IR (.ll format).
    
    Parameters:
        source_path (str): Path to the C/C++ source file.
        output_ll_path (str): Destination path for the .ll IR file.
        opt_level (str): Optimization level (e.g., '-O0', '-O1', '-O2', '-O3', '-Ofast').
        extra_flags (list): Additional compilation flags (e.g., ['-march=native', '-mllvm', '-vectorize-loops']).
        clang_path (str): Optional path to a specific clang executable.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")
        
    # Determine compiler (clang or clang++) based on extension
    ext = os.path.splitext(source_path)[1].lower()
    is_cpp = ext in [".cpp", ".cc", ".cxx", ".hpp", ".h"]
    
    if not clang_path:
        compiler = find_clang_pp() if is_cpp else find_clang()
    else:
        # If user provided a clang path, see if we need clang++ for C++ files
        if is_cpp and "clang.exe" in clang_path.lower():
            compiler = clang_path.lower().replace("clang.exe", "clang++.exe")
            if not os.path.exists(compiler):
                compiler = clang_path
        else:
            compiler = clang_path

    if not compiler or not os.path.exists(compiler) if compiler else True:
        # Re-check via shutil.which just in case
        fallback = shutil.which("clang++" if is_cpp else "clang")
        if fallback:
            compiler = fallback
        else:
            raise CompilerError(
                "Clang compiler could not be located.",
                "LLVM/Clang must be installed. Please ensure 'clang' or 'clang++' is in your PATH, "
                "or install LLVM using: winget install LLVM.LLVM"
            )

    # Base command: clang/clang++ -S -emit-llvm <opt_level> <source> -o <output>
    cmd = [compiler, "-S", "-emit-llvm", opt_level, source_path, "-o", output_ll_path]
    
    # Avoid debug symbols unless requested, but we want clean IR
    # Sometimes we want to compile without standard headers if they are missing, 
    # but for simple benchmarks, standard options are perfect.
    
    if extra_flags:
        cmd.extend(extra_flags)
        
    # Execute compilation
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            raise CompilerError(
                f"Compilation failed with exit code {result.returncode}.",
                result.stderr
            )
            
    except subprocess.SubprocessError as e:
        raise CompilerError(f"Subprocess execution error: {str(e)}", "")
        
    return output_ll_path

if __name__ == "__main__":
    # Self-test finding clang
    clang = find_clang()
    clang_pp = find_clang_pp()
    print(f"Located Clang: {clang}")
    print(f"Located Clang++: {clang_pp}")
