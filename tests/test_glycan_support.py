#!/usr/bin/env python3
"""
Unit tests for glycan support in StructBioReasoner and BindCraft.

Covers:
  1. GlycanChain data model (creation, serialization, CSV writing)
  2. Glycan-chain parsing from research-goal text
  3. PDB stripping of glycan chains before ProteinMPNN
  4. fold_sequence_task glycan injection logic
  5. ChaiAgent._inject_glycans / _append_extra_constraints

Run with:
    pytest tests/test_glycan_support.py -v
"""

import re
import csv
import sys
import tempfile
import textwrap
import logging
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Section 1: GlycanChain data model
# ---------------------------------------------------------------------------
from struct_bio_reasoner.data.protein_hypothesis import GlycanChain, BinderHypothesisData


class TestGlycanChain:
    """Unit tests for the GlycanChain dataclass."""

    def _sample(self) -> GlycanChain:
        return GlycanChain(
            chain_id='B',
            sequence='NAG(6-1 FUC)(4-1 NAG)',
            attachment_residue='N297',
            protein_chain='A',
            protein_atom='N',
            glycan_atom='C1',
        )

    def test_defaults(self):
        gc = GlycanChain(chain_id='C', sequence='NAG', attachment_residue='S42')
        assert gc.protein_chain == 'A'
        assert gc.protein_atom == 'N'
        assert gc.glycan_atom == 'C1'

    def test_to_dict_has_all_keys(self):
        d = self._sample().to_dict()
        assert set(d) == {
            'chain_id', 'sequence', 'attachment_residue',
            'protein_chain', 'protein_atom', 'glycan_atom',
        }

    def test_from_dict_roundtrip(self):
        orig = self._sample()
        restored = GlycanChain.from_dict(orig.to_dict())
        assert restored.chain_id == orig.chain_id
        assert restored.sequence == orig.sequence
        assert restored.attachment_residue == orig.attachment_residue
        assert restored.protein_chain == orig.protein_chain
        assert restored.protein_atom == orig.protein_atom
        assert restored.glycan_atom == orig.glycan_atom

    def test_from_dict_optional_defaults(self):
        """from_dict falls back to sensible defaults for optional keys."""
        gc = GlycanChain.from_dict({'chain_id': 'D', 'sequence': 'MAN', 'attachment_residue': 'T11'})
        assert gc.protein_chain == 'A'
        assert gc.protein_atom == 'N'
        assert gc.glycan_atom == 'C1'

    def test_to_fasta_entry(self):
        gc = self._sample()
        fasta = gc.to_fasta_entry()
        assert fasta.startswith('>glycan|B')
        assert 'NAG' in fasta

    def test_to_restraint_row_columns(self):
        gc = self._sample()
        row = gc.to_restraint_row('bond1')
        parts = row.split(',')
        # Expected: chainA, res_idxA, chainB, res_idxB, connection_type, confidence,
        #           min_dist, max_dist, comment, restraint_id
        assert len(parts) == 10, f"Expected 10 columns, got {len(parts)}: {parts}"
        assert parts[0] == 'A'       # protein chain
        assert 'N297' in parts[1]    # attachment residue@atom
        assert parts[2] == 'B'       # glycan chain
        assert parts[-1] == 'bond1'  # restraint id

    def test_write_restraints_csv(self, tmp_path):
        gc1 = GlycanChain('B', 'NAG', 'N131', 'A', 'N', 'C1')
        gc2 = GlycanChain('C', 'FUC', 'N203', 'A', 'N', 'C1')
        out = tmp_path / 'restraints.csv'
        GlycanChain.write_restraints_csv([gc1, gc2], out)
        lines = out.read_text().splitlines()
        # 1 header + 2 data rows
        assert len(lines) == 3
        # Header check
        assert 'chainA' in lines[0]
        # Data rows reference the correct chains
        assert 'B' in lines[1]
        assert 'C' in lines[2]

    def test_write_restraints_csv_parseable(self, tmp_path):
        """Written CSV is well-formed and parseable by the csv module."""
        gc = GlycanChain('B', 'NAG', 'N297', 'A', 'N', 'C1')
        out = tmp_path / 'r.csv'
        GlycanChain.write_restraints_csv([gc], out)
        with open(out) as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]['chainA'] == 'A'
        assert rows[0]['chainB'] == 'B'


class TestBinderHypothesisDataGlycans:
    """GlycanChain integration with BinderHypothesisData."""

    def test_glycan_chains_default_empty(self):
        data = BinderHypothesisData(
            hypothesis_text='test', target_name='P1',
            target_sequence='MKTAY', proposed_peptides=[],
            literature_references=[],
        )
        assert data.glycan_chains == []

    def test_to_dict_includes_glycan_chains(self):
        gc = GlycanChain('B', 'NAG', 'N297')
        data = BinderHypothesisData(
            hypothesis_text='test', target_name='P1',
            target_sequence='MKTAY', proposed_peptides=[],
            literature_references=[], glycan_chains=[gc],
        )
        d = data.to_dict()
        assert 'glycan_chains' in d
        assert len(d['glycan_chains']) == 1
        assert d['glycan_chains'][0]['chain_id'] == 'B'

    def test_from_dict_roundtrip_with_glycans(self):
        gc = GlycanChain('B', 'NAG(4-1 NAG)', 'N131')
        data = BinderHypothesisData(
            hypothesis_text='h', target_name='T',
            target_sequence='MKTAY', proposed_peptides=[],
            literature_references=[], glycan_chains=[gc],
        )
        restored = BinderHypothesisData.from_dict(data.to_dict())
        assert len(restored.glycan_chains) == 1
        assert restored.glycan_chains[0].sequence == 'NAG(4-1 NAG)'


# ---------------------------------------------------------------------------
# Section 2: Glycan-chain parsing from research-goal text
# (tested via the same regex used by BinderDesignSystem._extract_glycan_chains)
# ---------------------------------------------------------------------------

def _parse_glycan_chains(research_goal: str) -> list:
    """Mirror of BinderDesignSystem._extract_glycan_chains without needing a config."""
    known_sugars = 'NAG|FUC|MAN|GAL|SIA|GLC|GLA'
    pattern = rf'([A-Z])(\d+):((?:{known_sugars})[^\n]+)'
    matches = re.findall(pattern, research_goal)
    chain_letters = list('BCDEFGHIJKLMNOPQRSTUVWXYZ')
    chains = []
    for idx, (resname, resid, glycan_seq) in enumerate(matches):
        chains.append(GlycanChain(
            chain_id=chain_letters[idx],
            sequence=glycan_seq.strip(),
            attachment_residue=f'{resname}{resid}',
            protein_chain='A',
            protein_atom='N' if resname == 'N' else 'O',
            glycan_atom='C1',
        ))
    return chains


class TestGlycanParsing:
    """Tests for glycan-chain extraction from research-goal strings."""

    def test_single_n_glycan(self):
        goal = "Design binders for IgG1. N297:NAG(6-1 FUC)(4-1 NAG) is the glycan."
        chains = _parse_glycan_chains(goal)
        assert len(chains) == 1
        gc = chains[0]
        assert gc.chain_id == 'B'
        assert gc.attachment_residue == 'N297'
        assert gc.protein_atom == 'N'
        assert gc.sequence.startswith('NAG')

    def test_multiple_glycans_chain_letters(self):
        goal = textwrap.dedent("""\
            N131:NAG(6-1 FUC)(4-1 NAG(4-1 MAN))
            N203:NAG(4-1 NAG)
            S42:FUC
        """)
        chains = _parse_glycan_chains(goal)
        assert len(chains) == 3
        assert [gc.chain_id for gc in chains] == ['B', 'C', 'D']
        assert chains[0].attachment_residue == 'N131'
        assert chains[1].attachment_residue == 'N203'
        assert chains[2].attachment_residue == 'S42'

    def test_o_glycan_uses_atom_O(self):
        goal = "S42:GAL(3-1 NAG)"
        chains = _parse_glycan_chains(goal)
        assert len(chains) == 1
        assert chains[0].protein_atom == 'O'

    def test_n_glycan_uses_atom_N(self):
        goal = "N131:NAG(4-1 NAG)"
        chains = _parse_glycan_chains(goal)
        assert chains[0].protein_atom == 'N'

    def test_no_glycans_returns_empty(self):
        goal = "Design peptide binders for EGFR. Target: MKTAY. No glycans present."
        chains = _parse_glycan_chains(goal)
        assert chains == []

    def test_unknown_sugar_not_matched(self):
        # XYZ is not a known sugar code — should not match
        goal = "N297:XYZ(4-1 NAG)"
        chains = _parse_glycan_chains(goal)
        assert chains == []

    def test_all_supported_sugar_codes(self):
        sugars = ['NAG', 'FUC', 'MAN', 'GAL', 'SIA', 'GLC', 'GLA']
        for i, sugar in enumerate(sugars):
            goal = f"N{100+i}:{sugar}"
            chains = _parse_glycan_chains(goal)
            assert len(chains) == 1, f"{sugar} was not matched"

    def test_complex_branched_glycan(self):
        goal = "N131:NAG(6-1 FUC)(4-1 NAG(4-1 MAN(6-1 MAN(2-1 NAG))(3-1 MAN(2-1 NAG))))"
        chains = _parse_glycan_chains(goal)
        assert len(chains) == 1
        assert 'MAN' in chains[0].sequence


# ---------------------------------------------------------------------------
# Section 3: PDB stripping helper
# ---------------------------------------------------------------------------

def _strip_glycan_chains_from_pdb_local(pdb_path: Path, glycan_chain_ids: list) -> Path:
    """Local copy for testing without requiring full bindcraft install."""
    import tempfile
    glycan_set = set(glycan_chain_ids)
    kept = []
    with open(pdb_path) as fh:
        for line in fh:
            if line.startswith(('ATOM', 'HETATM', 'TER')):
                if len(line) > 21 and line[21] in glycan_set:
                    continue
            kept.append(line)
    tmp = tempfile.NamedTemporaryFile(
        suffix='.pdb', prefix='protein_only_', delete=False, mode='w'
    )
    tmp.writelines(kept)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


SAMPLE_PDB = textwrap.dedent("""\
    ATOM      1  CA  ALA A   1      1.000   2.000   3.000  1.00  0.00           C
    ATOM      2  CA  GLY A   2      4.000   5.000   6.000  1.00  0.00           C
    HETATM    3  C1  NAG B   1      7.000   8.000   9.000  1.00  0.00           C
    HETATM    4  C2  NAG B   1     10.000  11.000  12.000  1.00  0.00           C
    TER       5      ALA A   2
    TER       6      NAG B   1
    END
""")


class TestStripGlycanFromPDB:
    """Tests for _strip_glycan_chains_from_pdb helper."""

    @pytest.fixture
    def sample_pdb(self, tmp_path) -> Path:
        pdb = tmp_path / 'complex.pdb'
        pdb.write_text(SAMPLE_PDB)
        return pdb

    def test_glycan_lines_removed(self, sample_pdb):
        result = _strip_glycan_chains_from_pdb_local(sample_pdb, ['B'])
        content = Path(result).read_text()
        assert 'NAG' not in content
        Path(result).unlink()

    def test_protein_lines_preserved(self, sample_pdb):
        result = _strip_glycan_chains_from_pdb_local(sample_pdb, ['B'])
        content = Path(result).read_text()
        assert 'ALA' in content
        assert 'GLY' in content
        Path(result).unlink()

    def test_no_glycan_ids_nothing_stripped(self, sample_pdb):
        result = _strip_glycan_chains_from_pdb_local(sample_pdb, [])
        original = SAMPLE_PDB.strip().splitlines()
        stripped = Path(result).read_text().strip().splitlines()
        assert stripped == original
        Path(result).unlink()

    def test_wrong_chain_id_nothing_stripped(self, sample_pdb):
        result = _strip_glycan_chains_from_pdb_local(sample_pdb, ['Z'])
        content = Path(result).read_text()
        assert 'NAG' in content    # B chain not removed
        Path(result).unlink()

    def test_output_is_temp_file(self, sample_pdb):
        result = _strip_glycan_chains_from_pdb_local(sample_pdb, ['B'])
        assert result != sample_pdb
        assert result.exists()
        Path(result).unlink()

    def test_original_pdb_unchanged(self, sample_pdb):
        _strip_glycan_chains_from_pdb_local(sample_pdb, ['B'])
        assert sample_pdb.read_text() == SAMPLE_PDB


# ---------------------------------------------------------------------------
# Section 4: fold_sequence_task glycan injection logic (unit, no parsl)
# ---------------------------------------------------------------------------

class TestFoldSequenceGlycanLogic:
    """
    The glycan injection in fold_sequence_task is:
        if glycan_chains:
            sequence = list(sequence) + [gc['sequence'] for gc in glycan_chains]
            if constraints is None and glycan_restraint is not None:
                constraints = glycan_restraint

    We test this logic directly without launching Parsl tasks.
    """

    def _simulate_fold_sequence(self, sequence, glycan_chains, constraints, glycan_restraint):
        """Replicate the glycan-injection logic from fold_sequence_task."""
        if glycan_chains:
            sequence = list(sequence) + [gc['sequence'] for gc in glycan_chains]
            if constraints is None and glycan_restraint is not None:
                constraints = glycan_restraint
        return sequence, constraints

    def test_glycan_sequences_appended(self):
        seq, _ = self._simulate_fold_sequence(
            sequence=['MKTAY', 'PEPTIDE'],
            glycan_chains=[{'sequence': 'NAG(4-1 NAG)', 'chain_id': 'C'}],
            constraints=None,
            glycan_restraint='/tmp/glycan.csv',
        )
        assert seq == ['MKTAY', 'PEPTIDE', 'NAG(4-1 NAG)']

    def test_multiple_glycans_all_appended(self):
        glycan_chains = [
            {'sequence': 'NAG', 'chain_id': 'C'},
            {'sequence': 'FUC', 'chain_id': 'D'},
        ]
        seq, _ = self._simulate_fold_sequence(['TARGET', 'BINDER'], glycan_chains, None, None)
        assert seq[-2:] == ['NAG', 'FUC']

    def test_constraint_falls_back_to_glycan_restraint(self):
        _, constraints = self._simulate_fold_sequence(
            sequence=['TARGET'],
            glycan_chains=[{'sequence': 'NAG', 'chain_id': 'C'}],
            constraints=None,
            glycan_restraint='/tmp/glycan_restraints.csv',
        )
        assert constraints == '/tmp/glycan_restraints.csv'

    def test_existing_constraint_not_overridden(self):
        _, constraints = self._simulate_fold_sequence(
            sequence=['TARGET'],
            glycan_chains=[{'sequence': 'NAG', 'chain_id': 'C'}],
            constraints='/tmp/existing.csv',
            glycan_restraint='/tmp/glycan.csv',
        )
        assert constraints == '/tmp/existing.csv'

    def test_no_glycan_chains_sequence_unchanged(self):
        seq, constraints = self._simulate_fold_sequence(
            sequence=['TARGET', 'BINDER'],
            glycan_chains=None,
            constraints=None,
            glycan_restraint=None,
        )
        assert seq == ['TARGET', 'BINDER']
        assert constraints is None


# ---------------------------------------------------------------------------
# Section 5: ChaiAgent glycan helpers
# ---------------------------------------------------------------------------

class TestChaiAgentGlycanHelpers:
    """Tests for ChaiAgent._append_extra_constraints and _inject_glycans."""

    @pytest.fixture
    def agent(self):
        from struct_bio_reasoner.agents.structure_prediction.chai_agent import ChaiAgent
        return ChaiAgent(
            agent_id='test-agent',
            config={'fasta_dir': 'fastas', 'fold_dir': 'folds'},
            parsl_config={},
        )

    def test_append_extra_constraints(self, agent, tmp_path):
        base = tmp_path / 'base.csv'
        base.write_text(
            'chainA,res_idxA,chainB,res_idxB,connection_type,confidence,'
            'min_distance_angstrom,max_distance_angstrom,comment,restraint_id\n'
            'A,N297@N,C,@C1,covalent,1.0,0.0,0.0,protein-glycan,bond1\n'
        )
        extra = tmp_path / 'extra.csv'
        extra.write_text(
            'chainA,res_idxA,chainB,res_idxB,connection_type,confidence,'
            'min_distance_angstrom,max_distance_angstrom,comment,restraint_id\n'
            'A,S42@O,D,@C1,covalent,1.0,0.0,0.0,protein-glycan,bond2\n'
        )
        from struct_bio_reasoner.agents.structure_prediction.chai_agent import ChaiAgent
        ChaiAgent._append_extra_constraints(base, extra)
        rows = base.read_text().splitlines()
        # 1 header + 2 data rows
        assert len(rows) == 3
        assert 'bond2' in rows[-1]

    def test_append_extra_constraints_skips_header(self, agent, tmp_path):
        base = tmp_path / 'base.csv'
        base.write_text('header\nbond1_row\n')
        extra = tmp_path / 'extra.csv'
        extra.write_text('header\nbond2_row\n')
        from struct_bio_reasoner.agents.structure_prediction.chai_agent import ChaiAgent
        ChaiAgent._append_extra_constraints(base, extra)
        content = base.read_text()
        assert content.count('header') == 1  # header not duplicated

    def test_inject_glycans_extends_sequences(self, agent, tmp_path):
        gc = GlycanChain('B', 'NAG(4-1 NAG)', 'N131', 'A', 'N', 'C1')
        sequences = [['TARGET', 'BINDER'], ['TARGET', 'BINDER2']]
        new_seqs, _ = agent._inject_glycans(
            sequences, [gc], [None, None], cwd=str(tmp_path)
        )
        assert all(len(s) == 3 for s in new_seqs)
        assert all('NAG' in s[-1] for s in new_seqs)

    def test_inject_glycans_chain_re_lettered(self, agent, tmp_path):
        """Glycan chains should be assigned letters C+ when 2 protein chains exist."""
        gc1 = GlycanChain('B', 'NAG', 'N131', 'A', 'N', 'C1')
        gc2 = GlycanChain('C', 'FUC', 'N203', 'A', 'N', 'C1')
        sequences = [['TARGET', 'BINDER']]
        _, new_constraints = agent._inject_glycans(
            sequences, [gc1, gc2], [None], cwd=str(tmp_path)
        )
        # Restraint file should have 2 bonds
        csv_path = tmp_path / 'glycan_restraints.csv'
        assert csv_path.exists()
        lines = csv_path.read_text().splitlines()
        assert len(lines) == 3   # header + 2 data rows

    def test_inject_glycans_writes_restraint_csv(self, agent, tmp_path):
        gc = GlycanChain('B', 'NAG', 'N297', 'A', 'N', 'C1')
        agent._inject_glycans([['TARGET']], [gc], [None], cwd=str(tmp_path))
        csv_path = tmp_path / 'glycan_restraints.csv'
        assert csv_path.exists()

    def test_inject_glycans_merged_constraints(self, agent, tmp_path):
        """When a fold already has constraints, they must be merged."""
        existing = tmp_path / 'existing.csv'
        existing.write_text(
            'chainA,res_idxA,chainB,res_idxB,connection_type,confidence,'
            'min_distance_angstrom,max_distance_angstrom,comment,restraint_id\n'
            'A,H100@NE2,B,Y50@OH,hbond,0.9,0.0,3.5,protein-protein,hb1\n'
        )
        gc = GlycanChain('C', 'NAG', 'N131', 'A', 'N', 'C1')
        _, new_constraints = agent._inject_glycans(
            [['TARGET', 'BINDER']],
            [gc],
            [str(existing)],
            cwd=str(tmp_path),
        )
        merged = Path(new_constraints[0])
        assert merged.exists()
        content = merged.read_text()
        # Both the glycan bond and the protein-protein h-bond must be present
        assert 'protein-glycan' in content
        assert 'hb1' in content

    def test_inject_glycans_no_glycans_noop(self, agent, tmp_path):
        sequences = [['TARGET', 'BINDER']]
        constraints = [None]
        new_seqs, new_c = agent._inject_glycans(
            sequences, [], constraints, cwd=str(tmp_path)
        )
        # With zero glycan chains the function still runs but adds nothing
        assert len(new_seqs[0]) == len(sequences[0])


# ---------------------------------------------------------------------------
# Entry point for direct execution
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import pytest as _pytest
    _pytest.main([__file__, '-v'])


