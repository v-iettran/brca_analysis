#!/usr/bin/env node
/**
 * Rebuild the test fixtures from the payloads the API actually serves.
 *
 * Run this after ANY pipeline script that rewrites app/data/v3. A stale fixture
 * does not fail loudly — it silently makes the tests assert the old contract, so
 * a genuinely missing field looks like a passing suite.
 */
import fs from "node:fs";
import path from "node:path";

const SRC = path.resolve("../api/app/data/v3");
const DST = path.resolve("src/components/__tests__/fixtures");
const PATIENTS = ["TCGA-A8-A081", "TCGA-A1-A0SK"];

if (!fs.existsSync(path.join(SRC, "cohort_payload.json"))) {
  console.warn("no v3 payloads on disk; leaving fixtures as they are");
  process.exit(0);
}

const cohort = JSON.parse(fs.readFileSync(path.join(SRC, "cohort_payload.json"), "utf8"));

// Thin the per-sample maps; keep every field the interface reads.
const keep = new Set(Object.keys(cohort.projections.pca).slice(0, 60).concat(PATIENTS));
const only = (obj) => Object.fromEntries(Object.entries(obj ?? {}).filter(([k]) => keep.has(k)));

for (const proj of ["pca", "umap"]) cohort.projections[proj] = only(cohort.projections[proj]);
cohort.posterior_width = only(cohort.posterior_width);
cohort.pam50 = only(cohort.pam50);
cohort.configurations = Object.fromEntries(
  Object.entries(cohort.configurations)
    .filter(([id]) => id === "gmm:full:k=4" || id === "gmm:full:k=5")
    .map(([id, cfg]) => [id, { ...cfg, assignments: only(cfg.assignments), membership: only(cfg.membership) }])
);
delete cohort.reversal_by_cluster;
if (cohort.joint_projection) {
  cohort.joint_projection.tumours = cohort.joint_projection.tumours.slice(0, 150);
  cohort.joint_projection.patients = only(cohort.joint_projection.patients);
}

fs.writeFileSync(path.join(DST, "cohort.json"), JSON.stringify(cohort));
for (const id of PATIENTS) {
  fs.copyFileSync(path.join(SRC, `payload_${id}.json`), path.join(DST, `${id}.json`));
}

const families = {};
for (const row of cohort.cluster_profiles) families[row.family] = (families[row.family] ?? 0) + 1;
console.log("fixtures refreshed:", {
  profileRows: cohort.cluster_profiles.length,
  families,
  jointProjection: Boolean(cohort.joint_projection),
  evidenceReference: Boolean(cohort.evidence_reference),
});
