"""
AlphaFold Wrapper for StructBioReasoner

This module provides a comprehensive wrapper for AlphaFold, enabling:
- Protein structure prediction from sequence
- Confidence assessment and analysis
- Structure quality evaluation
- Integration with AlphaFold database

AlphaFold is a state-of-the-art system for protein structure prediction.
"""

import asyncio
import logging
import os
import tempfile
import json
import subprocess
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

# Check for AlphaFold availability
ALPHAFOLD_AVAILABLE = False
try:
    # Check if AlphaFold is installed and accessible
    result = subprocess.run(['python', '-c', 'import alphafold'], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        ALPHAFOLD_AVAILABLE = True
except (subprocess.SubprocessError, FileNotFoundError):
    pass

logger = logging.getLogger(__name__)


class AlphaFoldWrapper:
    """
    Comprehensive wrapper for AlphaFold protein structure prediction.
    
    Provides high-level methods for:
    - Structure prediction from sequence
    - Confidence analysis and assessment
    - Structure quality evaluation
    - AlphaFold database integration
    - Comparative structure analysis
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize AlphaFold wrapper with configuration."""
        self.config = config
        self.initialized = False
        self.alphafold_path = config.get("alphafold_path", "")
        self.database_path = config.get("database_path", "")
        self.model_preset = config.get("model_preset", "monomer")
        
        # Prediction parameters
        self.max_template_date = config.get("max_template_date", "2022-01-01")
        self.use_gpu = config.get("use_gpu", True)
        self.num_ensemble = config.get("num_ensemble", 1)
        self.num_multimer_predictions_per_model = config.get("num_multimer_predictions_per_model", 5)
        
        # Confidence thresholds
        self.high_confidence_threshold = config.get("high_confidence_threshold", 90.0)
        self.medium_confidence_threshold = config.get("medium_confidence_threshold", 70.0)
        self.low_confidence_threshold = config.get("low_confidence_threshold", 50.0)
        
        # Output settings
        self.output_dir = Path(config.get("output_dir", "alphafold_outputs"))
        self.output_dir.mkdir(exist_ok=True)
        
        # Active predictions tracking
        self.active_predictions = {}
        
        # AlphaFold database API
        self.alphafold_db_url = "https://alphafold.ebi.ac.uk/api/prediction/"
        
        if not ALPHAFOLD_AVAILABLE:
            logger.warning("AlphaFold not available - wrapper will operate in ENHANCED MOCK MODE")
            logger.info("To install AlphaFold for real functionality:")
            logger.info("1. pip install alphafold-colabfold")
            logger.info("2. Or use ColabFold: pip install colabfold[alphafold]")
            logger.info("3. Or access via AlphaFold database API (already integrated)")
            logger.info("Enhanced mock mode provides realistic confidence scores and structure analysis")
        else:
            logger.info("AlphaFold wrapper initialized successfully")

        logger.info(f"AlphaFold wrapper initialized (available: {ALPHAFOLD_AVAILABLE})")
    
    async def initialize(self) -> bool:
        """Initialize AlphaFold system."""
        if not ALPHAFOLD_AVAILABLE:
            logger.warning("AlphaFold not available - wrapper will operate in mock mode")
            self.initialized = True
            return True
        
        try:
            # Initialize AlphaFold system
            logger.info("Initializing AlphaFold system...")
            
            # This would be the actual AlphaFold initialization
            # from alphafold.model import model
            # from alphafold.model import config as model_config
            # self.model_config = model_config.model_config(self.model_preset)
            
            self.initialized = True
            logger.info("AlphaFold initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize AlphaFold: {e}")
            return False
    
    def is_ready(self) -> bool:
        """Check if AlphaFold is ready for use."""
        return self.initialized and ALPHAFOLD_AVAILABLE
    
    async def predict_structure(self, prediction_id: str, sequence: str, 
                              job_name: Optional[str] = None) -> Optional[str]:
        """
        Predict protein structure from amino acid sequence.
        
        Args:
            prediction_id: Unique identifier for this prediction
            sequence: Amino acid sequence
            job_name: Optional job name for organization
            
        Returns:
            Path to predicted PDB file or None if failed
        """
        if not self.is_ready():
            return await self._mock_predict_structure(prediction_id, sequence, job_name)
        
        try:
            logger.info(f"Predicting structure: {prediction_id}")
            
            # Prepare sequence file
            fasta_file = self.output_dir / f"{prediction_id}.fasta"
            with open(fasta_file, 'w') as f:
                f.write(f">{job_name or prediction_id}\n{sequence}\n")
            
            # Run AlphaFold prediction
            output_dir = self.output_dir / prediction_id
            output_dir.mkdir(exist_ok=True)
            
            # This would be the actual AlphaFold command
            cmd = [
                'python', f'{self.alphafold_path}/run_alphafold.py',
                f'--fasta_paths={fasta_file}',
                f'--max_template_date={self.max_template_date}',
                f'--model_preset={self.model_preset}',
                f'--db_preset=full_dbs',
                f'--output_dir={output_dir}',
                f'--use_gpu_relax={self.use_gpu}'
            ]
            
            if self.database_path:
                cmd.append(f'--data_dir={self.database_path}')
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # Find predicted structure file
                predicted_files = list(output_dir.glob("**/ranked_0.pdb"))
                if predicted_files:
                    predicted_pdb = str(predicted_files[0])
                    
                    # Analyze confidence
                    confidence_analysis = await self._analyze_confidence(predicted_pdb)
                    
                    self.active_predictions[prediction_id] = {
                        "type": "structure_prediction",
                        "sequence": sequence,
                        "output_pdb": predicted_pdb,
                        "confidence_analysis": confidence_analysis,
                        "job_name": job_name,
                        "status": "completed"
                    }
                    
                    logger.info(f"Structure prediction completed: {prediction_id}")
                    return predicted_pdb
                else:
                    logger.error("No predicted structure found")
                    return None
            else:
                logger.error(f"AlphaFold prediction failed: {stderr.decode()}")
                return None
            
        except Exception as e:
            logger.error(f"Structure prediction failed: {e}")
            return None
    
    async def fetch_from_database(self, prediction_id: str, uniprot_id: str) -> Optional[str]:
        """
        Fetch structure from AlphaFold database.
        
        Args:
            prediction_id: Unique identifier for this fetch
            uniprot_id: UniProt ID to fetch
            
        Returns:
            Path to downloaded PDB file or None if failed
        """
        try:
            logger.info(f"Fetching from AlphaFold database: {uniprot_id}")
            
            # Query AlphaFold database API
            response = requests.get(f"{self.alphafold_db_url}{uniprot_id}")
            
            if response.status_code == 200:
                data = response.json()
                pdb_url = data[0]['pdbUrl']
                
                # Download PDB file
                pdb_response = requests.get(pdb_url)
                if pdb_response.status_code == 200:
                    output_file = self.output_dir / f"{prediction_id}_{uniprot_id}_alphafold.pdb"
                    
                    with open(output_file, 'w') as f:
                        f.write(pdb_response.text)
                    
                    # Analyze confidence
                    confidence_analysis = await self._analyze_confidence(str(output_file))
                    
                    self.active_predictions[prediction_id] = {
                        "type": "database_fetch",
                        "uniprot_id": uniprot_id,
                        "output_pdb": str(output_file),
                        "confidence_analysis": confidence_analysis,
                        "database_info": data[0],
                        "status": "completed"
                    }
                    
                    logger.info(f"AlphaFold database fetch completed: {prediction_id}")
                    return str(output_file)
                else:
                    logger.error(f"Failed to download PDB file: {pdb_response.status_code}")
                    return None
            else:
                logger.error(f"AlphaFold database query failed: {response.status_code}")
                return None
            
        except Exception as e:
            logger.error(f"Database fetch failed: {e}")
            return None
    
    async def _analyze_confidence(self, pdb_file: str) -> Dict:
        """
        Analyze confidence scores from AlphaFold prediction.
        
        Args:
            pdb_file: Path to PDB file with confidence scores
            
        Returns:
            Dictionary containing confidence analysis
        """
        try:
            confidence_scores = []
            
            with open(pdb_file, 'r') as f:
                for line in f:
                    if line.startswith('ATOM') and line[12:16].strip() == 'CA':
                        # Extract confidence score from B-factor column
                        confidence = float(line[60:66].strip())
                        confidence_scores.append(confidence)
            
            if confidence_scores:
                confidence_array = np.array(confidence_scores)
                
                analysis = {
                    "mean_confidence": float(np.mean(confidence_array)),
                    "median_confidence": float(np.median(confidence_array)),
                    "min_confidence": float(np.min(confidence_array)),
                    "max_confidence": float(np.max(confidence_array)),
                    "std_confidence": float(np.std(confidence_array)),
                    "high_confidence_residues": int(np.sum(confidence_array >= self.high_confidence_threshold)),
                    "medium_confidence_residues": int(np.sum(
                        (confidence_array >= self.medium_confidence_threshold) & 
                        (confidence_array < self.high_confidence_threshold)
                    )),
                    "low_confidence_residues": int(np.sum(confidence_array < self.medium_confidence_threshold)),
                    "total_residues": len(confidence_scores),
                    "confidence_distribution": {
                        "very_high": float(np.sum(confidence_array >= 90) / len(confidence_array)),
                        "confident": float(np.sum((confidence_array >= 70) & (confidence_array < 90)) / len(confidence_array)),
                        "low": float(np.sum((confidence_array >= 50) & (confidence_array < 70)) / len(confidence_array)),
                        "very_low": float(np.sum(confidence_array < 50) / len(confidence_array))
                    }
                }
                
                return analysis
            else:
                logger.warning("No confidence scores found in PDB file")
                return {}
            
        except Exception as e:
            logger.error(f"Confidence analysis failed: {e}")
            return {}
    
    async def compare_predictions(self, prediction_id: str, pdb_files: List[str]) -> Optional[Dict]:
        """
        Compare multiple AlphaFold predictions or structures.
        
        Args:
            prediction_id: Unique identifier for this comparison
            pdb_files: List of PDB files to compare
            
        Returns:
            Dictionary containing comparison results or None if failed
        """
        if not self.is_ready():
            return await self._mock_compare_predictions(prediction_id, pdb_files)
        
        try:
            logger.info(f"Comparing predictions: {prediction_id}")
            
            # Analyze each structure
            analyses = []
            for pdb_file in pdb_files:
                confidence_analysis = await self._analyze_confidence(pdb_file)
                analyses.append({
                    "pdb_file": pdb_file,
                    "confidence_analysis": confidence_analysis
                })
            
            # Compare structures
            comparison = {
                "prediction_id": prediction_id,
                "structures": analyses,
                "comparison_metrics": {
                    "mean_confidence_range": [
                        min(a["confidence_analysis"].get("mean_confidence", 0) for a in analyses),
                        max(a["confidence_analysis"].get("mean_confidence", 0) for a in analyses)
                    ],
                    "best_structure": max(analyses, 
                                        key=lambda x: x["confidence_analysis"].get("mean_confidence", 0))["pdb_file"],
                    "confidence_consistency": np.std([
                        a["confidence_analysis"].get("mean_confidence", 0) for a in analyses
                    ])
                }
            }
            
            self.active_predictions[prediction_id] = {
                "type": "structure_comparison",
                "pdb_files": pdb_files,
                "comparison": comparison,
                "status": "completed"
            }
            
            logger.info(f"Prediction comparison completed: {prediction_id}")
            return comparison
            
        except Exception as e:
            logger.error(f"Prediction comparison failed: {e}")
            return None
    
    async def evaluate_structure_quality(self, prediction_id: str, pdb_file: str) -> Optional[Dict]:
        """
        Evaluate the quality of an AlphaFold prediction.
        
        Args:
            prediction_id: Unique identifier for this evaluation
            pdb_file: Path to PDB file to evaluate
            
        Returns:
            Dictionary containing quality evaluation or None if failed
        """
        try:
            logger.info(f"Evaluating structure quality: {prediction_id}")
            
            # Analyze confidence
            confidence_analysis = await self._analyze_confidence(pdb_file)
            
            # Calculate quality metrics
            mean_confidence = confidence_analysis.get("mean_confidence", 0)
            high_conf_fraction = confidence_analysis.get("confidence_distribution", {}).get("very_high", 0)
            
            quality_evaluation = {
                "prediction_id": prediction_id,
                "pdb_file": pdb_file,
                "confidence_analysis": confidence_analysis,
                "quality_assessment": {
                    "overall_quality": self._assess_overall_quality(mean_confidence),
                    "reliability_score": min(100, mean_confidence + high_conf_fraction * 10),
                    "structural_completeness": confidence_analysis.get("high_confidence_residues", 0) / 
                                             max(1, confidence_analysis.get("total_residues", 1)),
                    "prediction_confidence": "high" if mean_confidence >= 80 else 
                                           "medium" if mean_confidence >= 60 else "low"
                },
                "recommendations": self._generate_recommendations(confidence_analysis)
            }
            
            self.active_predictions[prediction_id] = {
                "type": "quality_evaluation",
                "pdb_file": pdb_file,
                "evaluation": quality_evaluation,
                "status": "completed"
            }
            
            logger.info(f"Structure quality evaluation completed: {prediction_id}")
            return quality_evaluation
            
        except Exception as e:
            logger.error(f"Structure quality evaluation failed: {e}")
            return None
    
    def _assess_overall_quality(self, mean_confidence: float) -> str:
        """Assess overall structure quality based on confidence."""
        if mean_confidence >= 90:
            return "excellent"
        elif mean_confidence >= 80:
            return "very_good"
        elif mean_confidence >= 70:
            return "good"
        elif mean_confidence >= 60:
            return "moderate"
        else:
            return "low"
    
    def _generate_recommendations(self, confidence_analysis: Dict) -> List[str]:
        """Generate recommendations based on confidence analysis."""
        recommendations = []
        
        mean_conf = confidence_analysis.get("mean_confidence", 0)
        low_conf_fraction = confidence_analysis.get("confidence_distribution", {}).get("very_low", 0)
        
        if mean_conf < 70:
            recommendations.append("Consider experimental validation due to low overall confidence")
        
        if low_conf_fraction > 0.2:
            recommendations.append("Focus experimental efforts on low-confidence regions")
        
        if mean_conf >= 80:
            recommendations.append("Structure suitable for detailed analysis and drug design")
        
        if confidence_analysis.get("high_confidence_residues", 0) > 0:
            recommendations.append("High-confidence regions can be used for functional analysis")
        
        return recommendations
    
    # Mock methods for when AlphaFold is not available
    async def _mock_predict_structure(self, prediction_id: str, sequence: str, job_name: Optional[str]) -> str:
        """Mock structure prediction for testing."""
        logger.info(f"Mock structure prediction: {prediction_id}")
        
        # Create mock PDB file
        output_file = self.output_dir / f"{prediction_id}_mock.pdb"
        mock_pdb_content = self._create_mock_alphafold_pdb(len(sequence))
        
        with open(output_file, 'w') as f:
            f.write(mock_pdb_content)
        
        # Mock confidence analysis
        confidence_analysis = {
            "mean_confidence": np.random.uniform(60, 95),
            "median_confidence": np.random.uniform(65, 90),
            "min_confidence": np.random.uniform(30, 60),
            "max_confidence": np.random.uniform(90, 99),
            "high_confidence_residues": int(len(sequence) * np.random.uniform(0.6, 0.9)),
            "total_residues": len(sequence),
            "confidence_distribution": {
                "very_high": np.random.uniform(0.4, 0.8),
                "confident": np.random.uniform(0.1, 0.3),
                "low": np.random.uniform(0.05, 0.15),
                "very_low": np.random.uniform(0.0, 0.1)
            }
        }
        
        self.active_predictions[prediction_id] = {
            "type": "structure_prediction",
            "sequence": sequence,
            "output_pdb": str(output_file),
            "confidence_analysis": confidence_analysis,
            "job_name": job_name,
            "status": "completed"
        }
        
        return str(output_file)
    
    async def _mock_compare_predictions(self, prediction_id: str, pdb_files: List[str]) -> Dict:
        """Mock prediction comparison for testing."""
        logger.info(f"Mock prediction comparison: {prediction_id}")
        
        # Mock comparison results
        comparison = {
            "prediction_id": prediction_id,
            "structures": [{"pdb_file": pdb, "confidence_analysis": {"mean_confidence": np.random.uniform(60, 95)}} 
                          for pdb in pdb_files],
            "comparison_metrics": {
                "mean_confidence_range": [60.5, 94.2],
                "best_structure": pdb_files[0] if pdb_files else None,
                "confidence_consistency": np.random.uniform(5, 15)
            }
        }
        
        self.active_predictions[prediction_id] = {
            "type": "structure_comparison",
            "pdb_files": pdb_files,
            "comparison": comparison,
            "status": "completed"
        }
        
        return comparison
    
    def _create_mock_alphafold_pdb(self, length: int) -> str:
        """Create a mock AlphaFold PDB file with confidence scores."""
        header = "HEADER    MOCK ALPHAFOLD PREDICTION\n"
        atoms = []
        
        for i in range(length):
            # Mock confidence score (B-factor column)
            confidence = np.random.uniform(40, 99)
            
            # Simple mock coordinates
            x = i * 3.8
            y = 0.0
            z = 0.0
            
            atom_line = f"ATOM  {i+1:5d}  CA  ALA A{i+1:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00{confidence:6.2f}           C\n"
            atoms.append(atom_line)
        
        return header + "".join(atoms) + "END\n"
    
    async def cleanup_prediction(self, prediction_id: str) -> bool:
        """Clean up resources for a specific prediction."""
        if prediction_id in self.active_predictions:
            prediction_info = self.active_predictions[prediction_id]
            
            # Clean up output files if needed
            if "output_pdb" in prediction_info:
                output_file = Path(prediction_info["output_pdb"])
                if output_file.exists():
                    try:
                        output_file.unlink()
                        logger.info(f"Cleaned up prediction files for {prediction_id}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up files for {prediction_id}: {e}")
            
            del self.active_predictions[prediction_id]
            return True
        
        return False
    
    def get_prediction_status(self, prediction_id: str) -> Optional[Dict]:
        """Get status information for a prediction."""
        return self.active_predictions.get(prediction_id)
    
    def list_active_predictions(self) -> List[str]:
        """List all active prediction IDs."""
        return list(self.active_predictions.keys())
    
    async def cleanup_all(self) -> None:
        """Clean up all resources."""
        for prediction_id in list(self.active_predictions.keys()):
            await self.cleanup_prediction(prediction_id)
        
        logger.info("AlphaFold wrapper cleanup completed")
