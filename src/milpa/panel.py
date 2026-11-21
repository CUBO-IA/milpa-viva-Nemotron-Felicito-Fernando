"""Descarga del dataset de personas y construcción del panel de agricultores."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from milpa.config import ROOT

COLUMNAS_DOC = ["department", "education_level", "area", "sex"]

NOMBRES_F = [
    "María", "Ana", "Rosa", "Carmen", "Gloria", "Marta", "Blanca", "Sonia",
    "Reina", "Dolores", "Elena", "Silvia", "Juana", "Teresa", "Patricia",
    "Sandra", "Claudia", "Morena", "Esperanza", "Mirna",
]
NOMBRES_M = [
    "José", "Juan", "Carlos", "Luis", "Francisco", "Manuel", "Miguel", "Pedro",
    "Antonio", "Santos", "Mario", "Jorge", "Oscar", "Roberto", "Julio",
    "Salvador", "Ricardo", "Rafael", "Ernesto", "Wilfredo",
]
APELLIDOS = [
    "Hernández", "López", "Martínez", "García", "Rodríguez", "Pérez",
    "Ramírez", "Flores", "Rivera", "Cruz", "Gómez", "Alvarado", "Portillo",
    "Mejía", "Romero", "Aguilar", "Ventura", "Guevara", "Chávez", "Argueta",
]


def ruta(rel: str) -> Path:
    """Resuelve una ruta relativa a la raíz del proyecto."""
    return ROOT / rel


# --- Descarga y documentación ------------------------------------------------


def descargar_personas(cfg: dict[str, Any], force: bool = False) -> pd.DataFrame:
    """Descarga el split configurado a parquet si no existe y lo devuelve."""
    destino = ruta(cfg["data"]["raw_parquet"])
    if destino.exists() and not force:
        return pd.read_parquet(destino)
    from datasets import load_dataset

    ds = load_dataset(cfg["data"]["dataset"], split=cfg["data"]["split"])
    df = ds.to_pandas()
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(destino, index=False)
    return df


def escribir_ocupaciones(df: pd.DataFrame, destino: Path) -> None:
    """Escribe value_counts de occupation (conteo y ocupación por línea)."""
    vc = df["occupation"].fillna("(vacío)").value_counts()
    lineas = [f"{n}\t{occ}" for occ, n in vc.items()]
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def escribir_columnas(df: pd.DataFrame, destino: Path) -> None:
    """Escribe los valores únicos (con conteo) de las columnas clave."""
    bloques = []
    for col in COLUMNAS_DOC:
        vc = df[col].fillna("(vacío)").value_counts().sort_index()
        filas = "\n".join(f"  {n}\t{v}" for v, n in vc.items())
        bloques.append(f"## {col}\n{filas}")
    destino.write_text("\n\n".join(bloques) + "\n", encoding="utf-8")


# --- Filtros ------------------------------------------------------------------


def _coincide(serie: pd.Series, patron: str) -> pd.Series:
    """Máscara booleana de coincidencia de regex (sin advertencias por grupos)."""
    rx = re.compile(patron)
    return serie.fillna("").map(lambda s: bool(rx.search(s)))


def filtrar_principal(df: pd.DataFrame, pcfg: dict[str, Any]) -> pd.DataFrame:
    """Personas cuya ocupación coincide con el regex agrícola principal."""
    return df[_coincide(df["occupation"], pcfg["regex_agricola"])].copy()


def filtrar_ampliacion(df: pd.DataFrame, pcfg: dict[str, Any]) -> pd.DataFrame:
    """Personas de la ampliación configurada (ocupación + área)."""
    amp = pcfg["ampliacion"]
    mask = _coincide(df["occupation"], amp["regex"]) & (df["area"] == amp["area"])
    return df[mask].copy()


def excluir_contratados(
    df: pd.DataFrame, pcfg: dict[str, Any]
) -> tuple[pd.DataFrame, pd.Series]:
    """Quita trabajadores contratados sin parcela propia.

    Devuelve el DataFrame filtrado y el conteo de excluidos por departamento.
    """
    mask = df["professional_persona"].map(
        lambda t: es_contratado(t, pcfg["exclusion_contratados"])
    )
    return df[~mask].copy(), df.loc[mask, "department"].value_counts()


# --- Derivaciones -------------------------------------------------------------


def _hash_int(*partes: object) -> int:
    """Entero determinista a partir de las partes dadas (sha256)."""
    texto = ":".join(str(p) for p in partes)
    return int(hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16], 16)


def cultivo_de(occupation: str, cultivos: dict[str, str], defecto: str) -> str:
    """Primer cultivo cuyo patrón coincide con la ocupación."""
    for nombre, patron in cultivos.items():
        if re.search(patron, occupation or ""):
            return nombre
    return defecto


def zona_de(depto: str, zonas: dict[str, list[str]]) -> str:
    """Zona geográfica del departamento."""
    for zona, deptos in zonas.items():
        if depto in deptos:
            return zona
    return "Desconocida"


def banda_edad(edad: int, bandas: dict[str, list[int]]) -> str:
    """Banda de edad según los rangos inclusivos configurados."""
    for nombre, (lo, hi) in bandas.items():
        if lo <= edad <= hi:
            return nombre
    return "fuera_de_rango"


def nivel_escolar(nivel: str, grupos: dict[str, list[str]]) -> str:
    """Escolaridad agrupada en tres niveles."""
    for grupo, valores in grupos.items():
        if nivel in valores:
            return grupo
    return "basica"


NUMEROS = {
    "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "quince": 15, "veinte": 20, "treinta": 30, "cincuenta": 50,
}
RX_MANZANAS = re.compile(r"\b(\d+|" + "|".join(NUMEROS) + r") manzanas?\b", re.IGNORECASE)


def normalizar(texto: str | None) -> str:
    """Reemplaza espacios no separables por espacios normales."""
    return re.sub(r"[   ]", " ", texto or "")


def _compilar(patrones: list[str]) -> list[re.Pattern[str]]:
    """Compila una lista de regex sin distinguir mayúsculas."""
    return [re.compile(p, re.IGNORECASE) for p in patrones]


RX_ASPIRACION = re.compile(
    r"\b(sueña|soñando|planea|quiere|quisiera|desea|espera|aspira|piensa|"
    r"a futuro|le gustaría|su meta|su objetivo|su sueño|algún día)\b[^.;]*$",
    re.IGNORECASE,
)


def _primera(
    patrones: list[re.Pattern[str]], texto: str, real: bool = False
) -> str | None:
    """Texto de la primera coincidencia entre los patrones, o None.

    Con real=True se ignoran coincidencias en frases aspiracionales
    ("sueña con vender…", "planea abrir…").
    """
    for p in patrones:
        for m in p.finditer(texto):
            if real and RX_ASPIRACION.search(texto[: m.start()]):
                continue
            return m.group(0)
    return None


def _manzanas_grandes(texto: str, minimo: int) -> str | None:
    """Coincidencia 'N manzanas' con N >= minimo, o None."""
    for m in RX_MANZANAS.finditer(texto):
        valor = m.group(1).lower()
        n = int(valor) if valor.isdigit() else NUMEROS.get(valor, 0)
        if n >= minimo:
            return m.group(0)
    return None


def escala_de(texto: str, ecfg: dict[str, Any], cultivo: str = "") -> tuple[str, str]:
    """Escala y señal que la decide: mediano > pequeño > subsistencia.

    Sin ninguna señal se usa el defecto del cultivo (`defecto_por_cultivo`)
    o, si no está listado, `defecto`.
    """
    t = normalizar(texto)
    senal = _manzanas_grandes(t, ecfg["manzanas_mediano"]) or _primera(
        _compilar(ecfg["mediano"]), t, real=True
    )
    if senal:
        return "mediano", senal
    for escala in ("pequeño", "subsistencia"):
        senal = _primera(_compilar(ecfg[escala]), t, real=True)
        if senal:
            return escala, senal
    defecto = ecfg.get("defecto_por_cultivo", {}).get(cultivo, ecfg.get("defecto", "subsistencia"))
    return defecto, "(sin señal de venta)"


def es_contratado(texto: str, xcfg: dict[str, list[str]]) -> bool:
    """True si el texto indica trabajo asalariado sin parcela propia."""
    t = normalizar(texto)
    return bool(_primera(_compilar(xcfg["contratado"]), t)) and not _primera(
        _compilar(xcfg["cuenta_propia"]), t
    )


# --- Nombres ------------------------------------------------------------------

_TOKEN = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+"
RX_NOMBRE_EDAD = re.compile(
    rf"\b({_TOKEN}(?: (?:de )?{_TOKEN}){{0,3}}),? (?:de |tiene |con )?\d{{1,3}} años"
)
RX_TOKEN = re.compile(rf"\b{_TOKEN}\b")
RX_PREFIJO_LUGAR = re.compile(r"\b(San|Santa|Santo|La|El|Los|Las)\s$")
NO_NOMBRES = set(
    """A Al Ante Antes Aunque Bajo Cada Como Comenzó Con Cuando De Del Desde
    Después Don Doña Durante El Ella Empezó En Entre Es Esta Este Gracias Ha
    Hace Hoy Inició La Las Le Lleva Lo Los Mientras Nació Norte Oeste Para Pero
    Pese Por Se Si Siempre Sin Sobre Su Sus Sur Centro También Tras Un Una Vos
    Ya Además Allí Ahí Cultivo Cría Desde Tiene Trabaja Agricultor Agricultora
    Salvador Santa San Junto Nunca Todo Toda Todos Primero Luego Hoy Cuenta""".split()
)


def _es_nombre(token: str, lugares: set[str]) -> bool:
    """True si el token puede ser un nombre propio de persona."""
    return token not in NO_NOMBRES and token not in lugares


def extraer_nombre(textos: list[str], lugares: set[str]) -> str | None:
    """Nombre propio de la persona a partir de sus textos, o None.

    1) Patrón 'Nombre, de N años' (o 'Nombre tiene N años').
    2) Token capitalizado más repetido entre los textos que no sea lugar ni
       palabra común (mínimo dos apariciones).
    """
    textos = [normalizar(t) for t in textos]
    for texto in textos:
        for m in RX_NOMBRE_EDAD.finditer(texto):
            if RX_PREFIJO_LUGAR.search(texto[: m.start()]):
                continue
            tokens = m.group(1).split()
            while tokens and tokens[0] in NO_NOMBRES:
                tokens.pop(0)
            if tokens and tokens[0] != "de":
                return " ".join(tokens)
    conteo: dict[str, int] = {}
    for texto in textos:
        for m in RX_TOKEN.finditer(texto):
            t = m.group(0)
            if _es_nombre(t, lugares) and not RX_PREFIJO_LUGAR.search(texto[: m.start()]):
                conteo[t] = conteo.get(t, 0) + 1
    if not conteo:
        return None
    mejor = max(conteo.items(), key=lambda kv: kv[1])
    return mejor[0] if mejor[1] >= 2 else None


def nombre_generado(uuid: str, sex: str) -> str:
    """Nombre determinista por uuid y sexo a partir de listas comunes."""
    nombres = NOMBRES_F if str(sex).lower().startswith("f") else NOMBRES_M
    nombre = nombres[_hash_int("nombre", uuid) % len(nombres)]
    apellido = APELLIDOS[_hash_int("apellido", uuid) % len(APELLIDOS)]
    return f"{nombre} {apellido}"


def con_tratamiento(nombre: str, sex: str, edad: int, edad_don: int) -> str:
    """Antepone Don/Doña desde edad_don años."""
    if edad < edad_don:
        return nombre
    return f"{'Doña' if str(sex).lower().startswith('f') else 'Don'} {nombre}"


def historia_corta(persona: str, profesional: str, max_chars: int = 400) -> str:
    """Persona + inicio de professional_persona, cortado en palabra completa."""
    texto = f"{normalizar(persona).strip()} {normalizar(profesional).strip()}".strip()
    if len(texto) <= max_chars:
        return texto
    corte = texto[: max_chars - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return corte + "…"


def lugares_de(df: pd.DataFrame) -> set[str]:
    """Tokens capitalizados de departamentos y municipios (no son nombres)."""
    valores = pd.concat([df["department"], df["municipality"]]).dropna().unique()
    lugares: set[str] = set()
    for v in valores:
        tokens = RX_TOKEN.findall(normalizar(str(v)))
        for i, t in enumerate(tokens):
            # "San Vicente" no convierte a "Vicente" en lugar.
            if i == 0 or tokens[i - 1] not in {"San", "Santa", "Santo"}:
                lugares.add(t)
    return lugares


def derivar(
    df: pd.DataFrame, pcfg: dict[str, Any], defecto_cultivo: str, lugares: set[str]
) -> pd.DataFrame:
    """Agrega columnas derivadas: cultivo, zona, bandas, escala y nombre."""
    out = df.copy()
    out["cultivo_principal"] = out["occupation"].map(
        lambda o: cultivo_de(o, pcfg["cultivos"], defecto_cultivo)
    )
    out["zona"] = out["department"].map(lambda d: zona_de(d, pcfg["zonas"]))
    out["banda_edad"] = out["age"].map(lambda e: banda_edad(int(e), pcfg["bandas_edad"]))
    out["escolaridad"] = out["education_level"].map(
        lambda n: nivel_escolar(n, pcfg["escolaridad"])
    )
    texto = out["professional_persona"].fillna("") + " " + out["persona"].fillna("")
    escalas = pd.Series(
        [escala_de(t, pcfg["escala"], c) for t, c in zip(texto, out["cultivo_principal"])],
        index=out.index,
    )
    out["escala"] = escalas.str[0]
    out["escala_senal"] = escalas.str[1]
    out["escala_inferida"] = True
    extraidos = [
        extraer_nombre([p, q], lugares)
        for p, q in zip(out["professional_persona"], out["persona"])
    ]
    out["nombre_fuente"] = ["texto" if n else "generado" for n in extraidos]
    out["nombre_display"] = [
        con_tratamiento(n or nombre_generado(u, s), s, int(e), pcfg["edad_don"])
        for n, u, s, e in zip(extraidos, out["uuid"], out["sex"], out["age"])
    ]
    return out


# --- Muestreo -----------------------------------------------------------------


def cuotas_proporcionales(conteos: pd.Series, n: int) -> dict[str, int]:
    """Reparte n según la proporción natural (mayor residuo, desempate por nombre)."""
    total = int(conteos.sum())
    n = min(n, total)
    if n == 0:
        return {}
    exactas = conteos / total * n
    base = exactas.astype(int)
    resto = n - int(base.sum())
    residuos = (exactas - base).reset_index()
    residuos.columns = ["clave", "residuo"]
    orden = residuos.sort_values(["residuo", "clave"], ascending=[False, True])["clave"]
    for clave in list(orden)[:resto]:
        base[clave] += 1
    return {k: int(v) for k, v in base.items() if v > 0}


def round_robin(df: pd.DataFrame, n: int, seed: int, etiqueta: str) -> pd.DataFrame:
    """Toma n filas rotando entre estratos edad x escolaridad, orden fijo por seed."""
    if n <= 0 or df.empty:
        return df.iloc[0:0]
    df = df.assign(_orden=[_hash_int(seed, u) for u in df["uuid"]])
    df = df.sort_values(["_orden", "uuid"])
    estratos = sorted(
        df.groupby(["banda_edad", "escolaridad"]).groups.keys(),
        key=lambda k: _hash_int(seed, etiqueta, *k),
    )
    colas = {k: list(df.index[(df["banda_edad"] == k[0]) & (df["escolaridad"] == k[1])])
             for k in estratos}
    elegidos: list[Any] = []
    while len(elegidos) < n and any(colas.values()):
        for k in estratos:
            if colas[k] and len(elegidos) < n:
                elegidos.append(colas[k].pop(0))
    return df.loc[elegidos].drop(columns="_orden")


@dataclass
class ResultadoDepto:
    """Resultado del muestreo de un departamento."""

    depto: str
    pedidos: int
    principal: int = 0
    ampliacion: int = 0
    faltantes: int = 0
    elegibles: int = 0
    excluidos_principal: int = 0
    excluidos_ampliacion: int = 0
    notas: list[str] = field(default_factory=list)


def muestrear_depto(
    principal: pd.DataFrame, ampliacion: pd.DataFrame, depto: str, n: int, seed: int
) -> tuple[pd.DataFrame, ResultadoDepto]:
    """Muestrea n personas de un departamento sin duplicar."""
    res = ResultadoDepto(depto=depto, pedidos=n)
    pool = principal[principal["department"] == depto]
    cuotas = cuotas_proporcionales(pool["cultivo_principal"].value_counts().sort_index(), n)
    partes = [
        round_robin(pool[pool["cultivo_principal"] == c], q, seed, f"{depto}|{c}")
        for c, q in sorted(cuotas.items())
    ]
    elegidos = pd.concat(partes) if partes else pool.iloc[0:0]
    res.principal = len(elegidos)

    falta = n - len(elegidos)
    if falta > 0:
        extra_pool = ampliacion[
            (ampliacion["department"] == depto) & ~ampliacion["uuid"].isin(elegidos["uuid"])
        ]
        extra = round_robin(extra_pool, falta, seed, f"{depto}|ampliacion")
        res.ampliacion = len(extra)
        res.notas.append(
            f"Regex principal con {len(pool)} disponibles; ampliación aporta {len(extra)}."
        )
        elegidos = pd.concat([elegidos, extra])
    res.faltantes = n - len(elegidos)
    if res.faltantes > 0:
        res.notas.append(f"Faltan {res.faltantes}: no hay más personas elegibles.")
    elegidos = elegidos.assign(fuente=["principal"] * res.principal + ["ampliacion"] * res.ampliacion)
    return elegidos, res


def construir_panel(
    df: pd.DataFrame, cfg: dict[str, Any], por_depto: int, seed: int
) -> tuple[pd.DataFrame, list[ResultadoDepto]]:
    """Construye el panel completo: filtra, deriva y muestrea por departamento."""
    pcfg = cfg["panel"]
    lugares = lugares_de(df)
    principal, excl_p = excluir_contratados(filtrar_principal(df, pcfg), pcfg)
    ampliacion, excl_a = excluir_contratados(filtrar_ampliacion(df, pcfg), pcfg)
    principal = derivar(principal, pcfg, "sin_clasificar", lugares)
    ampliacion = derivar(ampliacion, pcfg, pcfg["ampliacion"]["cultivo"], lugares)
    ampliacion = ampliacion[~ampliacion["uuid"].isin(principal["uuid"])]
    ampliacion["cultivo_principal"] = pcfg["ampliacion"]["cultivo"]

    deptos = [d for zona in pcfg["zonas"].values() for d in zona]
    partes, resultados = [], []
    for depto in sorted(deptos):
        sel, res = muestrear_depto(principal, ampliacion, depto, por_depto, seed)
        res.excluidos_principal = int(excl_p.get(depto, 0))
        res.excluidos_ampliacion = int(excl_a.get(depto, 0))
        res.elegibles = int((principal["department"] == depto).sum())
        partes.append(sel)
        resultados.append(res)
    panel = pd.concat(partes, ignore_index=True)
    if panel["uuid"].duplicated().any():
        raise RuntimeError("El panel contiene uuid duplicados.")
    return panel, resultados


# --- Reporte ------------------------------------------------------------------


def _tabla_md(tabla: pd.DataFrame) -> str:
    """Convierte un DataFrame en tabla Markdown sin dependencias extra."""
    cols = [str(tabla.index.name or "")] + [str(c) for c in tabla.columns]
    filas = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for idx, fila in tabla.iterrows():
        filas.append("| " + " | ".join([str(idx)] + [str(v) for v in fila]) + " |")
    return "\n".join(filas)


def _cruce(panel: pd.DataFrame, col: str) -> pd.DataFrame:
    """Tabla departamento x columna con totales."""
    t = pd.crosstab(panel["department"], panel[col], margins=True, margins_name="Total")
    t.index.name = "Departamento"
    return t


def escribir_reporte(
    panel: pd.DataFrame, resultados: list[ResultadoDepto], destino: Path,
    por_depto: int, seed: int,
) -> None:
    """Escribe docs/panel_reporte.md con cobertura y cruces del panel."""
    pedidos = por_depto * len(resultados)
    cobertura = pd.DataFrame(
        [{"Departamento": r.depto, "n": r.principal + r.ampliacion,
          "principal": r.principal, "ampliación": r.ampliacion,
          "faltantes": r.faltantes} for r in resultados]
    ).set_index("Departamento")
    exclusiones = pd.DataFrame(
        [{"Departamento": r.depto, "elegibles": r.elegibles,
          "excluidos (principal)": r.excluidos_principal,
          "excluidos (ampliación)": r.excluidos_ampliacion} for r in resultados]
    ).set_index("Departamento")
    exclusiones.loc["Total"] = exclusiones.sum()
    nombres = panel["nombre_fuente"].value_counts()
    notas = [f"- **{r.depto}**: {' '.join(r.notas)}" for r in resultados if r.notas]
    partes = [
        "# Reporte del panel",
        "",
        "Escenario simulado para demo. Agricultores sintéticos de "
        "nvidia/Nemotron-Personas-El-Salvador.",
        "",
        f"- Personas por departamento: {por_depto}",
        f"- Semilla: {seed}",
        f"- Filas: {len(panel)} de {pedidos} pedidas",
        "- Escala inferida por regex en professional_persona y persona "
        "(escala_inferida=True; señal en escala_senal).",
        f"- nombre_display extraído del texto: {int(nombres.get('texto', 0))}; "
        f"generado: {int(nombres.get('generado', 0))}.",
        "",
        "## Cobertura por departamento",
        "",
        _tabla_md(cobertura),
        "",
        "## Trabajadores contratados excluidos",
        "",
        "Se excluyen quienes trabajan como asalariados (empleado/a de finca, "
        "jornalero, peón, etc.) sin indicar parcela propia. `elegibles` es el "
        "universo del regex principal tras la exclusión.",
        "",
        _tabla_md(exclusiones),
        "",
        "## Faltantes y ampliaciones",
        "",
        "\n".join(notas) if notas else "Sin faltantes ni ampliaciones.",
        "",
        "## Departamento x banda de edad",
        "",
        _tabla_md(_cruce(panel, "banda_edad")),
        "",
        "## Departamento x escolaridad",
        "",
        _tabla_md(_cruce(panel, "escolaridad")),
        "",
        "## Departamento x cultivo principal",
        "",
        _tabla_md(_cruce(panel, "cultivo_principal")),
        "",
        "## Departamento x escala",
        "",
        _tabla_md(_cruce(panel, "escala")),
        "",
    ]
    destino.write_text("\n".join(partes), encoding="utf-8")
