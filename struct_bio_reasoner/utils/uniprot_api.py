import requests
from pathlib import Path

async def fetch_uniprot_sequence(uniprot_id: str) -> Optional[Dict[str, str]]:
    """
    Fetch protein sequence from UniProt API.
    
    Args:
        uniprot_id: UniProt accession ID
        
    Returns:
        Dictionary with protein name and sequence
    """
    try:
        url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.fasta"
        response = requests.get(url)
        
        if response.status_code == 200:
            lines = response.text.strip().split('\n')
            header = lines[0]
            sequence = ''.join(lines[1:])
            
            # Extract protein name from header
            # Format: >sp|P12345|PROT_HUMAN Protein name OS=...
            parts = header.split('|')
            if len(parts) >= 3:
                name_part = parts[2].split(' OS=')[0]
            else:
                name_part = uniprot_id
            
            
            return {
                'uniprot_id': uniprot_id,
                'name': name_part,
                'sequence': sequence
            }
        else:
            return None
            
    except Exception as e:
        return None