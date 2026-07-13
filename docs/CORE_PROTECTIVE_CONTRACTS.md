# Contratos protectores de CORE

Un contrato CORE debe poder ser protegido por otros contratos que limiten su
interpretación y su ejecución. La protección no cambia el contrato original:
lo rodea con condiciones comprobables.

## Núcleo de protección

Un contrato destinado a coordinar una acción debería enlazarse, cuando aplique,
con estas capas:

| Capa | Contrato CORE | Qué protege |
| --- | --- | --- |
| Integridad | `FrozenReleaseManifest.v1` y `FrozenRuleSet.v1` | Que el contenido, versión y dependencias no cambien silenciosamente. |
| Autoridad | `RuleApprovalRequest.v1`, `RuleApproval.v1` y `PhysicalSafetyAssuranceCase.v1` | Que una validación no se convierta en permiso autónomo. |
| Reversibilidad | `ReversibilityPolicy.v1`, `StateTransition.v1` y `EffectResult.v1` | Que cada efecto declare cómo detenerse, revertirse o compensarse. |
| Evidencia | `CausalTrace.v1`, `ExecutionReceipt.v1` y `RuleAnchorChainEvidence.v1` | Que la afirmación pueda reconstruirse y compararse con el resultado. |
| Cierre | `TaskCloseout.v1` y `RetentionManifest.v1` | Que el proceso termine con estado, residuos, advertencias y retención declarados. |

## Regla de composición

Una propuesta solo puede avanzar si todas sus capas obligatorias pasan. Un
contrato protector nunca debe convertir un resultado `passed` en autorización
para firmar, transmitir, desplegar, gastar fondos o causar una acción física.
Esas decisiones permanecen fuera de CORE y requieren la autoridad responsable
correspondiente.

La forma genérica de enlace es:

`contrato protegido -> fingerprint -> contratos protectores -> evidencia -> resultado -> cierre`

Cada enlace debe indicar el fingerprint exacto, la versión del schema, el
alcance, el responsable de revisión y si el efecto es reversible. Si falta una
capa, el sistema debe quedar en `blocked` o `needs_review`, nunca asumir que
la protección existe.

## Protecciones mínimas

- Integridad: el fingerprint del contrato protegido coincide con sus bytes.
- Alcance: la acción no excede los actores, recursos, dominio o tiempo
  declarados.
- Necesidad y proporcionalidad: se distinguen supervivencia, protección o
  alimentación de lujo, exceso o conveniencia.
- Alternativas: se registran opciones menos dañinas y por qué fueron
  descartadas.
- Reversibilidad: una acción irreversible exige evidencia y revisión superior.
- Autoridad: aprobación humana o responsable explícita cuando corresponda.
- Evidencia: el resultado identifica fuentes, incertidumbres y límites.
- Cierre: toda ejecución deja un recibo determinista y un estado final.

## Aprendizaje compartible

Lo que se congela y comparte es la estructura general de estas protecciones,
los schemas, validadores, pruebas y fingerprints. No se comparten secretos,
identidades, datos personales ni aperturas de compromisos privados. Así el
aprendizaje común aumenta la verificabilidad sin convertir los casos
particulares en propiedad pública.

Estos contratos son capas de seguridad y coordinación, no una autoridad sobre
el valor de una vida ni una licencia general para producir daño.
