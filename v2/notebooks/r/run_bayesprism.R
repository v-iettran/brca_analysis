#!/usr/bin/env Rscript
# BayesPrism deconvolution. Called from NB02 via subprocess.
# Args: --reference --mixture --celltypes --cellstates --outdir --cores

user_lib <- file.path(
  Sys.getenv("HOME"), "Library", "R",
  paste0(R.version$major, ".", sub("\\..*", "", R.version$minor)),
  "library"
)
if (dir.exists(user_lib)) .libPaths(c(user_lib, .libPaths()))
if (nzchar(Sys.getenv("R_LIBS_USER")) && dir.exists(Sys.getenv("R_LIBS_USER"))) {
  .libPaths(c(Sys.getenv("R_LIBS_USER"), .libPaths()))
}

args <- commandArgs(trailingOnly = TRUE)
opt <- list(cellstates = "", cores = "4")
i <- 1
while (i <= length(args)) {
  key <- substring(args[[i]], 3)
  opt[[key]] <- args[[i + 1]]
  i <- i + 2
}
dir.create(opt$outdir, recursive = TRUE, showWarnings = FALSE)

if (!requireNamespace("BayesPrism", quietly = TRUE) ||
    !requireNamespace("arrow", quietly = TRUE)) {
  writeLines(
    "BayesPrism or arrow is not installed. Run: Rscript v2/env/v2_setup.R",
    file.path(opt$outdir, "ERROR.txt")
  )
  quit(status = 1)
}

suppressPackageStartupMessages({
  library(BayesPrism)
  library(arrow)
})

sc_df <- as.data.frame(read_parquet(opt$reference))
if ("cell_id" %in% names(sc_df)) {
  rn <- as.character(sc_df$cell_id)
  sc_df$cell_id <- NULL
  sc_ref <- as.matrix(sc_df)
  rownames(sc_ref) <- rn
} else {
  sc_ref <- as.matrix(sc_df)
}

bulk_df <- as.data.frame(read_parquet(opt$mixture))
idx_cols <- names(bulk_df)[names(bulk_df) %in% c("index", "sample_id", "__index_level_0__")]
if (length(idx_cols)) {
  rn <- as.character(bulk_df[[idx_cols[[1]]]])
  bulk_df[[idx_cols[[1]]]] <- NULL
  bulk <- as.matrix(bulk_df)
  rownames(bulk) <- rn
} else {
  bulk <- as.matrix(bulk_df)
}
ct <- as.data.frame(read_parquet(opt$celltypes))
id_col <- intersect(c("cell_id", "index"), names(ct))
if (!length(id_col)) id_col <- names(ct)[1]
ct_labels <- as.character(ct$cell_type)
names(ct_labels) <- as.character(ct[[id_col[[1]]]])
# BayesPrism is happier without spaces
ct_labels <- gsub(" ", "_", ct_labels)

if (nzchar(opt$cellstates) && file.exists(opt$cellstates)) {
  cs <- as.data.frame(read_parquet(opt$cellstates))
  cs_labels <- cs$cell_state
  names(cs_labels) <- cs$cell_id
} else {
  cs_labels <- ct_labels
}

common <- intersect(colnames(sc_ref), colnames(bulk))
sc_ref <- sc_ref[, common, drop = FALSE]
bulk <- bulk[, common, drop = FALSE]

sc_ref <- cleanup.genes(
  input = sc_ref,
  input.type = "count.matrix",
  species = "hs",
  gene.group = c("Rb", "Mrp", "other_Rb", "chrM", "MALAT1", "chrX", "chrY")
)

prism <- new.prism(
  reference = sc_ref,
  mixture = bulk,
  input.type = "count.matrix",
  cell.type.labels = ct_labels[rownames(sc_ref)],
  cell.state.labels = cs_labels[rownames(sc_ref)],
  key = "malignant",
  outlier.cut = 0.01,
  outlier.fraction = 0.1
)

res <- run.prism(prism = prism, n.cores = as.integer(opt$cores))
theta <- get.fraction(res, which.theta = "final", state.or.type = "type")
Z_mal <- get.exp(res, state.or.type = "type", cell.name = "malignant")

write_parquet(as.data.frame(theta), file.path(opt$outdir, "theta.parquet"))
write_parquet(as.data.frame(Z_mal), file.path(opt$outdir, "Z_malignant.parquet"))
writeLines("ok", file.path(opt$outdir, "STATUS.txt"))
