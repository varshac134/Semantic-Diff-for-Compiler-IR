# Semantic IR Diff

A standalone tool for comparing two source or LLVM IR revisions and reporting semantic LLVM IR differences.

## Install

From the repository root:

```powershell
cd c:\Users\chind\Downloads\fight\model_release
.\.venv\Scripts\python.exe -m pip install -e .\semantic_ir_diff_project
```

## Usage

```powershell
cd c:\Users\chind\Downloads\fight\model_release
.\.venv\Scripts\semantic-ir-diff old_file.c new_file.c --opt-level -O3
```

## Example inputs

The repository includes example source and LLVM IR inputs in `examples/`.

```powershell
cd c:\Users\chind\Downloads\semantic_ir_diff_project
python -m semantic_ir_diff.cli examples\old.ll examples\new.ll --old-ir --new-ir --report-detail all
```

For more details, see `examples/README.md`.

For evaluation across commit pairs:

```powershell
cd c:\Users\chind\Downloads\fight\model_release
.\.venv\Scripts\semantic-ir-diff-eval --repo-path . --manifest semantic_ir_diff_project/docs/evaluation_manifest_example.csv --detail
```

## Clang support

Install LLVM/Clang locally using:

```powershell
cd c:\Users\chind\Downloads\fight\model_release
.\semantic_ir_diff_project\scripts\install_clang.ps1
```

If automatic download fails, download a prebuilt LLVM archive manually and pass it with `-ArchivePath`.
