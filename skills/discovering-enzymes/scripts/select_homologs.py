#!/usr/bin/env python3
"""
Align, filter and select sequence homologs.
"""

import argparse
import os, sys
from Bio import SeqIO

def convert_fasta_to_mmseqsDB(inpfl: str, outdir: str) -> str:
    """Converts the input FASTA file into the MMseqs2 database format."""
    name = os.path.splitext(os.path.basename(inpfl))[0]
    fileDB = outdir + name + '_DB'
    if not os.path.exists(fileDB):
        os.system('mmseqs createdb ' + inpfl + ' ' + fileDB)

    return fileDB

def align_homologs_to_query(homologs: str, query: str, outdir: str) -> str:
    """Aligns every sequence homolog in the input FASTA file to the query sequence and returns the alignment file as a string.

    Args:
        homologs: The path to the sequence homolog file in FASTA format
        query: The path to the query sequence file
        outdir: The output directory

    Returns:
        resultDB_a3m: A a3m file that contains the actual alignments of the homologs
    """
    #convert the sequence homolog file and query sequence file into the MMseqs2 database format
    homologsDB = convert_fasta_to_mmseqsDB(homologs, outdir)
    queryDB = convert_fasta_to_mmseqsDB(query, outdir)

    #generate an alignment
    resultDB_pref = homologsDB + '_pref'
    resultDB_aln = homologsDB + '_aln'
    resultDB_a3m = homologsDB + '.a3m'
    if not os.path.exists(resultDB_pref):
        #identify potential sequence similarities between the query and sequence homologs at high sensitivity (-s 7.5)
        os.system('mmseqs prefilter ' + queryDB + ' ' + homologsDB + ' ' + resultDB_pref + ' -s 7.5 --max-seqs 10000')
    if not os.path.exists(resultDB_aln):
        #compute a sequence alignment for every query-homolog pair 
        os.system('mmseqs align ' + queryDB + ' ' + homologsDB + ' ' + resultDB_pref + ' ' + resultDB_aln)
    if not os.path.exists(resultDB_a3m):
        #generate a multiple sequence alignment for the sequence homologs
        os.system('mmseqs result2msa '+ queryDB + ' ' + homologsDB + ' ' + resultDB_aln + ' ' + resultDB_a3m + ' --msa-format-mode 6 --skip-query false')
    os.system('sed -i "" -e "$ d" ' + resultDB_a3m) #remove null byte
    print (f"Finished sequence alignments. A completed sequence alignment of the homologs is in {resultDB_a3m}")

    return resultDB_a3m

def filter_homologs(
    hhfilter: str, 
    homologs_a3m: str, 
    seq_cov: int, 
    outdir: str
) -> str:
    """Filters sequence homologs using increasing pairwise sequence identity at a defined minimum sequence coverage by HHfilter and returns the resulting filtered sequence homologs alignment file in a3m format.

    Args:
        hhfilter: The path to the HHfilter executable
        homologs_a3m: The path to the sequence homolog alignment file in a3m format
        seq_cov: Minimum coverage with the first sequence (query) in homologs_a3m
        outdir: The output directory

    Returns:
        A a3m file that contains the alignments of the homologs after filtering in the order of increasing pairwise sequence identity
    """
    #check if hhfilter is installed
    if not os.path.exists(hhfilter):
        print(f"Error: HHfilter executable '{hhfilter}' was not found. Install HHfilter before continuing.")
        sys.exit(1)
        
    name = os.path.splitext(os.path.basename(homologs_a3m))[0]
    homologs_a3m_filtered = outdir + name + '_filtered.a3m'

    if not os.path.exists(homologs_a3m_filtered) or os.path.getsize(homologs_a3m_filtered) == 0:
        fh_o = open(homologs_a3m_filtered, "w+")

        #filter the homologs from 0% identity to 100% identity at an increments of 5%
        seqs_list = []
        for iden in range(0, 100, 5):
            #run HHfilter
            tmp = outdir + 'tmp.a3m'
            os.system(hhfilter + ' -id ' + str(iden) + ' -cov ' + str(seq_cov) + ' -i ' + homologs_a3m + ' -o ' + tmp)

            #filter out existing/duplicate sequences
            fasta_sequences = SeqIO.parse(open(tmp), 'fasta')
            for i, fasta in enumerate(fasta_sequences):
                id_line, sequence = fasta.description, str(fasta.seq)
                if not sequence in seqs_list:
                    fh_o.write(">" + id_line + "\t" + str(iden) + "\n" + sequence + "\n")
                    seqs_list.append(sequence)
            os.remove(tmp)
        fh_o.close()
    print (f"Finished filtering homologs. Filtered homologs are in {homologs_a3m_filtered}")

    return homologs_a3m_filtered

def select_homologs(
    homologs_a3m_filtered: str, 
    homologs: str, 
    n: int, 
    outdir: str
) -> str:
    """Selects n number of sequence homologs from post HHfilter sequence homologs a3m file and returns their complete sequences.

    Args:
        homologs_a3m_filtered: The path to an a3m file that contains the alignments of the homologs after HHfilter in the order of increasing pairwise sequence identity
        homologs: The path to the sequence homolog file in FASTA format
        n: Number of sequence homologs to be selected
        outdir: The output directory

    Returns:
        A FASTA file that contains n number of selected sequence homologs
    """

    name = os.path.splitext(os.path.basename(homologs_a3m_filtered))[0]
    homologs_selected = outdir + name + '_selected.fasta'

    #save the sequence homolog pool into a dictionary
    pool_dict = {} #key = seqid; value = full length sequence
    fasta_sequences = SeqIO.parse(open(homologs), 'fasta')
    for i, fasta in enumerate(fasta_sequences):
        id_line, aa_seq = fasta.description, str(fasta.seq)
        seqids = id_line.split(" | ")
        for seqid in seqids:
            pool_dict[seqid] = aa_seq

    #select n top sequences from the filtered sequence homologs
    fh_o = open(homologs_selected, "w+")
    count = -1 # since the first sequence in homologs_a3m_filtered is the query sequence
    fasta_sequences = SeqIO.parse(open(homologs_a3m_filtered), 'fasta')
    for i, fasta in enumerate(fasta_sequences):
        if count < n:
            id_line, sequence = fasta.description, str(fasta.seq)
            seqid = id_line.split()[0]
            if seqid in pool_dict:
                #get full length sequence from the sequence homolog pool
                fh_o.write(">" + seqid + "\n")
                fh_o.write(pool_dict[seqid] + "\n")
                count += 1
            else:
                print(f"{seqid} is not in {homologs_seq}.")
    fh_o.close()
    print (f"Selected {n} sequence homologs in {homologs_selected}")

    return homologs_selected

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Align, filter and select sequence homologs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example: python select_homologs.py query.fasta homologs/query_homologs.fasta"""
    )
    parser.add_argument('query', help='Path to the query sequence FASTA file')
    parser.add_argument('homologs', help='Path to the sequence homologs FASTA file')
    parser.add_argument('--hhfilter', default='software/hhfilter', help='Path to the HHfilter executable (default: software/hhfilter)')
    parser.add_argument('--cov', default=50, type=int, help='Minimum coverage with the query sequence (default: 50)')
    parser.add_argument('--n', default=48, type=int, help='Number of sequence homologs to be selected (default: 48)')
    parser.add_argument('--outdir', default='homologs/', help='Output directory (default: homologs/)')
    
    args = parser.parse_args()
    
    a3m = align_homologs_to_query(args.homologs, args.query, args.outdir)
    sort = filter_homologs(args.hhfilter, a3m, args.cov, args.outdir)
    select_homologs(sort, args.homologs, args.n, args.outdir)