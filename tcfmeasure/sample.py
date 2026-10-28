"""Draws a random sample of TCF sites for the manual check of the crawler (default 30).
The seed is stored, so the same sample can be drawn again.

    python -m tcfmeasure.sample datadir/tcfmeasure/<prefilter run>/tcf_sites.csv
    python -m tcfmeasure.sample <tcf_sites.csv> --n 30 --seed 4711

Output next to the input: sample_<n>_seed<seed>.csv (same columns as tcf_sites.csv) and .json.
"""
import argparse
import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sites", help="tcf_sites.csv from the prefilter")
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--seed", type=int, help="default: a new random seed (stored in the .json)")
    args = parser.parse_args()

    with open(args.sites, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        sites = [row for row in reader if not row.get("duplicate_of")]

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1_000_000)
    sample = random.Random(seed).sample(sites, min(args.n, len(sites)))
    sample.sort(key=lambda row: int(row["rank"]))

    path = Path(args.sites).with_name(f"sample_{len(sample)}_seed{seed}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(sample)
    path.with_suffix(".json").write_text(json.dumps({
        "source": str(args.sites), "population": len(sites), "n": len(sample), "seed": seed,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    print(f"{len(sample)} of {len(sites)} sites (seed {seed}) -> {path}")


if __name__ == "__main__":
    main()
