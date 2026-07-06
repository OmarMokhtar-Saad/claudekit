<p align="center">
  <img src="https://img.shields.io/badge/ClaudeKit-v2.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
</p>

<h1 align="center">ClaudeKit</h1>

<p align="center">
  <strong>Un systeme d'orchestration multi-agents de niveau production pour <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>.</strong><br>
  Planification structuree. Portes de revision. Execution securisee. Verification de qualite. Tout langage.
</p>

<p align="center">
  <a href="#demarrage-rapide">Demarrage Rapide</a> &middot;
  <a href="#comment-ca-marche">Comment ca Marche</a> &middot;
  <a href="#commandes">Commandes</a> &middot;
  <a href="#agents">Agents</a> &middot;
  <a href="#contribuer">Contribuer</a>
</p>

---

### Choisir la Langue | Select Language

[English](../README.md) | [العربية](README.ar.md) | [中文](README.zh.md) | [Espanol](README.es.md) | **Francais** | [日本語](README.ja.md) | [한국어](README.ko.md)

---

## Pourquoi ClaudeKit ?

Claude Code est puissant en soi. ClaudeKit le rend **structure, securise et auditable**.

Sans ClaudeKit, un assistant IA effectue des modifications directement -- sans plan, sans revision, sans retour en arriere. Avec ClaudeKit, chaque modification suit un pipeline : planifier, reviser, executer en securite, verifier le resultat.

### Composants Principaux

| Composant | Nombre | Description |
|-----------|--------|-------------|
| Agents | 13 | Agents specialises pour chaque tache |
| Commandes | 20+ | Commandes pretes a l'emploi |
| Competences | 55+ | Competences reutilisables |
| Modes | 7 | Differents modes de comportement |
| Gardes de securite | 29 | Gardes validant chaque configuration |
| Modeles de langage | 11 | Support Python, TypeScript, Java, Go et plus |
| Serveurs MCP | 5 | Integration du Protocole de Contexte de Modele |

---

## Demarrage Rapide

### Installation

```bash
git clone https://github.com/omarmokhtar/claudekit.git
./claudekit/install.sh /path/to/your-project --full
```

L'installateur detecte automatiquement le langage de votre projet, copie le repertoire `.claude/` dans votre projet, genere `CLAUDE.md` et `CONSTITUTION.md`, et configure les hooks avec vos commandes de build/test/lint.

### Options d'Installation

```bash
# Installation complete (agents + commandes + competences + hooks + operations)
./install.sh ./my-project --full

# Installation minimale (agents + commandes + operations uniquement)
./install.sh ./my-project --minimal

# Pre-configurer le langage
./install.sh ./my-project --full --language typescript

# Ecraser une installation existante
./install.sh ./my-project --full --force
```

### Utilisation

Ouvrez votre projet dans Claude Code et executez :

```
/plan Ajouter l'authentification utilisateur avec des jetons JWT
```

ClaudeKit prend le relais -- le Planificateur explore la base de code, redige un plan avec une configuration ops.json, le Reviseur le valide, l'Implementeur l'execute avec sauvegarde automatique, et le Verificateur controle le resultat.

---

## Commandes

| Commande | Description | Exemple |
|----------|-------------|---------|
| `/plan` | Creer un plan d'implementation avec ops.json | `/plan Ajouter la limitation de debit a l'API` |
| `/review` | Valider un plan (seuil 90/100) | `/review` |
| `/implement` | Executer un plan approuve | `/implement` |
| `/verify` | Executer les controles qualite (seuil 80/100) | `/verify` |
| `/debug` | Diagnostiquer un bug (lecture seule) | `/debug Pourquoi le login renvoie 500 ?` |
| `/docs` | Generer la documentation | `/docs Reference API du module auth` |
| `/git` | Operations Git | `/git commit "feat: ajout auth"` |
| `/coordinator` | Orchestration multi-agents | `/coordinator Migrer le schema de la base` |
| `/explore` | Explorer l'architecture du code | `/explore Comment fonctionne le module auth ?` |
| `/security` | Analyse de securite | `/security Scanner le module auth` |
| `/test` | Generer et executer des tests | `/test src/services/auth.ts --generate` |
| `/deploy` | Preparation de release et deploiement | `/deploy release` |

---

## Agents

| Agent | Responsabilite | Modele |
|-------|---------------|--------|
| **Coordinateur** | Classe les taches, orchestre les workflows, gere les transferts d'agents | Sonnet |
| **Planificateur** | Explore la base de code, redige les plans + configs ops.json | Sonnet |
| **Reviseur** | Validation multidimensionnelle -- Qualite du plan (40%), Architecture (30%), Securite (30%) | Opus |
| **Implementeur** | Execute les plans approuves via scripts d'operations avec sauvegarde auto | Sonnet |
| **Verificateur** | Validation qualite -- Analyse statique (30%), Tests (40%), Couverture (30%) | Haiku |
| **Debogueur** | Analyse de cause racine en lecture seule avec debogage systematique en 4 phases | Opus |
| **Documenteur** | Cree et maintient la documentation technique | Haiku |
| **GitOps** | Branches, commits, creation de PR, gestion des releases | Haiku |
| **Explorateur** | Exploration rapide du code, decouverte de patterns, cartographie d'architecture | Sonnet |
| **Testeur** | Ecriture de tests dediee -- unitaires, integration, E2E, analyse de couverture | Sonnet |
| **Scanner de Securite** | Scan OWASP Top 10, detection de secrets, analyse CVE des dependances | Opus |
| **DevOps** | Pipelines CI/CD, conteneurisation, deploiement, infrastructure as code | Sonnet |
| **Architecte BD** | Conception de schemas, migrations, optimisation de requetes, modelisation de donnees | Sonnet |

---

## Modes de Comportement

| Mode | Description |
|------|-------------|
| **Par defaut** | Fonctionnement normal avec explications completes et formatage de sortie |
| **Brainstorming** | Generation d'idees libre sans contraintes d'implementation |
| **Efficient en tokens** | Sortie compressee visant 40-70% d'economie de tokens |

---

## Workflow Base sur les Specifications

1. Redigez une specification dans `specs/`
2. Executez `/plan` pour planifier a partir de la specification
3. Le Reviseur valide par rapport a la specification
4. Le Verificateur assure la conformite avec la specification

---

## Contribuer

Les contributions sont les bienvenues ! Consultez le [guide de contribution](../CONTRIBUTING.md) pour plus de details.

---

## Licence

MIT -- Consultez [LICENSE](../LICENSE) pour plus de details.
