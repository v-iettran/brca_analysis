#!/usr/bin/env bash
# Copy the current work into the git repository, ready to review and commit.
#
# The working folder (final-project) and the git repository (brca_analysis) are
# two separate copies. Nothing you change here reaches GitHub until it has been
# copied across, and the repository is currently frozen at 25 August.
#
# This script only copies files. It does not commit, and it does not push.
# Run it, then look at `git status` and `git diff` before deciding anything.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../brca_analysis" && pwd)"

if [ ! -d "$REPO/.git" ]; then
  echo "Could not find the git repository at $REPO" >&2
  exit 1
fi

echo "Copying from : $HERE"
echo "Copying into : $REPO"
echo

# Everything the running app and the pipeline need. Raw data, virtual
# environments and build output are all left behind: they are large, they are
# regenerated, and several are far too big for GitHub.
rsync -a --delete \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude '.next/' \
  --exclude '.venv/' \
  --exclude '.venv_copilot/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.DS_Store' \
  --exclude '*.pyc' \
  "$HERE/application/" "$REPO/application/"

rsync -a \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.DS_Store' \
  "$HERE/v3/src/"       "$REPO/v3/src/"
rsync -a --exclude '__pycache__/' "$HERE/v3/scripts/"   "$REPO/v3/scripts/"
rsync -a --exclude '__pycache__/' "$HERE/v3/tests/"     "$REPO/v3/tests/"
rsync -a "$HERE/v3/notebooks/"      "$REPO/v3/notebooks/"
rsync -a "$HERE/v3/data/reference/" "$REPO/v3/data/reference/"

# Environment definitions for the R and Julia stages (BayesPrism, CARNIVAL,
# StructuralIdentifiability). Without these the pipeline is not reproducible.
rsync -a "$HERE/v3/env/" "$REPO/v3/env/"

# The gate ledger, the pre-registrations and the figures are the audit trail for
# every claim the panel makes, so they travel with the code.
mkdir -p "$REPO/v3/reports"
rsync -a "$HERE/v3/reports/" "$REPO/v3/reports/"

# Small model metadata. The trained weights themselves (.eqx, .pkl, .npz) are
# excluded by .gitignore -- they are large and regenerated.
mkdir -p "$REPO/v3/artifacts"
rsync -a --include '*.json' --include '.gitkeep' --exclude '*' \
  "$HERE/v3/artifacts/" "$REPO/v3/artifacts/"

for f in pytest.ini .gitignore; do
  [ -f "$HERE/v3/$f" ] && cp "$HERE/v3/$f" "$REPO/v3/$f"
done

# specs/ is deliberately not published: working design material, kept locally,
# and stale relative to what was actually built.
cp "$HERE/.dockerignore" "$REPO/.dockerignore"

# Root documentation. The README is the public face of the repository and links
# to DEPLOY.md, which in turn documents this script -- so the three are kept
# together rather than left to drift apart.
for f in README.md DEPLOY.md sync_to_repo.sh; do
  cp "$HERE/$f" "$REPO/$f"
done

echo
echo "Done. Nothing has been committed or pushed."
echo
echo "Next:"
echo "  cd $REPO"
echo "  git status              # see what changed"
echo "  git add -A"
echo "  git commit -m 'v3.2: clinical redesign, evidence tiers, grounded copilot'"
echo "  git push                # this is the step that makes it public"
