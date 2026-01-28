from abc import ABC, abstractmethod
from chai_lab.chai1 import run_inference
import gemmi
import numpy as np
from pathlib import Path
from string import Template
import tempfile
from typing import Any, Optional

class Folding(ABC):
    def __init__(self):
        pass
    
    @abstractmethod
    def prepare(self):
        pass
    
    @abstractmethod
    def __call__(self):
        pass
    
    @abstractmethod
    def postprocess(self):
        pass

class Chai(Folding):
    def __init__(self,
                 fasta_dir: Path,
                 out: Path,
                 diffusion_steps: int=100,
                 device: str='xpu:0'):
        self.fasta_dir = Path(fasta_dir)
        self.out = Path(out)
        self.diffusion_steps = diffusion_steps
        self.device = device

        self.devshm = Path('/dev/shm')

        self.fasta_dir.mkdir(exist_ok=True, parents=True)
        self.out.mkdir(exist_ok=True, parents=True)

    def prepare(self,
                seqs: list[str],
                out: Path) -> Path:
        chains = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        fasta_str = ''
        for i, seq in enumerate(seqs):
            fasta_str += f'>protein|{chains[i]}\n'
            fasta_str += f'{seq}\n'

        fasta = out / 'sequence.fa'
        fasta.write_text(fasta_str)

        return fasta

    def write_constraint_file(self,
                              out: Path,
                              constraints: Optional[dict]=None,) -> Path:
        header = 'chainA,res_idxA,chainB,res_idxB,connection_type,confidence,'
        header += 'min_distance_angstrom,max_distance_angstrom,comment,restraint_id'
        template = Template('$chainA,$resA,$chainB,$resB,$const_type,0.0,0.0,$distance,comment,$i')

        if constraints is None:
            return constraints

        constraints_text = [header]
        for i, constraint_params in constraints.items():
            constraint_params['i'] = i
            constraints_text.append(template.substitute(**constraint_params))

        constraint_file = out / 'constraints.txt'
        constraint_file.write_text('\n'.join(constraints_text))

        return constraint_file

    def __call__(self,
                 seqs: list[str],
                 name: str,
                 constraints: Optional[list[dict]]=None) -> dict[str, Any]:
        out = self.devshm / name
        out.mkdir(exist_ok=True, parents=True)
        fasta = self.prepare(seqs, out)

        if constraints is not None:
            constraints = self.write_constraint_file(out, constraints)

        with tempfile.TemporaryDirectory(dir=str(out)) as tmpdir:
            tmp = Path(tmpdir)
            
            run_inference(
                fasta_file=fasta,
                output_dir=tmp,
                device=self.device,
                use_esm_embeddings=True,
                num_diffn_timesteps=self.diffusion_steps,
                constraint_path=constraints,
            )

            structure_out = self.out / name
            structure_out.mkdir(exist_ok=True, parents=True)
            print(structure_out)
            results = self.postprocess(tmp, structure_out)

        return results

    def postprocess(self,
                    inputs: Path,
                    outputs: Path) -> dict[int, Any]:
        """Extract Chai model and score outputs and return in a single dictionary.
        Score components include: aggregate_score, ptm, iptm, per_chain_ptm, 
        per_chain_pair_iptm, has_inter_chain_clashes, chain_chain_clashes."""
        results = {}
        for i in range(5):
            model = inputs / f'pred.model_idx_{i}.cif'
            npz_file = inputs / f'scores.model_idx_{i}.npz'

            score_dict = np.load(str(npz_file))
            score = {key: score_dict[key] for key in score_dict.files}
            final_path = outputs / f'protein{i}.pdb'

            structure = gemmi.read_structure(str(model))
            structure.write_pdb(str(final_path))

            results[i] = {'model': final_path, 'scores': score}

        return results

class ChaiBinder(Chai):
    def __init__(self,
                 fasta_dir: Path,
                 out: Path,
                 diffusion_steps: int=100,
                 device: str='xpu:0'):
        super().__init__(fasta_dir=fasta_dir, 
                         out=out, 
                         diffusion_steps=diffusion_steps,
                         device=device)
        self.template_fasta = Template('>protein|target\n$target\n>protein|binder\n$binder')

    def prepare(self,
                seqs: list[str],
                exp: str,
                label: str) -> Path:
        fasta_str = self.template_fasta.substitute(target=seqs[0], binder=seqs[1])
        fasta_path = self.fasta_dir / exp / f'{label}.fa'
        fasta_path.write_text(fasta_str)

        return fasta_path
    
    def write_constraint_file(self,
                              out: Path,
                              constraints: Optional[dict]=None,) -> Path:
        header = 'chainA,res_idxA,chainB,res_idxB,connection_type,confidence,'
        header += 'min_distance_angstrom,max_distance_angstrom,comment,restraint_id'
        template = Template('$chainA,$resA,$chainB,$resB,$const_type,0.0,0.0,$distance,comment,$i')

        if constraints is None:
            return constraints

        constraints_text = [header]
        for i, constraint_params in constraints.items():
            constraint_params['i'] = i
            constraints_text.append(template.substitute(**constraint_params))

        constraint_file = out / 'constraints.txt'
        constraint_file.write_text('\n'.join(constraints_text))

        return constraint_file

    def __call__(self, 
                 seqs: list[str],
                 exp_label: str,
                 out_label: str,
                 constraints: Optional[dict]=None) -> Path:
        (self.fasta_dir / exp_label).mkdir(exist_ok=True)
        fasta = self.prepare(seqs, exp_label, out_label)
        out = self.devshm / exp_label
        out.mkdir(exist_ok=True, parents=True)
        
        if constraints is not None:
            constraints = self.write_constraint_file(out, constraints)

        with tempfile.TemporaryDirectory(dir=str(out)) as tmpdir:
            tmp = Path(tmpdir)
            run_inference(
                fasta_file=fasta,
                output_dir=tmp,
                device=self.device,
                use_esm_embeddings=True,
                num_diffn_timesteps=self.diffusion_steps,
                constraint_path=constraints,
            )

            (self.out / exp_label).mkdir(exist_ok=True)
            pdb = self.postprocess(tmp, f'{exp_label}/{out_label}')

        return pdb

    def postprocess(self,
                    in_path: Path,
                    out_name: str) -> Path:
        # NOTE: model 0 is not always best
        best_model = in_path / 'pred.model_idx_0.cif'
        final_path = self.out / f'{out_name}.pdb'

        structure = gemmi.read_structure(str(best_model))
        structure.write_pdb(str(final_path))

        return final_path

class Boltz(Folding):
    def __init__(self):
        pass

    def prepare(self):
        pass

    def __call__(self):
        pass
    
    def postprocess(self):
        pass
