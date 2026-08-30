#!/usr/bin/env Rscript
# CARNIVAL per-sample causal network. Called from NB07 via subprocess.
# Args: --pkn --tf --weights --perturbation --outdir --sample_id --timelimit --solverPath

user_lib <- file.path(
  Sys.getenv("HOME"), "Library", "R",
  paste0(R.version$major, ".", sub("\\..*", "", R.version$minor)),
  "library"
)
if (dir.exists(user_lib)) .libPaths(c(user_lib, .libPaths()))
if (nzchar(Sys.getenv("R_LIBS_USER")) && dir.exists(Sys.getenv("R_LIBS_USER"))) {
  .libPaths(c(Sys.getenv("R_LIBS_USER"), .libPaths()))
}
Sys.setenv(PATH = paste("/opt/homebrew/bin", "/usr/local/bin", Sys.getenv("PATH"), sep = ":"))

args <- commandArgs(trailingOnly = TRUE)
opt <- list(weights = "", perturbation = "", timelimit = "300", solverPath = "")
i <- 1
while (i <= length(args)) {
  key <- substring(args[[i]], 3)
  opt[[key]] <- args[[i + 1]]
  i <- i + 2
}
dir.create(opt$outdir, recursive = TRUE, showWarnings = FALSE)
err_path <- file.path(opt$outdir, paste0(opt$sample_id, ".ERROR.txt"))
json_path <- file.path(opt$outdir, paste0(opt$sample_id, ".json"))

write_json_out <- function(mode, elapsed, res, timed_out) {
  out <- list(
    sample_id = opt$sample_id,
    mode = mode,
    timed_out = timed_out,
    elapsed_sec = elapsed,
    result = res
  )
  write(
    jsonlite::toJSON(out, auto_unbox = TRUE, pretty = TRUE, dataframe = "rows", null = "null"),
    json_path
  )
}

if (!requireNamespace("CARNIVAL", quietly = TRUE) ||
    !requireNamespace("arrow", quietly = TRUE) ||
    !requireNamespace("jsonlite", quietly = TRUE)) {
  writeLines("CARNIVAL/arrow/jsonlite missing. Run: Rscript v3/env/v3_setup.R", err_path)
  quit(status = 1)
}

suppressPackageStartupMessages({
  library(CARNIVAL)
  library(arrow)
  library(jsonlite)
})

cbc <- opt$solverPath
if (!nzchar(cbc)) {
  cbc <- unname(Sys.which("cbc"))
}
if (!nzchar(cbc) || !file.exists(cbc)) {
  for (cand in c("/opt/homebrew/bin/cbc", "/usr/local/bin/cbc")) {
    if (file.exists(cand)) {
      cbc <- cand
      break
    }
  }
}
if (!nzchar(cbc) || !file.exists(cbc)) {
  writeLines("cbc solver binary not found", err_path)
  write_json_out("InvCARNIVAL", 0, list(error = "cbc solver binary not found"), FALSE)
  quit(status = 1)
}

pkn <- as.data.frame(read_parquet(opt$pkn))
need <- c("source", "interaction", "target")
if (!all(need %in% names(pkn))) {
  write_json_out("InvCARNIVAL", 0, list(error = "PKN missing source/interaction/target"), FALSE)
  quit(status = 1)
}
pkn <- pkn[, need, drop = FALSE]
pkn$source <- as.character(pkn$source)
pkn$target <- as.character(pkn$target)
pkn$interaction <- as.integer(as.numeric(as.character(pkn$interaction)))
pkn <- pkn[pkn$interaction %in% c(-1L, 1L), , drop = FALSE]
pkn <- pkn[!is.na(pkn$source) & !is.na(pkn$target), , drop = FALSE]

tf <- as.data.frame(read_parquet(opt$tf))
meas <- suppressWarnings(as.numeric(tf[1, ]))
names(meas) <- colnames(tf)
meas <- meas[is.finite(meas)]
pkn_nodes <- unique(c(pkn$source, pkn$target))
meas <- meas[names(meas) %in% pkn_nodes]
if (length(meas) < 5L) {
  write_json_out(
    "InvCARNIVAL", 0,
    list(error = paste0("fewer than 5 TF measurements in PKN (n=", length(meas), ")")),
    FALSE
  )
  quit(status = 1)
}

weightObj <- NULL
if (nzchar(opt$weights) && file.exists(opt$weights)) {
  w <- as.data.frame(read_parquet(opt$weights))
  weightObj <- as.numeric(w[1, ])
  names(weightObj) <- colnames(w)
  weightObj <- weightObj[names(weightObj) %in% pkn_nodes]
  if (!length(weightObj)) weightObj <- NULL
}

inputObj <- NULL
mode <- "InvCARNIVAL"
if (nzchar(opt$perturbation) && file.exists(opt$perturbation)) {
  p <- as.data.frame(read_parquet(opt$perturbation))
  inputObj <- as.numeric(p[1, ])
  names(inputObj) <- colnames(p)
  inputObj <- inputObj[names(inputObj) %in% pkn_nodes]
  if (length(inputObj)) mode <- "StdCARNIVAL" else inputObj <- NULL
}

work <- file.path(opt$outdir, paste0(".", opt$sample_id, "_work"))
dir.create(work, recursive = TRUE, showWarnings = FALSE)

t0 <- proc.time()[["elapsed"]]
res <- tryCatch({
  runCARNIVAL(
    inputObj = inputObj,
    measObj = meas,
    netObj = pkn,
    weightObj = weightObj,
    solver = "cbc",
    solverPath = cbc,
    timelimit = as.integer(opt$timelimit),
    threads = 1,
    keepLPFiles = FALSE,
    cleanTmpFiles = TRUE,
    dir_name = work
  )
}, error = function(e) list(error = conditionMessage(e)))
elapsed <- proc.time()[["elapsed"]] - t0
timed_out <- isTRUE(elapsed >= as.numeric(opt$timelimit) - 1)
write_json_out(mode, elapsed, res, timed_out)
unlink(work, recursive = TRUE, force = TRUE)
