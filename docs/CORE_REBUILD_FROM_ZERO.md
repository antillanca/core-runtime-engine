# CORE desde 0 - Reconstruccion publica por lista blanca

Fecha: 2026-07-06
Estado: ejecutado
Autoridad: documento publico de alcance del corte v11

## Contexto

CORE v11 es una reconstruccion por lista blanca. El objetivo fue reducir el
repositorio a un motor publico, determinista y agnostico de contratos,
schemas, validadores, fingerprints, manifests, evidencia acotada y tooling de
release.

El repositorio historico contenia prototipos, demos, datasets, runtime
experimental y material de investigacion que no forman parte del contrato
publico. Ese material fue archivado fuera de la superficie publica.

## Decision

Se conserva solo lo que cumple estas reglas:

- es reutilizable por dominios externos sin nombres privados;
- valida artefactos mediante contratos publicos;
- puede ejecutarse sin red y sin servicios obligatorios;
- no contiene semantica de un negocio, cliente, producto o workspace privado;
- no convierte CORE en autoridad legal, fiscal, economica ni operacional;
- mantiene salida determinista y replayable.

La reconstruccion se hizo por lista blanca, no por limpieza incremental. Si
una pieza no era necesaria para la superficie publica conservada, quedo fuera.

## Superficie conservada

| Area | Alcance publico |
| --- | --- |
| `schemas/` | schemas JSON publicos y familia `schemas/core/*.v1.json` |
| `scripts/validate_*.py` | validadores CLI por schema |
| `scripts/read_bounded_reference.py` | lectura acotada por refs, limites y raiz declarada |
| `scripts/derive_business_event.py` | derivacion estructural generica de eventos |
| `scripts/core_anchor.py`, `scripts/submit_anchoring.py` | anclaje opcional, apagado por defecto |
| `core_runtime/core/` | canonicalizacion, fingerprints, carga de contratos y utilidades deterministas |
| `core_runtime/cli/` | validate, lint, doctor, inventory, contract_preflight, release_check y tooling de release |
| `contracts/CoreAnchor.sol` | contrato opcional de anclaje externo |
| `tests/` | suite de validacion de schemas, scripts, CLI y ejemplos publicos |
| `examples/` | fixtures sinteticos, genericos y sin nombres privados |

## Superficie archivada

Se archivo todo lo que pertenecia a demos, simuladores, pipelines
experimentales, datasets, runtimes de investigacion, material historico o
dominios privados. El archivo historico existe para trazabilidad, no como
parte del contrato publico v11.

## Contrato de frontera publica

CORE publico no debe contener:

- nombres de productos, clientes, negocios o repos privados;
- rutas absolutas de operador o workspace;
- datos de clientes, costos, recetas, inventarios, documentos privados o
  secretos;
- semantica legal, fiscal, contable, operacional o economica de un dominio;
- fixtures aceptados que dependan de un dominio real;
- afirmaciones de autoridad sobre valor real, legalidad, fraude o negocio.

Los consumidores externos deben adaptar sus propios dominios a contratos
publicos mediante payloads redactados, manifests y fingerprints. CORE valida
estructura y trazabilidad; el dominio externo conserva la autoridad material.

## Compatibilidad

Los entrypoints publicos conservados mantienen contratos JSON por subprocess.
Los consumidores downstream pueden seguir invocando validadores y lectores
acotados, pero sus nombres privados no forman parte de esta documentacion ni
de los fixtures publicos.

## Criterio de cierre

- El README describe solo la superficie publica real.
- La suite de tests corre sin red.
- Los ejemplos aceptados son sinteticos y agnosticos.
- Los fixtures rechazados pueden demostrar fugas usando marcadores genericos,
  no nombres privados reales.
- La publicacion no contiene referencias a dominios privados.
- El legado permanece accesible fuera del contrato publico v11.

## Resultado

CORE v11 queda como motor publico de contratos, schemas, validadores,
fingerprints, evidencia acotada, replay y tooling de release. No opera ningun
negocio y no incorpora semantica privada de consumidores downstream.
