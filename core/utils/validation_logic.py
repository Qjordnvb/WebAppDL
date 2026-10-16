# core/utils/validation_logic.py
import hashlib
import json
import logging
import re
from typing import Dict, List, Any, Tuple

# Configura un logger para este módulo
logger = logging.getLogger(__name__)

# --- Funciones de Normalización y Limpieza ---


def normalize_string(text: Any) -> Any:
    """
    Normaliza un string para comparaciones consistentes.
    Maneja correctamente caracteres Unicode y secuencias de escape.
    Devuelve el valor original si no es un string.

    Args:
        text: Texto o valor a normalizar

    Returns:
        Texto normalizado o valor original
    """
    if not isinstance(text, str):
        return text
    try:
        # Si ya contiene secuencias Unicode, decodificarlas
        if "\\u" in text:
            # Intenta decodificar unicode_escape, si falla, devuelve original
            try:
                return bytes(text, "utf-8").decode("unicode_escape")
            except Exception:
                logger.warning(
                    f"Fallo al decodificar unicode_escape en: {text}", exc_info=False
                )
                return text  # Devolver original si falla la decodificación específica
        else:
            return text  # Si no hay secuencias \u, devolver tal cual
    except Exception as e:
        logger.error(
            f"Error inesperado normalizando string '{text}': {e}", exc_info=False
        )
        return text  # Devolver original en caso de error inesperado


def clean_string(text: Any) -> Any:
    """
    Limpia un string para comparaciones menos estrictas.
    Elimina espacios, puntuación y convierte a minúsculas.
    Devuelve el valor original si no es un string.

    Args:
        text: Texto o valor a limpiar

    Returns:
        Texto limpio para comparaciones o valor original
    """
    if not isinstance(text, str):
        return text

    # Normalizar primero
    cleaned = normalize_string(text)
    if not isinstance(
        cleaned, str
    ):  # Verificar si la normalización devolvió algo no-string
        return cleaned

    # Eliminar espacios en blanco, puntuación y convertir a minúsculas
    try:
        cleaned = cleaned.lower()
        # Conservar números, letras y espacios. Eliminar otros caracteres.
        cleaned = "".join(c for c in cleaned if c.isalnum() or c.isspace())
        cleaned = " ".join(cleaned.split())  # Normalizar múltiples espacios a uno solo
    except Exception as e:
        logger.error(f"Error limpiando string '{text}': {e}", exc_info=False)
        return text  # Devolver original en caso de error

    return cleaned


# --- Funciones de Comparación y Validación ---


def calculate_match_score(
    captured_dl: Dict[str, Any],
    expected_properties: Dict[str, Any],
    required_fields: List[str] = None,  # Hacer opcional, aunque recomendado
    key_fields_primary: List[str] = None,
    key_fields_secondary: List[str] = None,
    primary_weight: float = 0.60,
    secondary_weight: float = 0.20,
    other_weight: float = 0.20,
) -> Tuple[float, List[str], List[str]]:
    """
    Calcula un score de coincidencia ponderado para un DataLayer capturado
    contra las propiedades esperadas de una referencia. Identifica errores y warnings.

    Args:
        captured_dl: DataLayer capturado.
        expected_properties: Propiedades esperadas del DataLayer de referencia.
        required_fields: Lista de campos requeridos en el DataLayer capturado.
        key_fields_primary: Campos clave primarios para ponderación.
        key_fields_secondary: Campos clave secundarios para ponderación.
        primary_weight: Peso para campos primarios.
        secondary_weight: Peso para campos secundarios.
        other_weight: Peso para otros campos.

    Returns:
        Tuple: (score_final, lista_errores, lista_warnings)
    """
    if required_fields is None:
        required_fields = []  # Valor por defecto si no se provee
    if key_fields_primary is None:
        key_fields_primary = ["event", "event_category", "event_action", "event_label"]
    if key_fields_secondary is None:
        key_fields_secondary = ["component_name"]

    errors = []
    warnings_list = []
    total_expected_props = len(expected_properties)

    if not isinstance(captured_dl, dict):
        return 0.0, ["El DataLayer capturado no es un diccionario válido."], []
    if not expected_properties:
        return 0.0, ["No hay propiedades esperadas definidas en la referencia."], []

    matched_primary, total_primary_in_expected = 0, 0
    matched_secondary, total_secondary_in_expected = 0, 0
    matched_other, total_other_in_expected = 0, 0
    primary_errors, secondary_errors, other_errors = [], [], []

    # --- Comparación campo por campo (Referencia vs Capturado) ---
    for prop, expected_value in expected_properties.items():
        actual_value = captured_dl.get(prop)
        # Considera dinámico si es null o tiene {{...}}
        is_dynamic = expected_value is None or (
            isinstance(expected_value, str)
            and "{{" in expected_value
            and "}}" in expected_value
        )
        is_primary = prop in key_fields_primary
        is_secondary = prop in key_fields_secondary
        field_type_log = "otro"
        if is_primary:
            field_type_log = "clave primario"
        elif is_secondary:
            field_type_log = "clave secundario"

        prop_matched = False
        prop_warning = False

        if prop in captured_dl:
            if not is_dynamic:
                if isinstance(expected_value, str) and isinstance(actual_value, str):
                    norm_expected = normalize_string(expected_value)
                    norm_actual = normalize_string(actual_value)
                    if norm_expected == norm_actual:
                        prop_matched = True
                    else:
                        clean_expected = clean_string(expected_value)
                        clean_actual = clean_string(actual_value)
                        if clean_expected == clean_actual:
                            prop_matched = True
                            prop_warning = True  # Marcar para añadir warning
                        else:
                            # Error de valor fundamental
                            current_error_msg = f"Valor para '{field_type_log} {prop}' no coincide: esperado '{expected_value}', encontrado '{actual_value}'"
                            if is_primary:
                                primary_errors.append(current_error_msg)
                            elif is_secondary:
                                secondary_errors.append(current_error_msg)
                            else:
                                other_errors.append(current_error_msg)
                elif actual_value == expected_value:
                    prop_matched = True
                else:
                    # Error de valor (tipos no string o diferentes)
                    current_error_msg = f"Valor para '{field_type_log} {prop}' no coincide: esperado '{expected_value}', encontrado '{actual_value}'"
                    if is_primary:
                        primary_errors.append(current_error_msg)
                    elif is_secondary:
                        secondary_errors.append(current_error_msg)
                    else:
                        other_errors.append(current_error_msg)
            else:  # Campo dinámico presente
                prop_matched = True

            # Contar para score si hubo match
            if prop_matched:
                if is_primary:
                    matched_primary += 1
                elif is_secondary:
                    matched_secondary += 1
                else:
                    matched_other += 1

        # Añadir WARNING si aplica (independiente de otros errores)
        if prop_warning:
            current_warning_msg = f"Coincidencia sensible a mayúsculas/acentos para '{prop}': esperado '{expected_value}', encontrado '{actual_value}'"
            warnings_list.append(current_warning_msg)

        # Contar totales esperados
        if is_primary:
            total_primary_in_expected += 1
        elif is_secondary:
            total_secondary_in_expected += 1
        else:
            total_other_in_expected += 1

    # --- Verificación de Campos Faltantes y Extras ---
    captured_keys = set(captured_dl.keys())
    expected_keys = set(expected_properties.keys())

    missing_keys = expected_keys - captured_keys
    missing_field_errors = [
        f"Campo '{k}' presente en referencia pero AUSENTE en capturado"
        for k in missing_keys
    ]

    extra_keys = captured_keys - expected_keys
    extra_field_errors = []
    if extra_keys:
        extra_field_errors.append(
            f"Campo(s) extra en capturado no definidos en referencia: {sorted(list(extra_keys))}"
        )

    # --- Combinar Errores ---
    errors.extend(primary_errors)
    errors.extend(secondary_errors)
    errors.extend(other_errors)
    errors.extend(missing_field_errors)
    errors.extend(extra_field_errors)

    # --- Calcular Score Ponderado (basado solo en matches de campos esperados) ---
    primary_score = (
        (matched_primary / total_primary_in_expected)
        if total_primary_in_expected > 0
        else 1.0
    )
    secondary_score = (
        (matched_secondary / total_secondary_in_expected)
        if total_secondary_in_expected > 0
        else 1.0
    )
    other_score = (
        (matched_other / total_other_in_expected)
        if total_other_in_expected > 0
        else 1.0
    )

    # Penalización si 'event' estático no coincide exactamente
    event_prop = "event"
    if event_prop in expected_properties and not (
        expected_properties[event_prop] is None
        or (
            isinstance(expected_properties[event_prop], str)
            and "{{" in expected_properties[event_prop]
        )
    ):
        norm_event_expected = normalize_string(expected_properties[event_prop])
        norm_event_actual = normalize_string(captured_dl.get(event_prop, None))
        if norm_event_expected != norm_event_actual:
            primary_score *= 0.1  # Penalización fuerte

    final_score = (
        (primary_score * primary_weight)
        + (secondary_score * secondary_weight)
        + (other_score * other_weight)
    )
    final_score = min(max(final_score, 0.0), 1.0)  # Asegurar rango [0, 1]

    # Penalización adicional si hay errores primarios y score bajo
    if primary_errors and primary_score < 0.5:
        final_score *= 0.5

    return final_score, errors, warnings_list


def filter_datalayers(
    captured_datalayers: List[Dict[str, Any]],
    event_filter: str = "GAEvent",  # Hacer configurable si es necesario
) -> List[Dict[str, Any]]:
    """
    Filtra los DataLayers capturados para mantener aquellos relevantes.
    Por defecto, mantiene solo diccionarios con event: "GAEvent".

    Args:
       captured_datalayers: Lista de DataLayers capturados.
       event_filter: Valor del campo 'event' para filtrar (default: "GAEvent").

    Returns:
       Lista filtrada de DataLayers relevantes.
    """
    if not captured_datalayers:
        logger.warning("No se recibieron DataLayers para filtrar.")
        return []

    logger.info(
        f"Filtrando {len(captured_datalayers)} DataLayers capturados (filtro event='{event_filter}')..."
    )

    filtered_list = []
    excluded_count = 0
    for dl in captured_datalayers:
        if isinstance(dl, dict) and dl.get("event") == event_filter:
            filtered_list.append(dl)
        else:
            excluded_count += 1

    logger.info(
        f"Filtrado completado: {len(filtered_list)} relevantes restantes. ({excluded_count} excluidos)."
    )
    return filtered_list


def compare_captured_with_reference(
    captured_datalayers: List[Dict[str, Any]],
    schema: Dict[str, Any],
    match_threshold: float = 0.7,
) -> Dict[str, Any]:
    """
    Compara la lista de DataLayers capturados (relevantes) con las referencias del esquema.
    Calcula coincidencias, referencias faltantes y cobertura.

    Args:
        captured_datalayers: Lista de DataLayers capturados y filtrados.
        schema: El esquema de validación completo.
        match_threshold: Umbral de score para considerar una coincidencia.

    Returns:
        Diccionario con los resultados de la comparación.
    """
    comparison_results = {
        "reference_count": 0,
        "captured_count": len(captured_datalayers),  # Total relevantes recibidos
        "matched_count": 0,  # Cuantas referencias únicas tuvieron match
        "missing_count": 0,  # Cuantas referencias únicas NO tuvieron match
        "missing_details": [],
        "coverage_percent": 0.0,
    }

    reference_sections = []
    if schema and "sections" in schema:
        for idx, section in enumerate(schema["sections"]):
            datalayer_section = section.get("datalayer", {})
            properties = datalayer_section.get("properties")
            if properties:
                reference_sections.append(
                    {
                        "properties": properties,
                        "title": section.get("title", f"Sección sin título {idx}"),
                        "id": section.get("id", f"no_id_{idx}"),
                        "required_fields": datalayer_section.get("required_fields", []),
                        "match_found": False,  # Flag para rastrear si esta referencia fue encontrada
                    }
                )

    comparison_results["reference_count"] = len(reference_sections)
    if comparison_results["reference_count"] == 0:
        logger.warning("No hay secciones de referencia en el schema para comparar.")
        return comparison_results  # No hay nada que comparar

    # Iterar sobre los capturados para marcar las referencias encontradas
    for captured_dl in captured_datalayers:
        best_match_ref_idx = -1
        best_match_score = -1.0
        for j, ref_section in enumerate(reference_sections):
            # Solo necesitamos el score para encontrar el mejor match
            score, _, _ = calculate_match_score(
                captured_dl,
                ref_section["properties"],
                ref_section.get("required_fields", []),
            )
            if score > best_match_score:
                best_match_score = score
                best_match_ref_idx = j

        # Si se encontró un match válido para este capturado, marcar la referencia correspondiente
        if best_match_ref_idx != -1 and best_match_score >= match_threshold:
            # Marcar solo la primera vez que se encuentra esta referencia
            if not reference_sections[best_match_ref_idx]["match_found"]:
                reference_sections[best_match_ref_idx]["match_found"] = True

    # Contar referencias encontradas (match_found=True) y faltantes
    final_matched_count = sum(1 for ref in reference_sections if ref["match_found"])
    final_missing_count = comparison_results["reference_count"] - final_matched_count

    comparison_results["matched_count"] = final_matched_count
    comparison_results["missing_count"] = final_missing_count
    comparison_results["missing_details"] = [
        {
            "reference_title": ref["title"],
            "reference_id": ref["id"],
            "properties": ref["properties"],
        }
        for ref in reference_sections
        if not ref["match_found"]
    ]

    # Calcular cobertura basada en referencias únicas encontradas
    if comparison_results["reference_count"] > 0:
        comparison_results["coverage_percent"] = round(
            (final_matched_count / comparison_results["reference_count"]) * 100, 1
        )
    else:
        comparison_results["coverage_percent"] = 0.0

    logger.info(
        f"Resultados comparación: Encontradas={final_matched_count}, Faltantes={final_missing_count}, Cobertura={comparison_results['coverage_percent']}%"
    )
    return comparison_results


def generate_validation_details(
    captured_datalayers: List[
        Dict[str, Any]
    ],  # Lista de DLs capturados (pueden tener _captureTimestamp)
    schema: Dict[str, Any],
    config: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """
    Genera la lista detallada de validación para cada DataLayer capturado.
    Encuentra el mejor match con una referencia, calcula errores/warnings.

    Args:
        captured_datalayers: Lista completa de datalayers capturados (pueden incluir timestamp).
        schema: El esquema de validación.
        config: Configuración (para umbrales, etc.).

    Returns:
        Lista de diccionarios, cada uno representando el detalle de validación de un DL capturado.
    """
    if config is None:
        config = {}

    validation_details = []
    reference_sections = schema.get("sections", [])
    match_threshold = config.get("validation", {}).get("match_threshold", 0.7)
    time_threshold = config.get("validation", {}).get("warning_time_threshold_ms", 500)

    processed_datalayers_unique = []
    seen_datalayers_repr = set()
    logger.info(
        f"Procesando {len(captured_datalayers)} DLs para detalles (deduplicando primero)..."
    )
    # 1. Deduplicación (basada en contenido, ignorando timestamp)
    for dl in captured_datalayers:
        dl_content = (
            {k: v for k, v in dl.items() if k != "_captureTimestamp"}
            if isinstance(dl, dict)
            else dl
        )
        try:
            dl_representation = json.dumps(
                dl_content, sort_keys=True, ensure_ascii=False
            )
            if dl_representation not in seen_datalayers_repr:
                seen_datalayers_repr.add(dl_representation)
                processed_datalayers_unique.append(
                    dl
                )  # Guardar el original con timestamp
        except TypeError:
            logger.warning(
                f"No se pudo serializar DL para deduplicación: {dl}. Se incluirá."
            )
            processed_datalayers_unique.append(dl)
    logger.info(
        f"DLs únicos después de deduplicación: {len(processed_datalayers_unique)}"
    )

    # 2. Filtrado (por defecto, event='GAEvent')
    relevant_datalayers = filter_datalayers(processed_datalayers_unique)
    logger.info(f"DLs relevantes (únicos y filtrados): {len(relevant_datalayers)}")

    # 3. Warnings de Tiempo y Validación Detallada
    previous_timestamp = None
    for i, datalayer_with_ts in enumerate(relevant_datalayers):
        datalayer_content = {
            k: v for k, v in datalayer_with_ts.items() if k != "_captureTimestamp"
        }
        current_timestamp = datalayer_with_ts.get("_captureTimestamp")
        time_warnings = []

        # Calcular warning de tiempo si aplica
        if i > 0 and previous_timestamp and current_timestamp:
            time_diff = current_timestamp - previous_timestamp
            if time_diff < time_threshold:
                warning_msg = f"Evento rápido: Ocurrió {time_diff} ms después del DL anterior (umbral: {time_threshold} ms)."
                time_warnings.append(warning_msg)
        previous_timestamp = current_timestamp

        # Encontrar mejor match y validar
        best_match_section_info = None
        best_match_score = -1.0
        matched_errors = []
        match_warnings = []

        for section in reference_sections:
            expected_properties = section.get("datalayer", {}).get("properties", {})
            required_fields = section.get("datalayer", {}).get("required_fields", [])
            if not expected_properties:
                continue

            score, errors_match, warnings_match = calculate_match_score(
                datalayer_content, expected_properties, required_fields
            )
            if score > best_match_score:
                best_match_score = score
                best_match_section_info = {
                    "title": section.get("title", "Unknown Section"),
                    "properties": expected_properties,
                    "id": section.get("id"),
                }
                matched_errors = errors_match
                match_warnings = warnings_match

        combined_warnings = time_warnings + match_warnings
        detail_is_valid = None  # Puede ser True, False, o None (sin match claro)

        if best_match_score >= match_threshold:
            detail_is_valid = not bool(
                matched_errors
            )  # Válido si no hay errores en el match
        else:
            # No hubo match claro
            warning_msg = f"DataLayer no coincide con ninguna referencia conocida (Mejor score: {best_match_score*100:.1f}%)"
            combined_warnings.append(warning_msg)
            detail_is_valid = None  # Indicar que no hubo match

        # Ordenar referencia para comparación visual
        reference_data_sorted = None
        if best_match_section_info and best_match_score >= match_threshold:
            if isinstance(datalayer_content, dict) and isinstance(
                best_match_section_info["properties"], dict
            ):
                # Crear un nuevo diccionario para las propiedades ordenadas
                sorted_props = {}
                # Incluir primero las claves del capturado en orden
                for key in datalayer_content.keys():
                    if key in best_match_section_info["properties"]:
                        sorted_props[key] = best_match_section_info["properties"][key]
                # Incluir las claves restantes de la referencia
                for key, value in best_match_section_info["properties"].items():
                    if key not in sorted_props:
                        sorted_props[key] = value
                reference_data_sorted = sorted_props
            else:
                reference_data_sorted = best_match_section_info["properties"]

        detail = {
            "datalayer_index": i,  # Índice basado en la lista relevante
            "data": datalayer_content,
            "valid": detail_is_valid,
            "errors": matched_errors if detail_is_valid is False else [],
            "warnings": combined_warnings,
            "source": "capture",  # Indicar fuente genérica
            "matched_section_id": (
                best_match_section_info["id"]
                if best_match_section_info and detail_is_valid is not None
                else None
            ),
            "matched_section": (
                best_match_section_info["title"]
                if best_match_section_info and detail_is_valid is not None
                else None
            ),
            "match_score": best_match_score if best_match_section_info else None,
            "reference_data": reference_data_sorted,
            "_captureTimestamp": current_timestamp,  # Mantener timestamp original si existe
        }
        validation_details.append(detail)

    logger.info(f"Generados {len(validation_details)} detalles de validación.")
    return validation_details


def calculate_summary(
    validation_details: List[Dict[str, Any]], comparison_results: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calcula el resumen final basado en los detalles de validación únicos y la comparación.

    Args:
        validation_details: Lista de detalles de validación generados.
        comparison_results: Resultados de la comparación (para total_sections y missing).

    Returns:
        Diccionario con el resumen final.
    """
    summary = {
        "total_sections": comparison_results.get(
            "reference_count", 0
        ),  # Total de referencias
        "unique_valid_matches": 0,
        "unique_invalid_matches": 0,
        "unique_datalayers_with_warnings": 0,
        "unique_unmatched_datalayers": 0,
        "total_unique_captured_relevant": 0,
        "not_found_sections": comparison_results.get(
            "missing_count", 0
        ),  # Referencias no encontradas
    }

    unique_valid_matches_set = set()
    unique_invalid_matches_set = set()
    unique_warning_items_set = set()
    unique_unmatched_set = set()
    # debug_identifiers = {} # Para depuración

    for detail in validation_details:
        unique_identifier = None
        if detail["matched_section_id"] and detail["valid"] is not None:
            unique_identifier = f"ref_{detail['matched_section_id']}"
        else:  # Sin match claro (valid es None)
            try:
                dl_string = json.dumps(
                    detail["data"], sort_keys=True, ensure_ascii=False
                )
                unique_identifier = (
                    f"dl_{hashlib.sha1(dl_string.encode('utf-8')).hexdigest()[:16]}"
                )
            except Exception as hash_err:
                logger.error(
                    f"Error generando hash para DL {detail['datalayer_index']}: {hash_err}"
                )
                unique_identifier = f"dl_error_{detail['datalayer_index']}"

        # debug_identifiers[detail['datalayer_index']] = unique_identifier

        if detail["valid"] is True:
            unique_valid_matches_set.add(unique_identifier)
        elif detail["valid"] is False:
            unique_invalid_matches_set.add(unique_identifier)
        elif detail["valid"] is None:  # Contar explícitamente los no coincidentes
            unique_unmatched_set.add(unique_identifier)

        if detail.get("warnings"):  # Si la lista de warnings no está vacía
            unique_warning_items_set.add(unique_identifier)

    summary["unique_valid_matches"] = len(unique_valid_matches_set)
    summary["unique_invalid_matches"] = len(unique_invalid_matches_set)
    summary["unique_datalayers_with_warnings"] = len(unique_warning_items_set)
    summary["unique_unmatched_datalayers"] = len(unique_unmatched_set)
    summary["total_unique_captured_relevant"] = len(
        unique_valid_matches_set | unique_invalid_matches_set | unique_unmatched_set
    )

    logger.info(f"Resumen calculado: {summary}")
    return summary
