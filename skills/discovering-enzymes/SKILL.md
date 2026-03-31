---
name: discovering-enzymes
description: Search and select enzyme sequence homologs from a database. Use when users provide a query sequence and want to discover sequence homologs of the query sequence in a database.
---

# Discover enzyme homologs

Enzyme discovery toolkit to search, align, filter, and select enzyme sequence homologs in a database.

## Input Format

- The input file (`query.fasta`) should have at least one query sequence in FASTA format.
- The database (`targetDB`) should be in the MMseqs2 database format. A database can be downloaded by running `mmseqs databases <name> <o:sequenceDB> <tmpDir>`. For example: `mmseqs databases UniProtKB databases/UniProtKB tmp


## Workflow

**Step 1: Search database**

Searches a local database for sequence homologs of the query in the input file and saves the homologs in FASTA format.
Requires MMSeqs2 (mmseqs).

```bash
python skills/discovering-enzymes/scripts/search_database.py query.fasta \
--db UniProtKB \
--targetDB databases/UniProtKB \
--iterations 1 \
--outdir homologs/ \
```

**Step 2: Select homologs**

Generates sequence alignments, filters the alignment and selects a number of sequence homologs. Saves the selected homologs in FASTA format.
Requires MMSeqs2 (mmseqs) and HHfilter (hhfilter)

```bash
python skills/discovering-enzymes/scripts/select_homologs.py query.fasta homologs.fasta \
--hhfilter software/hhfilter \
--cov 50 \
--n 48 \
--outdir homologs/ \
```

## Parameters

### Search database
- `db`: Name of a database - UniProtKB, NR, or swissprot (default: UniProtKB)
- `targetDB`: Path to the database in the MMseqs2 database format (default: databases/UniProtKB)
- `iterations`: Number of iterations for a search (default: 1)
- `outdir`: Output directory (default: homologs/)

### Select homologs
- `hhfilter`: Path to the HHfilter executable (default: software/hhfilter)
- `cov`: 'Minimum coverage with the query sequence (default: 50)
- `n`: 'Number of sequence homologs to be selected (default: 48)
- `outdir`: Output directory (default: homologs/)

## Output Files

```
homologs/
├── homologs.fasta                       # All homologs from a search
└── homologs_DB_filtered_selected.fasta  # N selected homologs after filtering
```


## Dependencies

`biopython`


## Requirements

- **MMseqs2** (`mmseqs`): Many-against-Many sequence searching and alignment
- **HHfilter** (`hhfilter`): Filter an alignment by maximum sequence identity and minimum coverage