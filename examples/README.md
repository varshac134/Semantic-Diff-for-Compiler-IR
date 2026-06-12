# Example Inputs

This folder contains example inputs for the `semantic-ir-diff` tool.

## Files

- `old.c` — original source version.
- `new.c` — updated source version with inline optimization.
- `old.ll` — original LLVM IR version.
- `new.ll` — updated LLVM IR version.

## Run the CLI

Use the example IR files directly:

```powershell
cd c:\Users\chind\Downloads\semantic_ir_diff_project
python -m semantic_ir_diff.cli examples\old.ll examples\new.ll --old-ir --new-ir --report-detail all
```

Or compile the source examples using Clang (if installed):

```powershell
python -m semantic_ir_diff.cli examples\old.c examples\new.c --opt-level -O3 --report-detail all
```
