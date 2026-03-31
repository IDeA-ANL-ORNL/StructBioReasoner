#!/usr/bin/env python3
"""
Search a database for sequence homologs.
"""

import argparse
import os, sys, shutil
from Bio import SeqIO

def convert_fasta_to_mmseqsDB(inpfl: str, outdir: str) -> str:
    """Converts the input FASTA file into the MMseqs2 database format."""
    name = os.path.splitext(os.path.basename(inpfl))[0]
    fileDB = outdir + name + '_DB'
    if not os.path.exists(fileDB):
        os.system('mmseqs createdb ' + inpfl + ' ' + fileDB)

    return fileDB

def save_homologs(homologs: list, outdir: str) -> str:
    """Saves the unique sequence homologs into a FASTA file.

    Args:
        homologs: A list of the sequence homologs
        homologs = [
            {
                "homolog sequence": "amino acid sequence of the homolog",
                "homolog sequence ID": "homolog sequence ID",
                "query sequence ID": "query sequence ID",
                "database": "name of the database",
            }
        ]
        outdir: The output directory where the unique sequence homologs are saved

    Returns:
        A FASTA file that contains the unique sequence homologs
    """
    homologs_dict = {}
    for homolog in homologs:
        aa_seq = homolog["homolog sequence"]
        seqid = homolog["homolog sequence ID"]
        if aa_seq in homologs_dict:
            #append the homolog sequence IDs for duplicate homologs
            homologs_dict[aa_seq].append(seqid)
        else:
            homologs_dict[aa_seq] = [seqid]

    outfl = outdir + homologs[0]["query sequence ID"] + '_homologs.fasta'
    fh_o = open(outfl, "w+")
    for aa_seq in homologs_dict.keys():
        ids = list(set(homologs_dict[aa_seq]))
        id_line = " | ".join(ids)
        fh_o.write(">" + id_line + "\n")
        fh_o.write(aa_seq + "\n")
    fh_o.close()

    return outfl

def search_local_database(
    query: str, 
    db: str, 
    targetDB: str, 
    iterations: int, 
    outdir: str
) -> list:
    """Searches sequence homologs of the query sequence in a local database using MMseqs2 and returns the homologs as a list.
    
    Args:
        query: The path to the query sequence file in FASTA format
        db: The name of a database 
        targetDB: The path to the database in the MMseqs2 database format
        iterations: The number of iterations for a search
        outdir: The output directory where the intermediate files and the final unique sequence homologs are saved

    Returns:
        A list of the sequence homologs

        homologs = [
            {
                "homolog sequence": "amino acid sequence of the homolog",
                "homolog sequence ID": "homolog sequence ID",
                "query sequence ID": "query sequence ID",
                "database": "name of the database",
            }
        ]
    """
    #check if the database exists
    if not os.path.exists(targetDB):
        print(f"Error: Database '{targetDB}' was not found. Download a public reference database before continuing.")
        sys.exit(1)
    
    #create the output directory if not exists
    os.makedirs(outdir, exist_ok=True)

    #convert the query sequence file into the MMseqs2 database format
    queryDB = convert_fasta_to_mmseqsDB(query, outdir)

    #search homologs
    homologs = []
    name = os.path.splitext(os.path.basename(query))[0]
    outDB = outdir + name + '_' + db + '_homologs_DB'
    outDB_seq = outDB + '.seq'
    if not os.path.exists(outDB):
        #search homologs of the query sequence in a database for iterations
        tmp_dir = outdir + 'tmp'
        os.system('mmseqs search ' + queryDB + ' ' + targetDB + ' ' + outDB + ' ' + tmp_dir + ' --num-iterations ' + str(iterations))
        shutil.rmtree(tmp_dir)
    if not os.path.exists(outDB_seq):
       # convert the search output to a sequence format
        os.system('mmseqs convertalis ' + queryDB + ' ' + targetDB + ' ' + outDB + ' ' + outDB_seq + ' --format-mode 4 --format-output "target,tseq"')
    with open(outDB_seq, 'r') as fl:
        next(fl)
        for line in fl:
            line = line.rstrip()
            cols = line.split('\t')
            id_line = cols[0]
            aa_seq = cols[1]
            homolog_info = {
                "homolog sequence": aa_seq,
                "homolog sequence ID": id_line,
                "query sequence ID": name,
                "database": db
            }
            homologs.append(homolog_info)
    
    #save homologs
    outfl = save_homologs(homologs, outdir)
    print (f"Finished searching homologs of {query} in {db}. Saved the homologs in {outfl}")

    return homologs

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Search a database for sequence homologs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example: python search_database.py query.fasta"""
    )
    parser.add_argument('query', help='Path to the query sequence FASTA file')
    parser.add_argument('--db', default='UniProtKB', help='Name of a database (default: UniProtKB)')
    parser.add_argument('--targetDB', default='databases/UniProtKB', help='Path to the database in MMseqs2 database format (default: databases/UniProtKB)')
    parser.add_argument('--iterations', default=1, type=int, help='Number of iterations for a search (default: 1)')
    parser.add_argument('--outdir', default='homologs/', help='Output directory (default: homologs/)')
    args = parser.parse_args()
    
    search_local_database(args.query, args.db, args.targetDB, args.iterations, args.outdir)