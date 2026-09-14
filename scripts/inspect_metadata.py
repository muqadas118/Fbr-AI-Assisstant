import json
from pathlib import Path

# ============================================================
# PROJECT PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

METADATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "profile"
    / "vectorstore"
    / "metadata.json"
)


# ============================================================
# LOAD METADATA
# ============================================================

print("=" * 70)
print("FBR METADATA INSPECTION")
print("=" * 70)

print()
print("Metadata path:")
print(METADATA_PATH)

if not METADATA_PATH.exists():
    raise FileNotFoundError(
        f"metadata.json not found:\n{METADATA_PATH}"
    )

with open(METADATA_PATH, "r", encoding="utf-8") as f:
    metadata = json.load(f)


# ============================================================
# BASIC INFORMATION
# ============================================================

print()
print("=" * 70)
print("BASIC INFORMATION")
print("=" * 70)

print(f"Metadata type : {type(metadata).__name__}")
print(f"Total records: {len(metadata)}")


if not metadata:
    raise RuntimeError("metadata.json is empty.")


# ============================================================
# FIRST RECORD
# ============================================================

print()
print("=" * 70)
print("FIRST RECORD STRUCTURE")
print("=" * 70)

first = metadata[0]

print(f"Record type: {type(first).__name__}")

if isinstance(first, dict):

    print()
    print("Available fields:")

    for key in first.keys():
        value = first[key]

        print(
            f"- {key}: "
            f"type={type(value).__name__}, "
            f"value={repr(value)[:200]}"
        )

else:
    print("First record is not a dictionary.")


# ============================================================
# FIND SECTION 177
# ============================================================

print()
print("=" * 70)
print("SECTION 177 RECORDS")
print("=" * 70)

matches = []

for idx, item in enumerate(metadata):

    if not isinstance(item, dict):
        continue

    text = str(item.get("text", ""))

    if "177. Audit" in text or "177. Audit.—" in text:
        matches.append((idx, item))


print(f"Section 177 heading matches: {len(matches)}")


# ============================================================
# DISPLAY SECTION 177 MATCHES
# ============================================================

for position, (idx, item) in enumerate(matches, start=1):

    print()
    print("-" * 70)
    print(f"MATCH {position}")
    print("-" * 70)

    print(f"Metadata index : {idx}")

    print(
        f"Chunk ID      : "
        f"{item.get('chunk_id', item.get('id', 'N/A'))}"
    )

    print(
        f"Source        : "
        f"{item.get('source', 'N/A')}"
    )

    # Show every useful metadata field except full text
    for key, value in item.items():

        if key == "text":
            continue

        print(
            f"{key:<15}: "
            f"{repr(value)[:500]}"
        )

    text = str(item.get("text", ""))

    print()
    print("Text preview:")
    print(text[:1000])


# ============================================================
# NEIGHBOURING RECORDS
# ============================================================

if matches:

    print()
    print("=" * 70)
    print("NEIGHBOURING RECORDS")
    print("=" * 70)

    # Inspect the first Section 177 match.
    center_idx = matches[0][0]

    start = max(0, center_idx - 3)
    end = min(len(metadata), center_idx + 4)

    print(
        f"Inspecting metadata indexes "
        f"{start} through {end - 1}"
    )

    for idx in range(start, end):

        item = metadata[idx]

        if not isinstance(item, dict):
            continue

        print()
        print("-" * 70)
        print(f"INDEX {idx}")
        print("-" * 70)

        print(
            f"Source   : "
            f"{item.get('source', 'N/A')}"
        )

        print(
            f"Chunk ID : "
            f"{item.get('chunk_id', item.get('id', 'N/A'))}"
        )

        # Print possible ordering fields
        possible_fields = [
            "index",
            "chunk_index",
            "chunk_number",
            "page",
            "page_number",
            "section",
            "position",
            "start",
            "end",
            "id",
        ]

        for field in possible_fields:

            if field in item:
                print(
                    f"{field:<12}: "
                    f"{item[field]!r}"
                )

        text = str(item.get("text", ""))

        print()
        print("Text preview:")
        print(text[:500])


# ============================================================
# FINISHED
# ============================================================

print()
print("=" * 70)
print("METADATA INSPECTION COMPLETE")
print("=" * 70)

