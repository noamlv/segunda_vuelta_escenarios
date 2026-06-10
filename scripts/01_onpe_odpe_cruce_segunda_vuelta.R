find_project_root <- function() {
  candidatos <- c(".", "..", "../..", "../../..", "../../../..")
  for (cand in candidatos) {
    if (dir.exists(file.path(cand, "insumos")) && dir.exists(file.path(cand, "resultados"))) {
      return(normalizePath(cand, winslash = "/", mustWork = TRUE))
    }
  }
  stop("No se encontro una carpeta 'insumos' y 'resultados' en los directorios superiores.")
}

project_dir <- find_project_root()

find_analysis_file <- function(filename) {
  candidatos <- c(
    file.path(getwd(), filename),
    list.files(file.path(project_dir, "resultados"), pattern = filename, recursive = TRUE, full.names = TRUE)
  )
  candidatos <- candidatos[file.exists(candidatos)]
  if (!length(candidatos)) stop("No se encontro el archivo: ", filename)
  normalizePath(candidatos[[1]], winslash = "/", mustWork = TRUE)
}

source(find_analysis_file("01_onpe_odpe_cruce_reutilizable.R"))

find_default_sv_dir <- function() {
  candidatos <- c(
    file.path(getwd(), "Segunda vuelta ODPE"),
    file.path(project_dir, "insumos_segunda_vuelta")
  )
  candidatos <- c(
    candidatos,
    list.dirs(file.path(project_dir, "resultados"), recursive = TRUE, full.names = TRUE)
  )
  candidatos <- candidatos[dir.exists(candidatos)]
  nombres <- normalize_ascii(basename(candidatos))
  hit <- candidatos[grepl("SEGUNDA VUELTA ODPE|INSUMOS_SEGUNDA_VUELTA", toupper(nombres))]
  if (length(hit)) normalizePath(hit[[1]], winslash = "/", mustWork = TRUE) else file.path(project_dir, "insumos")
}

find_default_csv_dir <- function(root_dir) {
  preferred <- file.path(root_dir, "insumos", "descargas_modulo")
  if (dir.exists(preferred) && length(list.files(preferred, pattern = "[.]csv$", full.names = TRUE))) {
    return(normalizePath(preferred, winslash = "/", mustWork = TRUE))
  }

  candidatos <- c(root_dir, list.dirs(root_dir, recursive = TRUE, full.names = TRUE))
  candidatos <- candidatos[dir.exists(candidatos)]
  con_csv <- candidatos[lengths(lapply(candidatos, function(x) {
    list.files(x, pattern = "[.]csv$", full.names = TRUE)
  })) > 0]

  if (!length(con_csv)) return(root_dir)

  nombres <- normalize_ascii(basename(con_csv))
  hit <- con_csv[grepl("DESCARGAS.*MODULO|DESCARGAS_MODULO", toupper(nombres))]
  if (length(hit)) normalizePath(hit[[1]], winslash = "/", mustWork = TRUE) else
    normalizePath(con_csv[[1]], winslash = "/", mustWork = TRUE)
}

default_sv_root <- find_default_sv_dir()
default_sv_insumos <- find_default_csv_dir(default_sv_root)
insumos_dir <- Sys.getenv(
  "ONPE_SV_INSUMOS_DIR",
  default_sv_insumos
)

preferred_master_dir <- file.path(default_sv_root, "insumos", "maestras")
default_master_dir <- if (dir.exists(preferred_master_dir) && length(list.files(preferred_master_dir, pattern = "[.]xlsx?$", full.names = TRUE))) {
  preferred_master_dir
} else if (length(list.files(default_sv_root, pattern = "[.]xlsx?$", full.names = TRUE))) {
  default_sv_root
} else if (length(list.files(insumos_dir, pattern = "[.]xlsx?$", full.names = TRUE))) {
  insumos_dir
} else {
  file.path(project_dir, "insumos")
}

maestras_dir <- Sys.getenv("ONPE_SV_MAESTRAS_DIR", default_master_dir)
salidas_dir <- Sys.getenv("ONPE_SV_SALIDAS_DIR", file.path(default_sv_root, "salidas"))

result_specs <- list(
  list(
    eleccion = Sys.getenv("ONPE_SV_ELECCION_LABEL", "Presidencial segunda vuelta"),
    pattern = Sys.getenv("ONPE_SV_PRES_PATTERN", "Presidencial"),
    source_type = "csv"
  )
)

run_onpe_odpe_cruce(
  project_dir = project_dir,
  insumos_dir = insumos_dir,
  maestras_dir = maestras_dir,
  salidas_dir = salidas_dir,
  result_specs = result_specs,
  locales_mesas_file = Sys.getenv("ONPE_SV_LOCALES_MESAS_FILE", ""),
  locales_mesas_pattern = Sys.getenv("ONPE_SV_LOCALES_MESAS_PATTERN", "Mesa por Mesa.*SEP2026"),
  locales_mesas_sheet = Sys.getenv("ONPE_SV_LOCALES_MESAS_SHEET", "Sheet 1"),
  locales_mesas_skip = as.integer(Sys.getenv("ONPE_SV_LOCALES_MESAS_SKIP", "10")),
  odpe_file = Sys.getenv("ONPE_SV_ODPE_FILE", ""),
  odpe_pattern = Sys.getenv("ONPE_SV_ODPE_PATTERN", "Mesa por Mesa.*SEP2026"),
  odpe_sheet = Sys.getenv("ONPE_SV_ODPE_SHEET", "Sheet 1"),
  odpe_skip = as.integer(Sys.getenv("ONPE_SV_ODPE_SKIP", "10"))
)
