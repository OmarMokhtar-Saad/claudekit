---
name: i18n-patterns
description: "Use when implementing internationalization - locale-aware formatting, translation management, RTL support"
user-invocable: false
---

# Internationalization Patterns

## Core Principle

**Never hardcode locale assumptions.** Text, dates, numbers, currencies, and layouts all vary by locale. Design for internationalization from the start -- retrofitting is a rewrite.

---

## Translation Key Management

### Key Naming Convention

Use namespaced, hierarchical keys:

```
<feature>.<component>.<element>

Examples:
  auth.login.title          -> "Sign In"
  auth.login.submit_button  -> "Log In"
  auth.login.error.invalid  -> "Invalid email or password"
  settings.profile.name     -> "Display Name"
  common.actions.save       -> "Save"
  common.actions.cancel     -> "Cancel"
```

### Rules

- NEVER use the source text as the key (it changes, breaking translations)
- NEVER concatenate translated strings to build sentences
- ALWAYS use interpolation placeholders for dynamic values
- ALWAYS provide context comments for translators
- Group shared strings under a `common` namespace

### Interpolation

```
# GOOD: Interpolation with named placeholders
"welcome_message": "Welcome, {userName}! You have {count} notifications."

# BAD: String concatenation
greeting = t("welcome") + userName + t("you_have") + count + t("notifications")
```

---


### Externalization APIs by Language

Replace each user-visible literal with the platform's translation call, not a
home-grown lookup:

| Language | Call |
|---|---|
| JavaScript/TypeScript | `t('key')` or `intl.formatMessage({ id: 'key' })` |
| Python | `_('key')` or `gettext('key')` |
| Java/Kotlin | `messages.getString("key")` |
| Swift/Obj-C | `NSLocalizedString("key", comment: "context")` |

Include translator context as a comment or metadata alongside the key — a string
with no context is a string that gets mistranslated.

---

## Pluralization

Different languages have different plural rules. English has 2 forms (singular, plural). Arabic has 6. Russian has 3.

### ICU MessageFormat (Recommended)

```
{count, plural,
  =0 {No messages}
  one {1 message}
  other {{count} messages}
}
```

### Plural Categories (CLDR)

| Category | Languages That Use It |
|---|---|
| zero | Arabic, Latvian, Welsh |
| one | English, German, Spanish, French, Italian |
| two | Arabic, Hebrew, Slovenian |
| few | Czech, Polish, Russian, Arabic |
| many | Arabic, Polish, Russian |
| other | All languages (required fallback) |

**Rule:** Always provide at least `one` and `other` forms. Provide additional forms based on your target languages.

---

### Gender / Select

```
{gender, select,
  male {He updated his profile}
  female {She updated her profile}
  other {They updated their profile}
}
```

### Nested (select wrapping plural)

```
{gender, select,
  male {{count, plural, one {He has # item} other {He has # items}}}
  female {{count, plural, one {She has # item} other {She has # items}}}
  other {{count, plural, one {They have # item} other {They have # items}}}
}
```

**Rules:** always use `#` for the numeric placeholder inside a plural block;
never concatenate translated strings — use one message holding every variant;
never split a sentence across multiple keys.

---

## Date, Number, and Currency Formatting

### NEVER Format Manually

Use locale-aware formatting APIs:

| Data Type | Approach | Example |
|---|---|---|
| Dates | `Intl.DateTimeFormat` / locale library | "March 16, 2026" vs "16 mars 2026" |
| Numbers | `Intl.NumberFormat` / locale library | "1,234.56" vs "1.234,56" |
| Currency | `Intl.NumberFormat` with currency | "$1,234.56" vs "1.234,56 EUR" |
| Relative time | `Intl.RelativeTimeFormat` | "3 days ago" vs "il y a 3 jours" |

### Common Pitfalls

| Pitfall | Example | Fix |
|---|---|---|
| Hardcoded date format | `MM/DD/YYYY` | Use locale-aware formatter |
| Hardcoded decimal separator | `value.toFixed(2)` | Use number formatter |
| Hardcoded currency symbol | `"$" + amount` | Use currency formatter |
| Assuming 12-hour time | `3:00 PM` | Some locales use 24-hour |
| Hardcoded first day of week | Monday | Sunday in US, Saturday in Middle East |

---

## RTL (Right-to-Left) Layout Support

### RTL Languages

Arabic, Hebrew, Persian (Farsi), Urdu, and others read right-to-left.

### CSS Strategy

Use logical properties instead of physical properties:

| Physical (Avoid) | Logical (Preferred) |
|---|---|
| `margin-left` | `margin-inline-start` |
| `margin-right` | `margin-inline-end` |
| `padding-left` | `padding-inline-start` |
| `text-align: left` | `text-align: start` |
| `float: left` | `float: inline-start` |
| `left: 10px` | `inset-inline-start: 10px` |

### RTL Checklist

- [ ] Document direction set via `<html dir="rtl" lang="ar">`
- [ ] CSS uses logical properties (inline-start/end, not left/right)
- [ ] Icons that indicate direction are mirrored (arrows, progress bars)
- [ ] Icons that are universal are NOT mirrored (checkmarks, clocks, media controls)
- [ ] Text alignment follows document direction
- [ ] Bidirectional text is handled correctly (mixed LTR/RTL content)

---

## Translation Workflow

### File Organization

```
locales/
  en/
    common.json
    auth.json
    settings.json
  fr/
    common.json
    auth.json
    settings.json
  ar/
    common.json
    auth.json
    settings.json
```

### Process

1. Developer adds keys with source language text
2. Keys are extracted and sent to translators
3. Translations are reviewed and imported
4. Missing translations fall back to source language
5. Pseudo-localization is used for testing (accented characters, expanded text)

---

## Relative Time

- Use `Intl.RelativeTimeFormat` or equivalent
- Examples: "3 days ago", "in 2 hours", "yesterday"

---

## Translation File Formats by Ecosystem

| Format | Ecosystem | Extension |
|--------|-----------|-----------|
| JSON | JavaScript/TypeScript | `.json` |
| Properties | Java/Kotlin | `.properties` |
| XLIFF | iOS/macOS | `.xliff` |
| Strings | Swift/Obj-C | `.strings` |
| PO/POT | Python/PHP/Ruby | `.po` / `.pot` |
| YAML | Rails/Flutter | `.yml` |
| ARB | Flutter/Dart | `.arb` |

---


### The CI Round-Trip

1. A developer adds strings to the base locale (e.g. `en`)
2. CI extracts new or changed keys and generates a diff
3. The translation platform (Crowdin, Lokalise, Phrase) picks up the new keys
4. Translators translate and review
5. CI pulls completed translations back into the repo
6. The build compiles translation files into the app bundle

### RTL Testing

- Test every page in both LTR and RTL
- Verify form inputs align correctly
- Verify icons flip where appropriate — directional ones (arrows, progress) flip,
  non-directional ones (search, settings) must NOT
- Verify scrollbars appear on the correct side
- Verify toast and notification positioning
- Bidirectional text (Arabic with embedded English) needs proper isolation: `<bdi>`
  tags or Unicode isolate characters

---

## Translation Quality Checks

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

---
## i18n Checklist

- [ ] All user-visible strings use translation keys, not hardcoded text
- [ ] Date, number, and currency formatting uses locale-aware APIs
- [ ] Pluralization uses ICU MessageFormat or equivalent
- [ ] String concatenation is never used to build translated sentences
- [ ] RTL layout is supported via CSS logical properties
- [ ] Fonts support all target language character sets
- [ ] UI accommodates text expansion (German text is ~30% longer than English)
- [ ] Translation keys are namespaced and descriptive
- [ ] Fallback language is configured for missing translations
- [ ] No locale assumptions are hardcoded (date format, currency, sort order)
