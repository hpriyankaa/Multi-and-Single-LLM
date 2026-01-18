
## Dataset Curation: 100 Syntax-Failure Programs

This directory contains the data cleaning and shortlisting methodology used to construct a benchmark of **100 unique Python programs exhibiting syntax-level failures** from the Yaksh online programming portal maintained by IIT Bombay.

### Source Dataset
The Yaksh corpus consists of approximately **2.81 million student submissions** across **398 introductory Python programming questions**, collected from programming assignments.

### Goal
The objective of this preprocessing pipeline is to extract a **small, diverse, and high-quality subset of authentic syntax errors** that reflect realistic student mistakes, while avoiding trivial, redundant, or non-informative submissions.

### Shortlisting Procedure

The selection process is deterministic and consists of the following steps:

1. **Explicit Syntax Error Detection**  
   Submissions were first scanned for explicit syntax-related feedback using pattern matching over known Python parser messages (e.g., `SyntaxError`, `IndentationError`, `TabError`, and common parse-time diagnostics such as *unexpected indent* or *EOF while parsing*).

2. **Compile-Time Fallback for Missing Feedback**  
   For submissions where execution feedback was empty, the submitted code was re-evaluated using Python’s built-in `compile()` function. Programs that failed during compilation were retained as valid syntax-error instances, recovering latent parse-time failures.

3. **Filtering Non-Informative Code**  
   Trivial or uninformative submissions—such as empty programs, single identifiers, or bare function calls—were excluded. Only submissions exhibiting meaningful program structure (e.g., function definitions, control flow, assignments) were retained.

4. **Deduplication via Structural Normalization**  
   To eliminate near-duplicate programs, code was normalized by abstracting identifiers, literals, and formatting, followed by hashing the canonical representation. Submissions with identical hashes were treated as duplicates and only one instance was kept.

5. **Diversity Control Across Questions**  
   To avoid over-representation of frequently attempted problems, at most one submission per programming question was selected in the primary pass. This constraint was relaxed only if necessary to reach the target size.

### Final Dataset
The resulting benchmark consists of **100 unique, authentic parse-time failures** produced by the Python interpreter. Each program corresponds to a distinct student submission and reflects real-world syntax errors encountered in introductory programming courses.

This curated dataset ensures **diversity, realism, and full reproducibility** from the original Yaksh corpus.
