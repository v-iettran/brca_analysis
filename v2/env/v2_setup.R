# Pipeline v2 R environment. Handoff to Python is parquet via arrow.
# CBC is the CARNIVAL solver (lpSolve will not scale to a genome-wide PKN).

if (!requireNamespace("BiocManager", quietly = TRUE)) {
  install.packages("BiocManager", repos = "https://cloud.r-project.org")
}

BiocManager::install(
  c("CARNIVAL", "decoupleR", "OmnipathR", "limma", "sva"),
  update = FALSE,
  ask = FALSE
)

install.packages(
  c("devtools", "data.table", "arrow", "jsonlite"),
  repos = "https://cloud.r-project.org"
)

if (!requireNamespace("BayesPrism", quietly = TRUE)) {
  devtools::install_github("Danko-Lab/BayesPrism/BayesPrism")
}

message("v2 R setup complete. Confirm with:")
message("  library(CARNIVAL); library(OmnipathR); library(arrow)")
message("  if (requireNamespace('BayesPrism', quietly=TRUE)) library(BayesPrism)")
