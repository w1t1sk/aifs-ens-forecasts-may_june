#!/bin/bash
# Submit an AIFS-ENS batch inference job for a single year via Slurm.
#
# Usage:
#   sbatch submit_job.sh 2009
#   sbatch submit_job.sh 2009 --start-month 5 --end-month 6
#
# All extra arguments after the year are forwarded verbatim to
# 2_batch_inference.py.  See that script for the full list of flags.
#
# Adjust the #SBATCH directives below to match your cluster's configuration.
# The script expects the Apptainer container to be at the path set in
# CONTAINER_PATH (edit as needed).

#SBATCH --job-name=aifs-ens
#SBATCH --partition=GPU-AI_prio
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --output=slurm-%j-%x.out
#SBATCH --error=slurm-%j-%x.err

# ---------------------------------------------------------------------------
YEAR=${1:?'Usage: sbatch submit_job.sh YYYY [extra args...]'}
shift                       # remaining args forwarded to the Python script

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_PATH="${REPO_ROOT}/../aifs-crps-ens.sif"   # default location

if [[ ! -f "$CONTAINER_PATH" ]]; then
    echo "ERROR: Container not found at $CONTAINER_PATH"
    echo "Build it with:  apptainer build aifs-crps-ens.sif environment/aifs-crps-ens.def"
    exit 1
fi

echo "=== AIFS-ENS Inference: Year $YEAR ==="
echo "Container: $CONTAINER_PATH"
echo "Repo root: $REPO_ROOT"

apptainer exec --nv "$CONTAINER_PATH" \
    python3 "$REPO_ROOT/scripts/2_batch_inference.py" \
        --year "$YEAR" \
        "$@"
