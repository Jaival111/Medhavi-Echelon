import sys
import pandas as pd
from pattern_compiler import PatternCompiler


def main():
    INPUT_CSV = "train.csv"
    OUTPUT_CSV = "scored.csv"

    # Change this if your text column is named differently
    TEXT_COL = "text"

    # For huge CSVs: reduce if memory is tight, increase if you have RAM
    CHUNKSIZE = 100_000

    # If you get UnicodeDecodeError, change to "latin-1"
    ENCODING = "utf-8"

    scorer = PatternCompiler()
    first_write = True

    try:
        for chunk in pd.read_csv(INPUT_CSV, chunksize=CHUNKSIZE, encoding=ENCODING):
            if TEXT_COL not in chunk.columns:
                raise ValueError(
                    f"Column '{TEXT_COL}' not found. Available columns: {list(chunk.columns)}"
                )

            series = chunk[TEXT_COL].fillna("").astype(str)
            chunk["risk_score"] = series.map(scorer.risk_score)

            chunk.to_csv(
                OUTPUT_CSV,
                mode="w" if first_write else "a",
                index=False,
                header=first_write,
            )
            first_write = False

    except UnicodeDecodeError:
        print("Encoding error reading train.csv. Try setting ENCODING = 'latin-1'.", file=sys.stderr)
        sys.exit(1)

    print(f"Done. Output written to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
