suppressPackageStartupMessages({
  library(tidyverse)
  library(readxl)
  library(janitor)
  library(stringi)
  library(readr)
})

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || all(is.na(x)) || identical(x, "")) y else x
}

clean_txt <- function(x) {
  x <- as.character(x)
  x <- stringi::stri_trans_general(x, "Latin-ASCII")
  x <- toupper(x)
  stringr::str_squish(x)
}

normalize_ascii <- function(x) {
  stringi::stri_trans_general(as.character(x), "Latin-ASCII")
}

find_project_root <- function() {
  candidatos <- c(".", "..", "../..", "../../..", "../../../..")
  for (cand in candidatos) {
    if (dir.exists(file.path(cand, "insumos")) && dir.exists(file.path(cand, "resultados"))) {
      return(normalizePath(cand, winslash = "/", mustWork = TRUE))
    }
  }
  stop("No se encontro una carpeta 'insumos' y 'resultados' en los directorios superiores.")
}

normalize_input_path <- function(path, base_dir = NULL, must_work = TRUE) {
  if (is.null(path) || path == "") return(NULL)
  candidate <- if (is.null(base_dir) || grepl("^[A-Za-z]:|^/", path)) path else file.path(base_dir, path)
  normalizePath(candidate, winslash = "/", mustWork = must_work)
}

latest_path_by_pattern <- function(base_dir, pattern, type = c("file", "dir"), recursive = FALSE,
                                   extensions = NULL, required = TRUE) {
  type <- match.arg(type)
  base_dir <- normalize_input_path(base_dir)

  paths <- if (type == "file") {
    list.files(base_dir, recursive = recursive, full.names = TRUE, all.files = FALSE)
  } else {
    list.dirs(base_dir, recursive = recursive, full.names = TRUE)
  }

  if (type == "file") {
    info <- file.info(paths)
    paths <- paths[!is.na(info$isdir) & !info$isdir]
    if (!is.null(extensions)) {
      ext <- tolower(tools::file_ext(paths))
      paths <- paths[ext %in% tolower(extensions)]
    }
  } else {
    paths <- paths[normalizePath(paths, winslash = "/", mustWork = FALSE) != base_dir]
  }

  if (!length(paths)) {
    if (required) stop("No hay rutas candidatas en: ", base_dir)
    return(NULL)
  }

  pattern_ascii <- normalize_ascii(pattern)
  names_ascii <- normalize_ascii(basename(paths))
  hits <- paths[stringr::str_detect(names_ascii, stringr::regex(pattern_ascii, ignore_case = TRUE))]

  if (!length(hits)) {
    if (required) stop("No se encontro coincidencia para el patron '", pattern, "' en: ", base_dir)
    return(NULL)
  }

  hits[which.max(file.info(hits)$mtime)]
}

resolve_sheet <- function(path, requested_sheet = NULL) {
  sheets <- readxl::excel_sheets(path)
  if (is.null(requested_sheet) || requested_sheet == "") return(sheets[[1]])
  if (requested_sheet %in% sheets) return(requested_sheet)

  requested_ascii <- normalize_ascii(requested_sheet)
  sheets_ascii <- normalize_ascii(sheets)
  hit <- sheets[stringr::str_detect(sheets_ascii, stringr::regex(requested_ascii, ignore_case = TRUE))]
  if (length(hit)) return(hit[[1]])

  warning("No se encontro la hoja '", requested_sheet, "' en ", basename(path), ". Se usara: ", sheets[[1]])
  sheets[[1]]
}

ensure_columns <- function(.data, columns) {
  for (col in columns) {
    if (!col %in% names(.data)) .data[[col]] <- NA_character_
  }
  .data
}

standardize_master_names <- function(.data) {
  if (!"departameto" %in% names(.data) && "departamento" %in% names(.data)) {
    .data <- dplyr::rename(.data, departameto = departamento)
  }
  if (!"nombre_local" %in% names(.data) && "nombre_del_local" %in% names(.data)) {
    .data <- dplyr::rename(.data, nombre_local = nombre_del_local)
  }
  if (!"nombre_local" %in% names(.data) && "nombre_lv" %in% names(.data)) {
    .data <- dplyr::rename(.data, nombre_local = nombre_lv)
  }
  if (!"direccion" %in% names(.data) && "direccion_del_local" %in% names(.data)) {
    .data <- dplyr::rename(.data, direccion = direccion_del_local)
  }
  if (!"direccion" %in% names(.data) && "direccion_lv" %in% names(.data)) {
    .data <- dplyr::rename(.data, direccion = direccion_lv)
  }
  if (!"id_local" %in% names(.data) && "id_lv" %in% names(.data)) {
    .data <- dplyr::rename(.data, id_local = id_lv)
  }
  if (!"numero_de_mesa" %in% names(.data) && "mesa_de_sufragio" %in% names(.data)) {
    .data <- dplyr::rename(.data, numero_de_mesa = mesa_de_sufragio)
  }
  if (!"electores" %in% names(.data) && "total_electores" %in% names(.data)) {
    .data <- dplyr::rename(.data, electores = total_electores)
  }
  if (!"distrito_centro_computo" %in% names(.data) && "distrito_centro_de_computo" %in% names(.data)) {
    .data <- dplyr::rename(.data, distrito_centro_computo = distrito_centro_de_computo)
  }
  .data
}

read_locales_base <- function(path, sheet = NULL, skip = 10) {
  sheet <- resolve_sheet(path, sheet)
  readxl::read_excel(path, sheet = sheet, skip = skip) |>
    janitor::clean_names() |>
    standardize_master_names() |>
    mutate(across(any_of(c(
      "ubigeo", "departameto", "provincia", "distrito", "id_local",
      "nombre_local", "direccion", "numero_de_mesa",
      "odpe", "nombre_odpe", "sede_de_odpe", "ubigeo_centro_de_computo",
      "distrito_centro_computo", "dpto_continente", "provincia_pais",
      "distrito_ciudad", "tipo_tecnologia", "vraem_1", "ext",
      "modalidad", "ccpp"
    )), clean_txt))
}

read_result_mesas <- function(path, eleccion) {
  wanted <- c(
    "tipo_de_eleccion", "ambito", "region_continente", "provincia_pais",
    "distrito_ciudad", "centro_poblado", "local_de_votacion",
    "numero_de_mesa", "estado_del_acta", "tipo_de_observacion", "electores_habiles"
  )

  readr::read_csv(
    path,
    show_col_types = FALSE,
    col_types = readr::cols(.default = readr::col_character())
  ) |>
    janitor::clean_names() |>
    ensure_columns(wanted) |>
    select(all_of(wanted)) |>
    mutate(
      eleccion = eleccion,
      source_file = basename(path),
      across(all_of(wanted), clean_txt),
      electores_habiles_num = readr::parse_number(electores_habiles)
    ) |>
    distinct(region_continente, provincia_pais, distrito_ciudad, local_de_votacion, numero_de_mesa, .keep_all = TRUE)
}

read_result_spec <- function(spec, insumos_dir) {
  eleccion <- spec$eleccion %||% "Eleccion"
  source_type <- spec$source_type %||% "csv"
  pattern <- spec$pattern %||% eleccion
  recursive <- isTRUE(spec$recursive)

  if (source_type == "csv") {
    path <- spec$path %||% latest_path_by_pattern(insumos_dir, pattern, type = "file", extensions = "csv")
    path <- normalize_input_path(path, insumos_dir)
    return(read_result_mesas(path, eleccion))
  }

  if (source_type == "csvs") {
    base_dir <- normalize_input_path(spec$path %||% insumos_dir, insumos_dir)
    paths <- list.files(base_dir, recursive = recursive, full.names = TRUE, pattern = "[.]csv$")
    names_ascii <- normalize_ascii(basename(paths))
    pattern_ascii <- normalize_ascii(pattern)
    paths <- paths[stringr::str_detect(names_ascii, stringr::regex(pattern_ascii, ignore_case = TRUE))]
    if (!length(paths)) stop("No se encontraron CSV para el patron '", pattern, "' en: ", base_dir)
    return(purrr::map_dfr(paths, read_result_mesas, eleccion = eleccion))
  }

  if (source_type == "dir_csvs") {
    dir_path <- spec$path %||% latest_path_by_pattern(insumos_dir, pattern, type = "dir")
    dir_path <- normalize_input_path(dir_path, insumos_dir)
    paths <- list.files(dir_path, recursive = TRUE, full.names = TRUE, pattern = "[.]csv$")
    if (!length(paths)) stop("La carpeta no contiene CSV: ", dir_path)
    return(purrr::map_dfr(paths, read_result_mesas, eleccion = eleccion))
  }

  stop("source_type no reconocido: ", source_type)
}

default_result_specs <- function() {
  list(
    list(eleccion = "Presidencial", pattern = "Presidencial", source_type = "csv"),
    list(eleccion = "Senadores distrito unico", pattern = "Senadores Distrito Electoral Unico", source_type = "csv"),
    list(eleccion = "Senadores distrito multiple", pattern = "Senadores Distrito Electoral Multiple", source_type = "dir_csvs")
  )
}

run_onpe_odpe_cruce <- function(project_dir = NULL,
                                insumos_dir = NULL,
                                maestras_dir = NULL,
                                salidas_dir = NULL,
                                result_specs = NULL,
                                locales_mesas_file = NULL,
                                locales_mesas_pattern = "LocalesMesasElectores.*EG2026",
                                locales_mesas_sheet = "Mesas Locales EG2026",
                                locales_mesas_skip = 10,
                                odpe_file = NULL,
                                odpe_pattern = "FINAL.*LOCALES.*VOTACION.*EG 2026",
                                odpe_sheet = "LOCALES",
                                odpe_skip = 10) {
  project_dir <- normalize_input_path(project_dir %||% find_project_root())
  insumos_dir <- normalize_input_path(insumos_dir %||% file.path(project_dir, "insumos"))
  maestras_dir <- normalize_input_path(maestras_dir %||% insumos_dir)
  salidas_dir <- normalize_input_path(salidas_dir %||% file.path(project_dir, "resultados", "salidas"), must_work = FALSE)
  dir.create(salidas_dir, recursive = TRUE, showWarnings = FALSE)

  result_specs <- result_specs %||% default_result_specs()

  locales_mesas_file <- locales_mesas_file %||%
    latest_path_by_pattern(maestras_dir, locales_mesas_pattern, type = "file", extensions = c("xlsx", "xls"))
  odpe_file <- odpe_file %||%
    latest_path_by_pattern(maestras_dir, odpe_pattern, type = "file", extensions = c("xlsx", "xls"))

  locales_mesas_file <- normalize_input_path(locales_mesas_file, maestras_dir)
  odpe_file <- normalize_input_path(odpe_file, maestras_dir)

  resultados_mesas <- purrr::map_dfr(result_specs, read_result_spec, insumos_dir = insumos_dir) |>
    mutate(
      mesa_key = str_c(region_continente, provincia_pais, distrito_ciudad, local_de_votacion, numero_de_mesa, sep = " | ")
    )

  locales_mesas <- read_locales_base(locales_mesas_file, locales_mesas_sheet, skip = locales_mesas_skip) |>
    ensure_columns(c(
      "ubigeo", "departameto", "provincia", "distrito", "id_local", "nombre_local",
      "direccion", "numero_de_mesa", "electores", "odpe", "nombre_odpe",
      "sede_de_odpe", "tipo_tecnologia"
    )) |>
    filter(!is.na(id_local), id_local != "") |>
    distinct(ubigeo, departameto, provincia, distrito, id_local, nombre_local, direccion, numero_de_mesa, .keep_all = TRUE) |>
    mutate(
      odpe = if_else(is.na(odpe) | odpe == "", nombre_odpe, odpe),
      electores_mesa = readr::parse_number(as.character(electores)),
      mesa_key = str_c(departameto, provincia, distrito, nombre_local, numero_de_mesa, sep = " | ")
    )

  odpe_base <- read_locales_base(odpe_file, odpe_sheet, skip = odpe_skip) |>
    ensure_columns(c(
      "id_local", "odpe", "nombre_odpe", "sede_de_odpe", "ubigeo_centro_de_computo",
      "distrito_centro_computo", "dpto_continente", "provincia_pais", "distrito_ciudad",
      "mesas", "electores", "tipo_tecnologia", "vraem_1", "ext"
    )) |>
    filter(!is.na(id_local), id_local != "") |>
    mutate(odpe = if_else(is.na(odpe) | odpe == "", nombre_odpe, odpe)) |>
    distinct(id_local, .keep_all = TRUE) |>
    transmute(
      id_local,
      odpe,
      nombre_odpe,
      sede_de_odpe,
      ubigeo_centro_de_computo,
      distrito_centro_computo,
      dpto_continente,
      provincia_pais,
      distrito_ciudad,
      mesas,
      electores_local = readr::parse_number(as.character(electores)),
      tipo_tecnologia,
      vraem_1,
      ext
    )

  locales_odpe <- locales_mesas |>
    left_join(odpe_base, by = "id_local", suffix = c("_mesa", "_odpe")) |>
    mutate(
      odpe = dplyr::coalesce(na_if(odpe_odpe, ""), na_if(odpe_mesa, "")),
      nombre_odpe = dplyr::coalesce(na_if(nombre_odpe_odpe, ""), na_if(nombre_odpe_mesa, "")),
      sede_de_odpe = dplyr::coalesce(na_if(sede_de_odpe_odpe, ""), na_if(sede_de_odpe_mesa, "")),
      tipo_tecnologia = dplyr::coalesce(na_if(tipo_tecnologia_odpe, ""), na_if(tipo_tecnologia_mesa, ""))
    )

  canon_departamento_odpe <- locales_odpe |>
    filter(!is.na(odpe), odpe != "") |>
    mutate(
      departameto_canon = case_when(
        nombre_odpe == "LIMA CENTRO 1" ~ "LIMA",
        departameto %in% c("AFRICA", "AMERICA", "ASIA", "EUROPA", "OCEANIA") ~ "LIMA",
        TRUE ~ departameto
      )
    ) |>
    group_by(odpe, nombre_odpe) |>
    summarise(
      departameto = first(na.omit(departameto_canon)),
      .groups = "drop"
    )

  resultados_enriquecidos <- resultados_mesas |>
    left_join(
      locales_odpe |>
        select(
          departameto, provincia, distrito, id_local, nombre_local, direccion,
          numero_de_mesa, odpe, nombre_odpe, sede_de_odpe, electores_mesa, tipo_tecnologia
        ),
      by = c(
        "region_continente" = "departameto",
        "provincia_pais" = "provincia",
        "distrito_ciudad" = "distrito",
        "local_de_votacion" = "nombre_local",
        "numero_de_mesa" = "numero_de_mesa"
      )
    )

  diagnostico_cruce <- resultados_enriquecidos |>
    group_by(eleccion) |>
    summarise(
      total_mesas_onpe = n_distinct(mesa_key),
      mesas_cruzadas_con_odpe = n_distinct(mesa_key[!is.na(odpe)]),
      tasa_cruce_odpe = mesas_cruzadas_con_odpe / total_mesas_onpe,
      .groups = "drop"
    )

  mesas_sin_odpe <- resultados_enriquecidos |>
    filter(is.na(odpe)) |>
    distinct(eleccion, region_continente, provincia_pais, distrito_ciudad, local_de_votacion, numero_de_mesa, mesa_key)

  resumen_departamento_odpe <- resultados_enriquecidos |>
    filter(!is.na(odpe)) |>
    group_by(eleccion, odpe, nombre_odpe) |>
    summarise(
      mesas_procesadas = n_distinct(mesa_key),
      mesas_contabilizadas = n_distinct(mesa_key[estado_del_acta == "CONTABILIZADA"]),
      mesas_al_jee = n_distinct(mesa_key[estado_del_acta == "PARA ENVIO AL JEE"]),
      electores_procesados = sum(electores_habiles_num, na.rm = TRUE),
      electores_contabilizados = sum(electores_habiles_num[estado_del_acta == "CONTABILIZADA"], na.rm = TRUE),
      electores_al_jee = sum(electores_habiles_num[estado_del_acta == "PARA ENVIO AL JEE"], na.rm = TRUE),
      .groups = "drop"
    ) |>
    left_join(
      locales_odpe |>
        filter(!is.na(odpe)) |>
        group_by(odpe, nombre_odpe) |>
        summarise(
          mesas_totales = n_distinct(mesa_key),
          electores_totales = sum(electores_mesa, na.rm = TRUE),
          .groups = "drop"
        ),
      by = c("odpe", "nombre_odpe")
    ) |>
    left_join(
      canon_departamento_odpe,
      by = c("odpe", "nombre_odpe")
    ) |>
    mutate(
      pct_mesas = mesas_procesadas / mesas_totales,
      pct_mesas_contabilizadas = mesas_contabilizadas / mesas_totales,
      pct_mesas_al_jee = mesas_al_jee / mesas_totales,
      pct_electores = electores_procesados / electores_totales,
      pct_electores_contabilizados = electores_contabilizados / electores_totales,
      electores_por_contabilizar = electores_totales - electores_contabilizados,
      pct_electores_por_contabilizar = electores_por_contabilizar / electores_totales
    ) |>
    arrange(eleccion, departameto, odpe)

  resumen_departamento <- resumen_departamento_odpe |>
    group_by(eleccion, departameto) |>
    summarise(
      mesas_procesadas = sum(mesas_procesadas, na.rm = TRUE),
      mesas_contabilizadas = sum(mesas_contabilizadas, na.rm = TRUE),
      mesas_al_jee = sum(mesas_al_jee, na.rm = TRUE),
      mesas_totales = sum(mesas_totales, na.rm = TRUE),
      electores_procesados = sum(electores_procesados, na.rm = TRUE),
      electores_contabilizados = sum(electores_contabilizados, na.rm = TRUE),
      electores_al_jee = sum(electores_al_jee, na.rm = TRUE),
      electores_totales = sum(electores_totales, na.rm = TRUE),
      .groups = "drop"
    ) |>
    mutate(
    pct_mesas = mesas_procesadas / mesas_totales,
    pct_mesas_contabilizadas = mesas_contabilizadas / mesas_totales,
    pct_mesas_al_jee = mesas_al_jee / mesas_totales,
    pct_electores = electores_procesados / electores_totales,
    pct_electores_contabilizados = electores_contabilizados / electores_totales,
    electores_por_contabilizar = electores_totales - electores_contabilizados,
    pct_electores_por_contabilizar = electores_por_contabilizar / electores_totales
  ) |>
    arrange(eleccion, desc(pct_mesas))

  readr::write_csv(resultados_enriquecidos, file.path(salidas_dir, "onpe_mesas_enriquecidas.csv"))
  readr::write_csv(diagnostico_cruce, file.path(salidas_dir, "diagnostico_cruce_odpe.csv"))
  readr::write_csv(mesas_sin_odpe, file.path(salidas_dir, "mesas_sin_odpe.csv"))
  readr::write_csv(resumen_departamento_odpe, file.path(salidas_dir, "resumen_departamento_odpe.csv"))
  readr::write_csv(resumen_departamento, file.path(salidas_dir, "resumen_departamento.csv"))

  cat("Cruce terminado.\n")
  print(diagnostico_cruce)
  cat("\nInsumos ONPE:", insumos_dir, "\n")
  cat("Maestras:", maestras_dir, "\n")
  cat("Archivos escritos en:", salidas_dir, "\n")

  invisible(list(
    resultados_enriquecidos = resultados_enriquecidos,
    diagnostico_cruce = diagnostico_cruce,
    mesas_sin_odpe = mesas_sin_odpe,
    resumen_departamento_odpe = resumen_departamento_odpe,
    resumen_departamento = resumen_departamento,
    salidas_dir = salidas_dir
  ))
}
