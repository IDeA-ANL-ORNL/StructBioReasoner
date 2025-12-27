"""
Metric Evaluation and Logging for Agentic Binder Pipeline

This module provides utilities to:
1. Compile metrics from pipeline iterations (decisions, energies, sequences, RMSD, RMSF)
2. Log metrics to Weights & Biases (wandb)

Usage:
    from struct_bio_reasoner.utils.metric_eval import MetricEvaluator
    
    # Initialize evaluator
    evaluator = MetricEvaluator(
        project_name="binder_design",
        run_name="nmnat2_experiment_1"
    )
    
    # Update metrics after each iteration
    evaluator.update_metrics(
        decision="computational_design",
        binder_results=results,
        md_results=md_analysis,
        fe_results=fe_analysis
    )
    
    # Get compiled metrics dictionary
    metrics = evaluator.get_metrics()
    
    # Log to wandb
    evaluator.log_to_wandb(step=iteration)
"""

import logging
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


class MetricEvaluator:
    """
    Evaluates and logs metrics from the agentic binder design pipeline.
    
    Tracks:
    - decision_list: Agent decisions mapped to indices (0-4)
    - best_binder_energy: Best binding energy per iteration
    - best_binder_free_energy: Best free energy per iteration
    - best_binder_sequence: Best binder sequence per iteration
    - binder_rmsds: RMSD values from MD simulations
    - binder_rmsfs: RMSF values from MD simulations
    """
    
    # Agent name to index mapping
    AGENT_MAPPING = {
        'computational_design': 0,
        'molecular_dynamics': 1,
        'analysis': 2,
        'free_energy': 3,
        'rag': 4
    }
    
    def __init__(
        self,
        project_name: str = "binder_design",
        run_name: Optional[str] = None,
        enable_wandb: bool = True,
        wandb_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the metric evaluator.
        
        Args:
            project_name: W&B project name
            run_name: W&B run name (optional, auto-generated if None)
            enable_wandb: Whether to enable W&B logging
            wandb_config: Additional W&B configuration
        """
        self.project_name = project_name
        self.run_name = run_name
        self.enable_wandb = enable_wandb
        self.wandb_config = wandb_config or {}
        
        # Initialize metrics dictionary
        self.metrics = {
            'decision_list': [],
            'best_binder_energy': [],
            'best_binder_free_energy': [],
            'best_binder_sequence': [],
            'binder_rmsds': [],
            'binder_rmsfs': []
        }
        
        # W&B run object
        self.wandb_run = None
        
        # Initialize W&B if enabled
        if self.enable_wandb:
            self._initialize_wandb()
    
    def _initialize_wandb(self):
        """Initialize Weights & Biases logging."""
        try:
            import wandb
            
            self.wandb_run = wandb.init(
                project=self.project_name,
                name=self.run_name,
                config=self.wandb_config,
                reinit=True
            )
            
            logger.info(f"W&B initialized: project={self.project_name}, run={self.run_name}")
            
        except ImportError:
            logger.warning("wandb not installed. Install with: pip install wandb")
            self.enable_wandb = False
        except Exception as e:
            logger.error(f"Failed to initialize W&B: {e}")
            self.enable_wandb = False
    
    def update_metrics(
        self,
        decision: str,
        binder_results: Optional[Any] = None,
        md_results: Optional[Any] = None,
        fe_results: Optional[Any] = None
    ):
        """
        Update metrics with results from current iteration.
        
        Args:
            decision: Agent decision name (e.g., 'computational_design')
            binder_results: Results from BindCraft agent (BinderAnalysis object)
            md_results: Results from MD agent (SimAnalysis object or dict)
            fe_results: Results from free energy agent (EnergeticAnalysis object or dict)
        """
        # Map decision to index
        decision_idx = self.AGENT_MAPPING.get(decision, -1)
        self.metrics['decision_list'].append(decision_idx)

        logger.info(f"Updating metrics for decision: {decision} (index: {decision_idx})")

        # Extract binder energy and sequence
        if binder_results is not None:
            energy, sequence = self._extract_binder_info(binder_results)
            self.metrics['best_binder_energy'].append(energy)
            self.metrics['best_binder_sequence'].append(sequence)
        else:
            self.metrics['best_binder_energy'].append(None)
            self.metrics['best_binder_sequence'].append(None)

        # Extract free energy
        if fe_results is not None:
            free_energy = self._extract_free_energy(fe_results)
            self.metrics['best_binder_free_energy'].append(free_energy)
        else:
            self.metrics['best_binder_free_energy'].append(None)

        # Extract RMSD and RMSF from MD results
        if md_results is not None:
            rmsd, rmsf = self._extract_md_metrics(md_results)
            self.metrics['binder_rmsds'].append(rmsd)
            self.metrics['binder_rmsfs'].append(rmsf)
        else:
            self.metrics['binder_rmsds'].append(None)
            self.metrics['binder_rmsfs'].append(None)

    def _extract_binder_info(self, binder_results: Any) -> tuple[Optional[float], Optional[str]]:
        """
        Extract best binder energy and sequence from BinderAnalysis results.

        Args:
            binder_results: BinderAnalysis object or dict

        Returns:
            Tuple of (best_energy, best_sequence)
        """
        try:
            # Handle BinderAnalysis object
            if hasattr(binder_results, 'top_binders'):
                top_binders = binder_results.top_binders
            elif isinstance(binder_results, dict) and 'top_binders' in binder_results:
                top_binders = binder_results['top_binders']
            else:
                logger.warning("Could not find top_binders in binder_results")
                return None, None

            # top_binders is a dict with integer keys
            if not top_binders or len(top_binders) == 0:
                return None, None

            # Get the first (best) binder
            best_binder = top_binders[0]

            # Extract energy
            energy = best_binder.get('energy', None)

            # Extract sequence - try multiple possible keys
            sequence = None
            for key in ['sequence', 'binder_sequence', 'seq']:
                if key in best_binder:
                    sequence = best_binder[key]
                    break

            # If sequence not found, try to read from PDB file
            if sequence is None and 'pdb_path' in best_binder:
                try:
                    from ..utils.protein_utils import pdb2seq
                    pdb_path = Path(best_binder['pdb_path'])
                    if pdb_path.exists():
                        _, sequence = pdb2seq(pdb_path)
                except Exception as e:
                    logger.warning(f"Could not extract sequence from PDB: {e}")

            logger.info(f"Extracted binder: energy={energy}, sequence_len={len(sequence) if sequence else 0}")
            return energy, sequence

        except Exception as e:
            logger.error(f"Error extracting binder info: {e}")
            return None, None

    def _extract_free_energy(self, fe_results: Any) -> Optional[float]:
        """
        Extract best free energy from EnergeticAnalysis results.

        Args:
            fe_results: EnergeticAnalysis object or dict

        Returns:
            Best free energy value (kcal/mol)
        """
        try:
            # Handle EnergeticAnalysis object
            if hasattr(fe_results, 'binding_affinities'):
                binding_affinities = fe_results.binding_affinities
            elif isinstance(fe_results, dict) and 'binding_affinities' in fe_results:
                binding_affinities = fe_results['binding_affinities']
            else:
                logger.warning("Could not find binding_affinities in fe_results")
                return None

            # binding_affinities is a dict with path keys and {'mean', 'std', 'unit'} values
            if not binding_affinities:
                return None

            # Get all mean values
            mean_values = []
            for path, data in binding_affinities.items():
                if isinstance(data, dict) and 'mean' in data:
                    mean = data['mean']
                    if mean is not None:
                        mean_values.append(mean)

            # Return the best (most negative) free energy
            if mean_values:
                best_fe = min(mean_values)
                logger.info(f"Extracted free energy: {best_fe} kcal/mol")
                return best_fe

            return None

        except Exception as e:
            logger.error(f"Error extracting free energy: {e}")
            return None

    def _extract_md_metrics(self, md_results: Any) -> tuple[Optional[float], Optional[float]]:
        """
        Extract RMSD and RMSF from MD simulation results.

        Args:
            md_results: SimAnalysis object or dict

        Returns:
            Tuple of (mean_rmsd, mean_rmsf)
        """
        try:
            # Handle SimAnalysis object or dict
            if hasattr(md_results, 'paths'):
                # This is a dict with 'paths' key from MD agent
                paths = md_results.paths if hasattr(md_results, 'paths') else md_results.get('paths', [])
                # For now, we don't have direct RMSD/RMSF in this format
                # These would need to be extracted from trajectory analysis
                logger.warning("MD results contain paths but no direct RMSD/RMSF data")
                return None, None

            # Try to extract from trajectory analysis format
            rmsd = None
            rmsf = None

            # Check for various possible structures
            if isinstance(md_results, dict):
                # Format 1: Direct rmsd/rmsf keys
                if 'rmsd' in md_results:
                    rmsd_data = md_results['rmsd']
                    if isinstance(rmsd_data, dict) and 'mean' in rmsd_data:
                        rmsd = rmsd_data['mean']
                    elif isinstance(rmsd_data, (int, float)):
                        rmsd = rmsd_data

                if 'rmsf' in md_results:
                    rmsf_data = md_results['rmsf']
                    if isinstance(rmsf_data, dict) and 'mean' in rmsf_data:
                        rmsf = rmsf_data['mean']
                    elif isinstance(rmsf_data, (int, float)):
                        rmsf = rmsf_data

                # Format 2: Nested in trajectory_analysis
                if 'trajectory_analysis' in md_results:
                    traj = md_results['trajectory_analysis']
                    if 'rmsd' in traj:
                        rmsd_data = traj['rmsd']
                        if isinstance(rmsd_data, dict) and 'mean' in rmsd_data:
                            rmsd = rmsd_data['mean']
                    if 'rmsf' in traj:
                        rmsf_data = traj['rmsf']
                        if isinstance(rmsf_data, dict) and 'mean' in rmsf_data:
                            rmsf = rmsf_data['mean']

            logger.info(f"Extracted MD metrics: RMSD={rmsd}, RMSF={rmsf}")
            return rmsd, rmsf

        except Exception as e:
            logger.error(f"Error extracting MD metrics: {e}")
            return None, None

    def get_metrics(self) -> Dict[str, List]:
        """
        Get the compiled metrics dictionary.

        Returns:
            Dictionary with all tracked metrics
        """
        return self.metrics.copy()

    def log_to_wandb(self, step: Optional[int] = None, additional_metrics: Optional[Dict[str, Any]] = None):
        """
        Log current metrics to Weights & Biases.

        Args:
            step: Current iteration/step number
            additional_metrics: Additional metrics to log
        """
        if not self.enable_wandb or self.wandb_run is None:
            logger.warning("W&B logging not enabled or not initialized")
            return

        try:
            import wandb

            # Prepare metrics for logging
            log_dict = {}

            # Log the most recent values
            if self.metrics['decision_list']:
                log_dict['decision'] = self.metrics['decision_list'][-1]

            if self.metrics['best_binder_energy']:
                energy = self.metrics['best_binder_energy'][-1]
                if energy is not None:
                    log_dict['best_binder_energy'] = energy

            if self.metrics['best_binder_free_energy']:
                fe = self.metrics['best_binder_free_energy'][-1]
                if fe is not None:
                    log_dict['best_binder_free_energy'] = fe

            if self.metrics['binder_rmsds']:
                rmsd = self.metrics['binder_rmsds'][-1]
                if rmsd is not None:
                    log_dict['binder_rmsd'] = rmsd

            if self.metrics['binder_rmsfs']:
                rmsf = self.metrics['binder_rmsfs'][-1]
                if rmsf is not None:
                    log_dict['binder_rmsf'] = rmsf

            # Log sequence length instead of full sequence
            if self.metrics['best_binder_sequence']:
                seq = self.metrics['best_binder_sequence'][-1]
                if seq is not None:
                    log_dict['binder_sequence_length'] = len(seq)

            # Add cumulative statistics
            log_dict['total_iterations'] = len(self.metrics['decision_list'])

            # Count decisions by type
            for agent_name, agent_idx in self.AGENT_MAPPING.items():
                count = self.metrics['decision_list'].count(agent_idx)
                log_dict[f'decision_count_{agent_name}'] = count

            # Add best energy so far
            energies = [e for e in self.metrics['best_binder_energy'] if e is not None]
            if energies:
                log_dict['best_energy_overall'] = min(energies)
                log_dict['mean_energy'] = np.mean(energies)

            # Add best free energy so far
            free_energies = [fe for fe in self.metrics['best_binder_free_energy'] if fe is not None]
            if free_energies:
                log_dict['best_free_energy_overall'] = min(free_energies)
                log_dict['mean_free_energy'] = np.mean(free_energies)

            # Add RMSD/RMSF statistics
            rmsds = [r for r in self.metrics['binder_rmsds'] if r is not None]
            if rmsds:
                log_dict['mean_rmsd'] = np.mean(rmsds)
                log_dict['std_rmsd'] = np.std(rmsds)

            rmsfs = [r for r in self.metrics['binder_rmsfs'] if r is not None]
            if rmsfs:
                log_dict['mean_rmsf'] = np.mean(rmsfs)
                log_dict['std_rmsf'] = np.std(rmsfs)

            # Add any additional metrics
            if additional_metrics:
                log_dict.update(additional_metrics)

            # Log to W&B
            wandb.log(log_dict, step=step)

            logger.info(f"Logged metrics to W&B (step={step}): {list(log_dict.keys())}")

        except Exception as e:
            logger.error(f"Error logging to W&B: {e}")

    def log_summary(self):
        """
        Log final summary statistics to W&B.
        """
        if not self.enable_wandb or self.wandb_run is None:
            logger.warning("W&B logging not enabled or not initialized")
            return

        try:
            import wandb

            summary_dict = {}

            # Total iterations
            summary_dict['total_iterations'] = len(self.metrics['decision_list'])

            # Decision distribution
            for agent_name, agent_idx in self.AGENT_MAPPING.items():
                count = self.metrics['decision_list'].count(agent_idx)
                summary_dict[f'total_{agent_name}_decisions'] = count

            # Best metrics
            energies = [e for e in self.metrics['best_binder_energy'] if e is not None]
            if energies:
                summary_dict['final_best_energy'] = min(energies)
                summary_dict['final_mean_energy'] = np.mean(energies)
                summary_dict['final_std_energy'] = np.std(energies)

            free_energies = [fe for fe in self.metrics['best_binder_free_energy'] if fe is not None]
            if free_energies:
                summary_dict['final_best_free_energy'] = min(free_energies)
                summary_dict['final_mean_free_energy'] = np.mean(free_energies)
                summary_dict['final_std_free_energy'] = np.std(free_energies)

            rmsds = [r for r in self.metrics['binder_rmsds'] if r is not None]
            if rmsds:
                summary_dict['final_mean_rmsd'] = np.mean(rmsds)
                summary_dict['final_std_rmsd'] = np.std(rmsds)

            rmsfs = [r for r in self.metrics['binder_rmsfs'] if r is not None]
            if rmsfs:
                summary_dict['final_mean_rmsf'] = np.mean(rmsfs)
                summary_dict['final_std_rmsf'] = np.std(rmsfs)

            # Update W&B summary
            for key, value in summary_dict.items():
                wandb.run.summary[key] = value

            logger.info(f"Logged summary to W&B: {list(summary_dict.keys())}")

        except Exception as e:
            logger.error(f"Error logging summary to W&B: {e}")

    def finish(self):
        """
        Finish W&B run and cleanup.
        """
        if self.enable_wandb and self.wandb_run is not None:
            try:
                import wandb

                # Log final summary
                self.log_summary()

                # Finish the run
                wandb.finish()

                logger.info("W&B run finished")

            except Exception as e:
                logger.error(f"Error finishing W&B run: {e}")

    def reset(self):
        """
        Reset all metrics to empty lists.
        """
        self.metrics = {
            'decision_list': [],
            'best_binder_energy': [],
            'best_binder_free_energy': [],
            'best_binder_sequence': [],
            'binder_rmsds': [],
            'binder_rmsfs': []
        }
        logger.info("Metrics reset")

    def save_metrics(self, filepath: Union[str, Path]):
        """
        Save metrics to a JSON file.

        Args:
            filepath: Path to save metrics
        """
        import json

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Convert to JSON-serializable format
        metrics_to_save = {}
        for key, values in self.metrics.items():
            if key == 'best_binder_sequence':
                # Save sequences as-is
                metrics_to_save[key] = values
            else:
                # Convert None and numpy types to JSON-compatible
                metrics_to_save[key] = [
                    float(v) if isinstance(v, (np.integer, np.floating)) else v
                    for v in values
                ]

        with open(filepath, 'w') as f:
            json.dump(metrics_to_save, f, indent=2)

        logger.info(f"Metrics saved to {filepath}")

    def load_metrics(self, filepath: Union[str, Path]):
        """
        Load metrics from a JSON file.

        Args:
            filepath: Path to load metrics from
        """
        import json

        filepath = Path(filepath)

        with open(filepath, 'r') as f:
            loaded_metrics = json.load(f)

        self.metrics = loaded_metrics

        logger.info(f"Metrics loaded from {filepath}")

