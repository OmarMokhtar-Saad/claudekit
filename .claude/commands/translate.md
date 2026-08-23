---
description: "Translate documentation or extract UI strings for internationalization"
argument-hint: "<target-language|extract> [file-or-directory]"
---

# Translate

Translate project documentation to a target language or extract UI strings for internationalization.

## Task

Translation operation: $ARGUMENTS

## Supported Languages

| Code | Language | Script Direction |
|------|----------|-----------------|
| `ar` | Arabic (العربية) | RTL |
| `zh` | Chinese (中文) | LTR |
| `es` | Spanish (Espanol) | LTR |
| `fr` | French (Francais) | LTR |
| `ja` | Japanese (日本語) | LTR |
| `ko` | Korean (한국어) | LTR |
| `de` | German (Deutsch) | LTR |
| `pt` | Portuguese (Portugues) | LTR |
| `ru` | Russian (Русский) | LTR |
| `hi` | Hindi (हिन्दी) | LTR |
| `tr` | Turkish (Turkce) | LTR |

## Operations

### Translate Document (`/translate <lang> <file>`)

1. Read the source document
2. Identify translatable content (text, headings, table cells, alt text)
3. Preserve all Markdown formatting, code blocks, links, and HTML structure
4. Translate natural language content to the target language
5. For RTL languages (Arabic, Hebrew):
   - Wrap content in `<div dir="rtl" align="right">`
   - Ensure tables render correctly in RTL context
   - Preserve LTR formatting for code, URLs, and file paths
6. Write the translated file to the appropriate location
7. Add a language selector header linking all available translations

### Extract Strings (`/translate extract <directory>`)

1. Scan source files in the target directory for user-facing strings
2. Identify string literals in:
   - UI components (labels, buttons, messages, tooltips)
   - Error messages and validation text
   - Log messages intended for users
   - Configuration display strings
3. Generate a translation file in the appropriate format:
   - `.json` for JavaScript/TypeScript projects
   - `.properties` for Java projects
   - `.strings` for Swift projects
   - `.po` for Python projects
4. Organize strings by component/module
5. Include context comments for translators
6. Flag strings that contain interpolation variables

### Sync Translations (`/translate sync <base-lang> <target-lang>`)

1. Compare the base language file with the target language file
2. Identify missing keys in the target
3. Identify removed keys (present in target but not in base)
4. Report untranslated or stale entries
5. Generate a diff summary

## RTL Handling Rules

- ALWAYS wrap RTL content in appropriate `dir="rtl"` containers
- NEVER reverse code snippets, file paths, URLs, or command-line examples
- ALWAYS preserve bidirectional markers for mixed-direction content
- ALWAYS test table alignment in RTL context
- Numeric values remain LTR even in RTL documents

## Quality Checks

After translation:

- Verify no Markdown formatting was broken
- Verify all links still resolve correctly
- Verify code blocks are untouched
- Verify placeholders/variables are preserved (e.g., `$ARGUMENTS`, `{name}`)
- Verify the language selector links are correct
- For RTL: verify the `dir` attribute is present on the root container

## Output

- Display the translated file path
- Report number of translated segments
- Flag any segments that need human review (idioms, technical terms, ambiguous phrases)
- Show warnings for any formatting issues detected
