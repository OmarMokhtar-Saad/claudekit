<p align="center">
  <img src="https://img.shields.io/badge/ClaudeKit-v2.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
</p>

<h1 align="center">ClaudeKit</h1>

<p align="center">
  <strong>Un sistema de orquestacion multi-agente de nivel produccion para <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>.</strong><br>
  Planificacion estructurada. Puertas de revision. Ejecucion segura. Verificacion de calidad. Cualquier lenguaje.
</p>

<p align="center">
  <a href="#inicio-rapido">Inicio Rapido</a> &middot;
  <a href="#como-funciona">Como Funciona</a> &middot;
  <a href="#comandos">Comandos</a> &middot;
  <a href="#agentes">Agentes</a> &middot;
  <a href="#contribuir">Contribuir</a>
</p>

---

### Seleccionar Idioma | Select Language

[English](../README.md) | [العربية](README.ar.md) | [中文](README.zh.md) | **Espanol** | [Francais](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

---

## Por que ClaudeKit?

Claude Code es poderoso por si solo. ClaudeKit lo hace **estructurado, seguro y auditable**.

Sin ClaudeKit, un asistente de IA realiza cambios directamente -- sin plan, sin revision, sin rollback. Con ClaudeKit, cada cambio sigue un pipeline: planificarlo, revisarlo, ejecutarlo de forma segura, verificar el resultado.

### Componentes Principales

| Componente | Cantidad | Descripcion |
|------------|----------|-------------|
| Agentes | 13 | Agentes especializados para cada tarea |
| Comandos | 20+ | Comandos listos para usar |
| Habilidades | 55+ | Habilidades reutilizables |
| Modos | 7 | Diferentes modos de comportamiento |
| Guardias de seguridad | 29 | Guardias que validan cada configuracion |
| Plantillas de lenguaje | 11 | Soporte para Python, TypeScript, Java, Go y mas |
| Servidores MCP | 5 | Integracion del Protocolo de Contexto de Modelo |

---

## Inicio Rapido

### Instalacion

```bash
git clone https://github.com/omarmokhtar/claudekit.git
./claudekit/install.sh /path/to/your-project --full
```

El instalador detecta automaticamente el lenguaje de tu proyecto, copia el directorio `.claude/` a tu proyecto, genera `CLAUDE.md` y `CONSTITUTION.md`, y configura los hooks con tus comandos de build/test/lint.

### Opciones de Instalacion

```bash
# Instalacion completa (agentes + comandos + habilidades + hooks + operaciones)
./install.sh ./my-project --full

# Instalacion minima (agentes + comandos + operaciones solamente)
./install.sh ./my-project --minimal

# Pre-configurar lenguaje
./install.sh ./my-project --full --language typescript

# Sobrescribir instalacion existente
./install.sh ./my-project --full --force
```

### Uso

Abre tu proyecto en Claude Code y ejecuta:

```
/plan Agregar autenticacion de usuario con tokens JWT
```

ClaudeKit toma el control -- el Planificador explora la base de codigo, escribe un plan con configuracion ops.json, el Revisor lo valida, el Implementador lo ejecuta con respaldo automatico, y el Verificador comprueba el resultado.

---

## Comandos

| Comando | Descripcion | Ejemplo |
|---------|-------------|---------|
| `/plan` | Crear un plan de implementacion con ops.json | `/plan Agregar limitacion de tasa al API` |
| `/review` | Validar un plan (umbral 90/100) | `/review` |
| `/implement` | Ejecutar un plan aprobado | `/implement` |
| `/verify` | Ejecutar verificaciones de calidad (umbral 80/100) | `/verify` |
| `/debug` | Diagnosticar un error (solo lectura) | `/debug Por que el login devuelve 500?` |
| `/docs` | Generar documentacion | `/docs Referencia API del modulo de auth` |
| `/git` | Operaciones Git | `/git commit "feat: agregar auth"` |
| `/coordinator` | Orquestacion multi-agente | `/coordinator Migrar esquema de base de datos` |
| `/explore` | Explorar arquitectura del codigo | `/explore Como funciona el modulo de auth?` |
| `/security` | Analisis de seguridad | `/security Escanear modulo de auth` |
| `/test` | Generar y ejecutar pruebas | `/test src/services/auth.ts --generate` |
| `/deploy` | Preparacion de release y despliegue | `/deploy release` |

---

## Agentes

| Agente | Responsabilidad | Modelo |
|--------|----------------|--------|
| **Coordinador** | Clasifica tareas, orquesta flujos de trabajo, gestiona traspasos de agentes | Sonnet |
| **Planificador** | Explora la base de codigo, escribe planes de implementacion + configs ops.json | Sonnet |
| **Revisor** | Validacion multidimensional del plan -- Calidad (40%), Arquitectura (30%), Seguridad (30%) | Opus |
| **Implementador** | Ejecuta planes aprobados via scripts de operaciones con respaldo automatico | Sonnet |
| **Verificador** | Validacion de calidad -- Analisis estatico (30%), Pruebas (40%), Cobertura (30%) | Haiku |
| **Depurador** | Analisis de causa raiz en solo lectura usando depuracion sistematica de 4 fases | Opus |
| **Documentador** | Crea y mantiene documentacion tecnica | Haiku |
| **GitOps** | Ramas, commits, creacion de PR, gestion de releases | Haiku |
| **Explorador** | Exploracion rapida del codigo, descubrimiento de patrones, mapeo de arquitectura | Sonnet |
| **Tester** | Escritura dedicada de pruebas -- unitarias, integracion, E2E, analisis de cobertura | Sonnet |
| **Scanner de Seguridad** | Escaneo OWASP Top 10, deteccion de secretos, analisis de CVE de dependencias | Opus |
| **DevOps** | Pipelines CI/CD, contenedorizacion, despliegue, infraestructura como codigo | Sonnet |
| **Arquitecto de BD** | Diseno de esquemas, migraciones, optimizacion de consultas, modelado de datos | Sonnet |

---

## Modos de Comportamiento

| Modo | Descripcion |
|------|-------------|
| **Predeterminado** | Operacion normal con explicaciones completas y formato de salida |
| **Lluvia de ideas** | Generacion de ideas libre sin restricciones de implementacion |
| **Eficiente en tokens** | Salida comprimida apuntando a 40-70% de ahorro en tokens |

---

## Flujo de Trabajo Basado en Especificaciones

1. Escribe una especificacion en `specs/`
2. Ejecuta `/plan` para planificar desde la especificacion
3. El Revisor valida contra la especificacion
4. El Verificador asegura conformidad con la especificacion

---

## Contribuir

Las contribuciones son bienvenidas! Consulta la [guia de contribucion](../CONTRIBUTING.md) para mas detalles.

---

## Licencia

MIT -- Consulta [LICENSE](../LICENSE) para mas detalles.
