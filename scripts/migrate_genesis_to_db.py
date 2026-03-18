#!/usr/bin/env python3
"""
Migrate genesis JSON files to SQLite genesis_seed table.

Reads .data/genome/genesis_*.json → cleans action markers → writes to openher.db.
Run once after upgrading to DB-based genesis storage.

Usage:
    PYTHONPATH=. python3 scripts/migrate_genesis_to_db.py [--data-dir .data]
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.genome.style_memory import ContinuousStyleMemory


def main():
    parser = argparse.ArgumentParser(description="Migrate genesis JSON → SQLite")
    parser.add_argument("--data-dir", default=".data", help="Data directory (default: .data)")
    args = parser.parse_args()

    genome_dir = os.path.join(args.data_dir, "genome")
    db_path = os.path.join(args.data_dir, "openher.db")

    if not os.path.isdir(genome_dir):
        print(f"❌ Genome directory not found: {genome_dir}")
        sys.exit(1)

    json_files = sorted(glob.glob(os.path.join(genome_dir, "genesis_*.json")))
    if not json_files:
        print(f"❌ No genesis_*.json files found in {genome_dir}")
        sys.exit(1)

    print(f"📂 Source: {genome_dir}")
    print(f"💾 Target: {db_path}")
    print(f"📄 Found {len(json_files)} genesis files\n")

    total_seeds = 0
    for json_file in json_files:
        basename = os.path.basename(json_file)
        # genesis_kelly.json → kelly
        persona_id = basename.replace("genesis_", "").replace(".json", "")

        with open(json_file, "r", encoding="utf-8") as f:
            seeds = json.load(f)

        count = len(seeds)
        total_seeds += count

        # save_genesis_to_db handles action marker cleaning
        ContinuousStyleMemory.save_genesis_to_db(persona_id, seeds, db_path)
        print(f"  ✅ {persona_id:<12} {count:>3} seeds migrated")

    print(f"\n🎉 Migration complete: {len(json_files)} personas, {total_seeds} total seeds")
    print(f"   DB: {db_path}")
    print(f"\n💡 You can now delete the JSON files:")
    print(f"   rm {genome_dir}/genesis_*.json")


if __name__ == "__main__":
    main()
