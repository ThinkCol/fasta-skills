#!/usr/bin/env python3
"""merge-summaries.py — Recursive hierarchical merge for mini-summaries.

Reads mini-summary text files from a work directory, groups them into
chunks of N, and writes grouped files for the next merge level.

Usage:
  python3 merge-summaries.py <work-dir> <group-size> <level>

Reads:  <work-dir>/level<L-1>_summary_*.txt
Writes: <work-dir>/level<L>_group_*.txt  (concatenated groups for agent to summarise)

Prints the number of groups written to stdout.
If only 1 input file exists, copies it as the final summary and prints "FINAL".
"""
import sys
import os
import glob
import shutil

def main():
    work_dir = sys.argv[1]
    group_size = int(sys.argv[2])
    level = int(sys.argv[3])

    prev_level = level - 1
    pattern = os.path.join(work_dir, f"level{prev_level}_summary_*.txt")
    files = sorted(glob.glob(pattern))

    if not files:
        print("0")
        return

    # If only one summary remains, it's the final output
    if len(files) == 1:
        shutil.copy2(files[0], os.path.join(work_dir, "final_summary.txt"))
        print("FINAL")
        return

    # Group files into chunks of group_size
    groups = [files[i:i + group_size] for i in range(0, len(files), group_size)]

    for idx, group in enumerate(groups):
        out_path = os.path.join(work_dir, f"level{level}_group_{idx}.txt")
        with open(out_path, "w", encoding="utf-8") as out:
            for f in group:
                out.write(f"--- Source: {os.path.basename(f)} ---\n")
                with open(f, "r", encoding="utf-8") as inp:
                    out.write(inp.read())
                out.write("\n\n")

    print(len(groups))

if __name__ == "__main__":
    main()
