# Semantic Diff for Compiler LLVM IR

A high-fidelity tool written in Python that normalizes and analyzes LLVM IR (Intermediate Representation) between two revisions of a source code file to identify semantic differences, compiler optimizations gained/lost, control flow simplification, and memory access modifications.

Unlike normal textual diff tools (such as `git diff`) which only show syntactic code modifications, `semantic-ir-diff` helps developers and performance engineers understand the actual optimization and code-generation impact of their changes.

---

## Key Features

1. **IR Normalization Pipeline**: Strips debug metadata, target attributes, and parameter tags. Canonicalizes basic block labels using DFS graph traversal and renames local registers sequentially.
2. **CFG Structural Diff Engine**: Compares Control Flow Graphs, matching basic blocks using custom similarity metrics based on opcode sequences and CFG neighbor layouts.
3. **Change Classifier**: Maps raw edits to high-level compiler optimizations:
   - **Vectorization** (Gained, Lost, Modified width)
   - **Function Inlining** (Gained/Lost)
   - **Loop Unrolling** (Gained/Lost, unroll factors)
   - **Control Flow / Branch Elimination**
   - **Memory to Register Promotion (mem2reg)**
   - **Constant Folding / Strength Reduction**
4. **Interactive CLI & HTML Reports**: Outputs a color-coded terminal report or exports interactive, responsive, stand-alone HTML reports.
5. **E2E Evaluation Suite**: Includes 10 real-world benchmark optimization test cases programmatically compiled and validated.

---

## File Structure

- `compiler.py` - Wraps Clang to compile C/C++ to LLVM IR (`.ll`).
- `normalizer.py` - Strips metadata and canonicalizes labels/registers.
- `parser.py` - Parses normalized IR into structured CFG objects.
- `cfg_diff.py` - Performs structural and instruction diffing.
- `classifier.py` - Classifies edits into semantic optimizations.
- `cli.py` - Orchestrates the pipeline; produces colorized CLI or HTML output.
- `evaluator.py` - Compiles and validates the 10 built-in optimization test cases.

---

## Installation & Setup

1. **Install LLVM / Clang**:
   Ensure `clang` is in your command path, or install LLVM using:
   ```powershell
   winget install LLVM.LLVM
   ```

2. **Run the CLI**:
   - Compare a file under two different optimization levels:
     ```bash
     python cli.py my_code.c -O1 -o -O3
     ```
   - Compare two git revisions of a source file:
     ```bash
     python cli.py my_code.c --rev1 HEAD~1 --rev2 HEAD
     ```
   - Compare two pre-compiled `.ll` IR files:
     ```bash
     python cli.py old.ll new.ll
     ```
   - Generate an interactive HTML report:
     ```bash
     python cli.py my_code.c -O1 -o -O3 -f html -out report.html
     ```

3. **Run the Evaluation Suite**:
   ```bash
   python evaluator.py
   ```
