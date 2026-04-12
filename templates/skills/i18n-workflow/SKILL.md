---
name: i18n-workflow
description: "Use when internationalizing an application -- covers string externalization, ICU MessageFormat, locale-aware formatting, RTL support, and translation file management."
---

# Internationalization Workflow

## Purpose

Guide the complete internationalization (i18n) and localization (l10n) process for any application. Covers extracting hardcoded strings, structuring translation files, handling plurals and gender, formatting dates/numbers/currencies by locale, and supporting right-to-left languages.

---

## String Externalization

### Principles

1. **No hardcoded user-facing strings** -- every string visible to users must come from a translation file
2. **Keys over values** -- use semantic keys (`auth.login.button`) not English text keys (`"Log In"`)
3. **Context for translators** -- include descriptions explaining where and how the string is used
4. **Group by feature** -- organize strings by module/feature, not by screen

### Process

1. Scan source files for string literals in UI-rendering code
2. Replace each literal with a translation function call:
   - JavaScript: `t('key')` or `intl.formatMessage({ id: 'key' })`
   - Python: `_('key')` or `gettext('key')`
   - Java: `messages.getString("key")`
   - Swift: `NSLocalizedString("key", comment: "context")`
3. Add the extracted key-value pair to the base locale file
4. Include translator context as comments or metadata

### File Structure

```
locales/
  en/
    common.json        # Shared strings (buttons, labels, errors)
    auth.json          # Authentication module
    dashboard.json     # Dashboard module
    errors.json        # Error messages
  ar/
    common.json
    auth.json
    ...
  zh/
    ...
```

---

## ICU MessageFormat

Use ICU MessageFormat for all non-trivial strings. It handles plurals, gender, select, and number/date formatting in a translator-friendly way.

### Plurals

```
{count, plural,
  =0 {No items}
  one {# item}
  other {# items}
}
```

### Gender / Select

```
{gender, select,
  male {He updated his profile}
  female {She updated her profile}
  other {They updated their profile}
}
```

### Nested

```
{gender, select,
  male {{count, plural, one {He has # item} other {He has # items}}}
  female {{count, plural, one {She has # item} other {She has # items}}}
  other {{count, plural, one {They have # item} other {They have # items}}}
}
```

### Rules

- ALWAYS use ICU plural categories (`zero`, `one`, `two`, `few`, `many`, `other`) -- never assume only `one`/`other`
- ALWAYS use `#` for the numeric placeholder inside plural blocks
- NEVER concatenate translated strings -- use a single message with all variants
- NEVER split sentences across multiple keys

---

## Locale-Aware Formatting

### Dates

- Use `Intl.DateTimeFormat` (JS), `DateTimeFormatter` (Java), `strftime` with locale (Python)
- NEVER hardcode date formats like `MM/DD/YYYY` -- always derive from locale
- Provide format options (short, medium, long, full) not format strings

### Numbers

- Use `Intl.NumberFormat` (JS), `NumberFormat` (Java), `locale.format_string` (Python)
- Decimal separators vary: `1,234.56` (en) vs `1.234,56` (de) vs `1 234,56` (fr)
- NEVER use string interpolation for numbers -- always use locale-aware formatters

### Currency

- Always pair currency code with amount: `{ amount: 1234.56, currency: 'USD' }`
- Currency symbol position varies by locale ($100 vs 100$)
- Use `Intl.NumberFormat` with `style: 'currency'`

### Relative Time

- Use `Intl.RelativeTimeFormat` or equivalent
- Examples: "3 days ago", "in 2 hours", "yesterday"

---

## RTL Support

### CSS

```css
/* Use logical properties instead of physical */
margin-inline-start: 1rem;   /* NOT margin-left */
padding-inline-end: 0.5rem;  /* NOT padding-right */
border-inline-start: 1px solid;
text-align: start;           /* NOT text-align: left */
```

### HTML

```html
<html lang="ar" dir="rtl">
```

### Layout Mirroring

- Navigation: sidebar moves from left to right
- Icons with direction (arrows, progress bars) must flip
- Icons without direction (search, settings) must NOT flip
- Text alignment follows `start`/`end` not `left`/`right`
- Bidirectional text (e.g., Arabic with embedded English) needs proper isolation: `<bdi>` tags or Unicode isolates

### Testing

- Test every page in both LTR and RTL
- Verify form inputs align correctly
- Verify icons flip where appropriate
- Verify scrollbars appear on the correct side
- Verify toast/notification positioning

---

## Translation File Management

### Formats by Ecosystem

| Format | Ecosystem | Extension |
|--------|-----------|-----------|
| JSON | JavaScript/TypeScript | `.json` |
| Properties | Java/Kotlin | `.properties` |
| XLIFF | iOS/macOS | `.xliff` |
| Strings | Swift/Obj-C | `.strings` |
| PO/POT | Python/PHP/Ruby | `.po` / `.pot` |
| YAML | Rails/Flutter | `.yml` |
| ARB | Flutter/Dart | `.arb` |

### Workflow

1. Developer adds strings to the base locale (e.g., `en`)
2. CI extracts new/changed keys and generates a diff
3. Translation platform (Crowdin, Lokalise, Phrase) picks up new keys
4. Translators translate and review
5. CI pulls completed translations back to the repo
6. Build process compiles translation files into the app bundle

### Quality Checks

- **Completeness**: every key in the base locale must exist in all target locales
- **Placeholders**: all `{variable}` placeholders must appear in every translation
- **Length**: flag translations significantly longer than the source (may overflow UI)
- **ICU syntax**: validate all ICU MessageFormat strings parse correctly
- **Encoding**: all files must be UTF-8 without BOM
- **Duplicates**: no duplicate keys within a single file
- **Sorting**: keys should be sorted alphabetically for clean diffs

---

## Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Approach |
|-------------|-------------|-----------------|
| Concatenating translated fragments | Word order varies by language | Use a single message with placeholders |
| Using English text as keys | Keys change when English copy changes | Use semantic keys (`auth.login.title`) |
| Hardcoding date/number formats | Formats vary by locale | Use `Intl` APIs or equivalent |
| Assuming `one`/`other` plurals | Arabic has 6 plural forms, Polish has 4 | Use all ICU plural categories |
| Translating inside code | Mixing translation with logic | Extract all strings to resource files |
| Storing translations in code | Hard to manage, no translator tooling | Use external translation files |
| Using images with text | Cannot translate images easily | Use CSS/HTML text over images |
| Right/left in CSS | Breaks in RTL layouts | Use `start`/`end` logical properties |
