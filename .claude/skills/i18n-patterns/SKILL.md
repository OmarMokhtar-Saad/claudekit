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
