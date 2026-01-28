from abc import ABC, abstractmethod
from pathlib import Path
import subprocess
import sys

class InverseFolding(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def prepare(self):
        pass

    @abstractmethod
    def __call__(self):
        pass

    @abstractmethod
    def postprocessing(self):
        pass

class ProteinMPNN(InverseFolding):
    def __init__(self,
                 proteinmpnn_path: Path,
                 num_seq: int = 1,
                 max_retries: int=5,
                 sampling_temp: str = '0.1',
                 batch_size: int = 250,
                 model_name: str = 'v_48_020',
                 model_weights: str = 'soluble_model_weights',
                 device: str = 'xpu:0'):
        self.proteinmpnn_path = Path(proteinmpnn_path)
        self.run_py = self.proteinmpnn_path / 'protein_mpnn_run.py'
        self.helpers = [
            self.proteinmpnn_path / 'helper_scripts' / 'parse_multiple_chains.py',
            self.proteinmpnn_path / 'helper_scripts' / 'assign_fixed_chains.py',
            self.proteinmpnn_path / 'helper_scripts' / 'make_fixed_positions_dict.py'
        ]
        self.num_seq = num_seq
        self.max_retries = max_retries
        self.sampling_temp = sampling_temp
        self.batch_size = batch_size
        self.model_name = model_name
        self.model_weights = self.proteinmpnn_path / model_weights
        self.device = device
        self.file_intermediates = ['parsed_design.jsonl', 
                                   'chain_B_design.jsonl', 
                                   'fixed_design.jsonl']

    def prepare(self,
                pdb_path: Path,
                parsed: Path,
                assigned: Path,
                fixed: Path,
                fixed_indices: list[int]) -> None:
        args = [
            [
                '--input_path', str(pdb_path), 
                '--output_path', str(parsed),
            ],
            [
                '--input_path', str(parsed),
                '--output_path', str(assigned),
                '--chain_list', 'B'
            ],
            [
                '--input_path', str(parsed),
                '--output_path', str(fixed),
                '--chain_list', 'B',
                '--position_list', ' '.join([str(x) for x in fixed_indices]),
            ]
        ]

        for helper, arg in zip(self.helpers, args):
            subprocess.run([sys.executable, str(helper), *arg], check=True)

    def __call__(self,
                 input_path: Path,
                 pdb_path: Path,
                 output_path: Path,
                 remodel_positions: list[int]):
        jsonls = [input_path / fi for fi in self.file_intermediates]
        self.prepare(pdb_path, *jsonls, remodel_positions)
        self.run(jsonls, output_path)

        return self.postprocessing(output_path)

    def run(self,
            jsonls: list[Path],
            output: Path) -> None:
        cmd = [
            sys.executable, str(self.run_py),
            '--jsonl_path', str(jsonls[0]),
            '--chain_id_jsonl', str(jsonls[1]),
            '--fixed_positions_jsonl', str(jsonls[2]),
            '--out_folder', str(output),
            '--num_seq_per_target', str(self.batch_size),
            '--sampling_temp', self.sampling_temp,
            '--batch_size', str(self.batch_size),
            '--model_name', self.model_name,
            '--path_to_model_weights', str(self.model_weights),
            '--device', self.device,
        ]

        subprocess.run(cmd, check=True)

    def postprocessing(self,
                       output_dir: Path) -> list[str]:
        seqs_dir = output_dir / 'seqs'
        if not seqs_dir.exists():
            return []
            
        fas = seqs_dir.glob('*.fa')
        seqs = []
        for fa in fas:
            seqs.extend(self.process_single_file(fa))
        
        return seqs

    def process_single_file(self,
                            path: Path) -> list[str]:
        with open(path) as f:
            raw_data = f.readlines()
        
        seqs = [line.strip() for line in raw_data[3::2]]
            
        return list(set(seqs))


class ESMIF1(InverseFolding):
    def __init__(self):
        pass
    
    def prepare(self):
        pass
    
    def __call__(self):
        pass
    
    def postprocessing(self):
        pass
