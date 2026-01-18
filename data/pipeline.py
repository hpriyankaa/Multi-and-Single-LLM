"""
Error Type Extraction + Proof Artifacts (READY TO PASTE) — FINAL VERSION

Fixes included:
1) Grader assertion messages like "AssertionError in: assert ..." are NOT Python tracebacks.
   They are labeled: AssertionFailure_Grader.
2) Rows where error text literally says "Correct answer" are labeled: CorrectAnswerInErrorField.

Outputs:
- error_counts_clean.csv
- audit_examples.jsonl (<= N examples per label)
- manual_label_sample.csv (<= N examples per label)

Streaming-friendly for huge JSONL files.
"""

import json
import re
import ast
import csv
import builtins
import random
from collections import Counter
from typing import Any, Dict, List, Optional


# ============================================================
# 1) Whitelist of valid exceptions
# ============================================================
BUILTIN_EXCEPTIONS = {
    name for name, obj in vars(builtins).items()
    if isinstance(obj, type) and issubclass(obj, BaseException)
}

# Add only if you intentionally want extra non-builtin exceptions:
EXTRA_EXCEPTIONS = set()
# Example:
# EXTRA_EXCEPTIONS = {"AxisError"}

ALLOWED_EXCEPTIONS = BUILTIN_EXCEPTIONS | EXTRA_EXCEPTIONS


# ============================================================
# 2) Patterns (traceback-aware exception extraction)
# ============================================================
TB_RE = re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE)
COLON_EXC_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception))\s*:", re.IGNORECASE)
DASH_EXC_RE = re.compile(r"Error\s+Traceback\s*-\s*([A-Z][A-Za-z0-9_]*(?:Error|Exception))\b", re.IGNORECASE)
EXC_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception))\b")


# ============================================================
# 3) Non-exception classification patterns
# ============================================================
WRONG_ANSWER_PATTERNS = [
    r"\bincorrect\s+answer\b",
    r"\bwrong\s+answer\b",
    r"\bdid\s+not\s+match\b",
    r"\bline\s+number\(s\)\b.*\bdid\s+not\s+match\b",
    r"\bexpected\s+\d+\s+number\s+of\s+lines\b",
    r"\bwe\s+had\s+expected\b.*\bwe\s+got\b",
    r"\boutput\s+mismatch\b",
]

TIME_LIMIT_PATTERNS = [
    r"\btime\s+limit\b",
    r"\btime\s+limit\s+exceeded\b",
    r"\btimeout\b",
    r"\btimed?\s+out\b",
    r"\bcode\s+took\s+more\s+than\b",
    r"\binfinite\s+loop\b",
    r"\bexecution\s+time\s+exceeded\b",
]

MEMORY_LIMIT_PATTERNS = [
    r"\bmemory\s+limit\b",
    r"\bmemory\s+limit\s+exceeded\b",
    r"\bout\s+of\s+memory\b",
    r"\bmemory\s+exceeded\b",
]

RUNTIME_ERROR_GENERIC_PATTERNS = [
    r"\bruntime\s+error\b",
]


# ============================================================
# 4) Helpers
# ============================================================
def normalize_error_field(error_value: Any) -> List[Any]:
    """Normalize the 'error' field into a list, preserving dict structure."""
    if error_value is None:
        return []

    if isinstance(error_value, list):
        return error_value

    if isinstance(error_value, str):
        s = error_value.strip()
        if not s or s == "[]":
            return []

        # Try JSON first
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            pass

        # Try Python literal
        try:
            parsed = ast.literal_eval(s)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            pass

        return [s]

    return [error_value]


def _item_to_text_blobs(item: Any) -> List[str]:
    """Extract relevant text from an error item. Prefer dict keys like error_msg/traceback."""
    blobs = []
    if isinstance(item, dict):
        for k in ("error_msg", "traceback", "message", "stderr", "details", "error"):
            v = item.get(k)
            if isinstance(v, str) and v.strip():
                blobs.append(v)
        if not blobs:
            try:
                blobs.append(json.dumps(item, ensure_ascii=False))
            except Exception:
                blobs.append(str(item))
    else:
        blobs.append(str(item))
    return blobs


def _canonicalize_exception(name: str) -> Optional[str]:
    """Return canonical exception name if in whitelist, else None."""
    n = (name or "").strip()
    if not n:
        return None
    for a in ALLOWED_EXCEPTIONS:
        if a.lower() == n.lower():
            return a
    return None


def extract_exception_types(error_items: List[Any]) -> List[str]:
    """
    Extract Python exception types from traceback-like contexts only, then whitelist-filter.
    Returns unique exception types for the row.
    """
    found = set()

    for item in error_items:
        for txt in _item_to_text_blobs(item):
            t = txt or ""
            has_tb = bool(TB_RE.search(t))

            candidates = []
            # Strong evidence patterns (can exist even without full TB)
            candidates.extend(DASH_EXC_RE.findall(t))
            candidates.extend(COLON_EXC_RE.findall(t))

            # Only allow loose name matches if there's an actual Traceback header
            if has_tb and not candidates:
                candidates.extend(EXC_NAME_RE.findall(t))

            for c in candidates:
                canon = _canonicalize_exception(c)
                if canon:
                    found.add(canon)

    return list(found)


def classify_non_exception(error_items: List[Any]) -> str:
    """Classify rows with no extracted exception."""
    if not error_items:
        return "EmptyErrorList"

    blobs = []
    for item in error_items:
        blobs.extend(_item_to_text_blobs(item))

    combined = " ".join(blobs).strip()
    if not combined:
        return "EmptyErrorList"

    low = combined.lower()

    # FIX #1: "Correct answer" appearing in error field (data quirk)
    if re.search(r"\bcorrect\s+answer\b", low):
        return "CorrectAnswerInErrorField"

    # FIX #2: grader-level assertion failures (not a Python traceback)
    if "assertionerror" in low and "assert" in low and not TB_RE.search(combined):
        return "AssertionFailure_Grader"

    for pat in WRONG_ANSWER_PATTERNS:
        if re.search(pat, low, re.IGNORECASE):
            return "WrongAnswer"

    for pat in TIME_LIMIT_PATTERNS:
        if re.search(pat, low, re.IGNORECASE):
            return "TimeLimitExceeded"

    for pat in MEMORY_LIMIT_PATTERNS:
        if re.search(pat, low, re.IGNORECASE):
            return "MemoryLimitExceeded"

    for pat in RUNTIME_ERROR_GENERIC_PATTERNS:
        if re.search(pat, low, re.IGNORECASE):
            return "RuntimeError"

    return "OtherFailure"


# ============================================================
# 5) Proof artifacts (audit + manual labeling sample)
# ============================================================
def make_audit_record(obj: Dict[str, Any], label: str, evidence_texts: List[str], max_chars: int = 800) -> Dict[str, Any]:
    raw_err = obj.get("error")
    preview = str(raw_err)
    if len(preview) > max_chars:
        preview = preview[:max_chars] + " ...[truncated]"
    return {
        "question_id": obj.get("question_id"),
        "label": label,
        "evidence_texts": evidence_texts[:3],
        "error_preview": preview
    }


def write_audit_jsonl(audit_examples: Dict[str, List[Dict[str, Any]]], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        for label, rows in audit_examples.items():
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_manual_label_sample_csv(audit_examples: Dict[str, List[Dict[str, Any]]], out_csv: str, per_label: int = 50) -> None:
    rows = []
    for label, exs in audit_examples.items():
        take = exs if len(exs) <= per_label else random.sample(exs, per_label)
        for r in take:
            rows.append({
                "label_pred": r["label"],
                "question_id": r["question_id"],
                "evidence_text": " | ".join(r["evidence_texts"]),
                "error_preview": r["error_preview"],
                "label_human": ""  # fill manually later
            })

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["label_pred", "question_id", "evidence_text", "error_preview", "label_human"])
        w.writeheader()
        w.writerows(rows)


# ============================================================
# 6) Reporting
# ============================================================
def write_counts_csv(counts: Counter, out_csv: str) -> None:
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["error_type", "count"])
        for k, v in counts.most_common():
            w.writerow([k, v])


def print_report(counts: Counter, stats: Dict[str, int]) -> None:
    total = stats["total_rows"]
    print("\nSUMMARY")
    print("=" * 60)
    for k in [
        "total_rows",
        "missing_error_field",
        "null_error_field",
        "empty_error_field",
        "json_parse_errors",
        "rows_with_exceptions",
        "rows_without_exceptions",
        "rows_with_multiple_exceptions",
    ]:
        print(f"{k.replace('_',' ').title():30s}: {stats[k]:,}")

    print("\n" + "=" * 60)
    print("ERROR TYPE COUNTS (sorted by frequency)")
    print("=" * 60)
    for et, c in counts.most_common():
        pct = (c / total * 100) if total else 0.0
        print(f"  {et:30s} : {c:10,} ({pct:6.2f}%)")


# ============================================================
# 7) Main pipeline
# ============================================================
def run_pipeline(
    input_file: str,
    counts_csv: str = "error_counts_clean.csv",
    audit_jsonl: str = "audit_examples.jsonl",
    manual_sample_csv: str = "manual_label_sample.csv",
    audit_max_per_label: int = 50,
    manual_sample_per_label: int = 50,
    progress_every: int = 200000,
    verbose: bool = True,
):
    counts = Counter()

    stats = dict(
        total_rows=0,
        missing_error_field=0,
        null_error_field=0,
        empty_error_field=0,
        json_parse_errors=0,
        rows_with_exceptions=0,
        rows_without_exceptions=0,
        rows_with_multiple_exceptions=0,
    )

    audit_examples: Dict[str, List[Dict[str, Any]]] = {}

    def maybe_add_audit(obj: Dict[str, Any], label: str, evidence_texts: List[str]):
        lst = audit_examples.setdefault(label, [])
        if len(lst) < audit_max_per_label:
            lst.append(make_audit_record(obj, label, evidence_texts))

    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            stats["total_rows"] += 1
            if verbose and stats["total_rows"] % progress_every == 0:
                print(f"Processed {stats['total_rows']:,} rows...")

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                stats["json_parse_errors"] += 1
                continue

            if "error" not in obj:
                stats["missing_error_field"] += 1
                continue

            err = obj.get("error")
            if err is None:
                stats["null_error_field"] += 1
                continue

            error_items = normalize_error_field(err)
            if not error_items:
                stats["empty_error_field"] += 1
                counts["EmptyErrorList"] += 1
                maybe_add_audit(obj, "EmptyErrorList", [])
                continue

            evidence = []
            for it in error_items:
                evidence.extend(_item_to_text_blobs(it))

            excs = extract_exception_types(error_items)
            if excs:
                stats["rows_with_exceptions"] += 1
                uniq = set(excs)
                for e in sorted(uniq):
                    counts[e] += 1
                    maybe_add_audit(obj, e, evidence)
                if len(uniq) > 1:
                    stats["rows_with_multiple_exceptions"] += 1
            else:
                stats["rows_without_exceptions"] += 1
                label = classify_non_exception(error_items)
                counts[label] += 1
                maybe_add_audit(obj, label, evidence)

    # ---------------- sanity checks (SAFE; does not affect counts) ----------------
    accounted = (
        stats["json_parse_errors"]
        + stats["missing_error_field"]
        + stats["null_error_field"]
        + stats["empty_error_field"]
        + stats["rows_with_exceptions"]
        + stats["rows_without_exceptions"]
    )
    assert stats["total_rows"] == accounted, (
        f"Row accounting mismatch: total_rows={stats['total_rows']} vs accounted={accounted}"
    )

    exception_count_events = sum(v for k, v in counts.items() if k in ALLOWED_EXCEPTIONS)
    assert exception_count_events >= stats["rows_with_exceptions"], \
        "Invariant failed: exception-count events < rows_with_exceptions"

    # Outputs
    write_counts_csv(counts, counts_csv)
    write_audit_jsonl(audit_examples, audit_jsonl)
    write_manual_label_sample_csv(audit_examples, manual_sample_csv, per_label=manual_sample_per_label)

    if verbose:
        print_report(counts, stats)
        print("\nArtifacts written:")
        print(f"  Counts CSV           : {counts_csv}")
        print(f"  Audit examples JSONL : {audit_jsonl}  (<= {audit_max_per_label} per label)")
        print(f"  Manual sample CSV    : {manual_sample_csv}  (<= {manual_sample_per_label} per label)")

    return {"counts": counts, "stats": stats, "audit_examples": audit_examples}


# ============================================================
# 8) Run (EDIT PATH ONLY IF NEEDED)
# ============================================================
if __name__ == "__main__":
    INPUT_FILE = "answers.jsonl"  # change only if your file path/name differs
    run_pipeline(
        input_file=INPUT_FILE,
        counts_csv="error_counts_clean.csv",
        audit_jsonl="audit_examples.jsonl",
        manual_sample_csv="manual_label_sample.csv",
        audit_max_per_label=50,
        manual_sample_per_label=50,
        progress_every=200000,
        verbose=True,
    )
