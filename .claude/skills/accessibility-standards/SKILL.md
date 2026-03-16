---
name: accessibility-standards
description: "Use when implementing or reviewing UI components - WCAG 2.1 AA compliance and ARIA patterns"
user-invocable: false
---

# Accessibility Standards

## Core Principle

**Accessibility is not optional.** Every user interface must be usable by people with diverse abilities. Design for accessibility from the start -- retrofitting is expensive and incomplete.

---

## WCAG 2.1 AA Requirements

### The Four Principles (POUR)

| Principle | Meaning | Key Requirements |
|---|---|---|
| **Perceivable** | Content must be presentable to all senses | Text alternatives, captions, contrast |
| **Operable** | Interface must be navigable by all input methods | Keyboard access, timing, seizure safety |
| **Understandable** | Content and operation must be clear | Readable, predictable, error assistance |
| **Robust** | Content must work with assistive technologies | Valid markup, ARIA, name/role/value |

### Critical AA Success Criteria

| Criterion | Requirement |
|---|---|
| 1.1.1 Non-text Content | All images have meaningful alt text (or empty alt for decorative) |
| 1.3.1 Info and Relationships | Semantic HTML conveys structure (headings, lists, tables) |
| 1.4.3 Contrast (Minimum) | Text contrast ratio at least 4.5:1 (3:1 for large text) |
| 2.1.1 Keyboard | All functionality available via keyboard |
| 2.4.3 Focus Order | Tab order follows logical reading order |
| 2.4.7 Focus Visible | Keyboard focus indicator is always visible |
| 3.3.1 Error Identification | Errors are clearly described in text |
| 4.1.2 Name, Role, Value | All UI components have accessible names and roles |

---

## ARIA Patterns

### When to Use ARIA

**First rule of ARIA: do not use ARIA if native HTML provides the semantics.**

| Need | Use Native HTML | Use ARIA Only When |
|---|---|---|
| Button | `<button>` | Custom element must behave as button |
| Navigation | `<nav>` | Complex navigation widget |
| Dialog | `<dialog>` | Custom modal implementation |
| Tab panel | N/A | `role="tablist"`, `role="tab"`, `role="tabpanel"` |
| Alert | N/A | `role="alert"` for dynamic notifications |

### Common ARIA Attributes

| Attribute | Purpose | Example |
|---|---|---|
| `aria-label` | Accessible name when no visible text | `<button aria-label="Close">X</button>` |
| `aria-labelledby` | Name from another element | `<div aria-labelledby="heading-id">` |
| `aria-describedby` | Additional description | `<input aria-describedby="help-text">` |
| `aria-expanded` | Disclosure state | `<button aria-expanded="false">Menu</button>` |
| `aria-hidden` | Hide from assistive technology | `<span aria-hidden="true">decorative</span>` |
| `aria-live` | Dynamic content updates | `<div aria-live="polite">Status: updated</div>` |
| `aria-required` | Required field | `<input aria-required="true">` |

---

## Focus Management

### Rules

- **NEVER remove focus outlines** without providing an alternative visible indicator
- **ALWAYS trap focus** inside modal dialogs (tab cycles within the dialog)
- **ALWAYS return focus** to the triggering element when a dialog closes
- **ALWAYS manage focus** when content changes dynamically (route changes, loaded content)

### Focus Trap Pattern for Modals

```
1. User opens modal -> focus moves to first focusable element in modal
2. Tab at last element -> focus wraps to first element
3. Shift+Tab at first element -> focus wraps to last element
4. Escape key -> close modal, return focus to trigger button
```

---

## Keyboard Navigation

### Required Keyboard Support

| Action | Key(s) |
|---|---|
| Navigate between focusable elements | Tab / Shift+Tab |
| Activate buttons and links | Enter or Space |
| Navigate within widget (tabs, menus) | Arrow keys |
| Close overlay / cancel | Escape |
| Select option | Enter or Space |

### Custom Widget Keyboard Patterns

| Widget | Keys | Behavior |
|---|---|---|
| Tab panel | Left/Right arrows | Switch between tabs |
| Menu | Up/Down arrows | Navigate items |
| Combobox | Down arrow | Open dropdown |
| Tree view | Left/Right arrows | Expand/collapse nodes |
| Date picker | Arrow keys | Navigate calendar grid |

---

## Screen Reader Testing

### What to Verify

- [ ] All interactive elements announce their name and role
- [ ] Form inputs are associated with labels (via `for`/`id` or wrapping `<label>`)
- [ ] Error messages are announced when they appear (`aria-live` or focus management)
- [ ] Dynamic content changes are communicated (`aria-live` regions)
- [ ] Decorative images are hidden (`alt=""` or `aria-hidden="true"`)
- [ ] Headings create a logical document outline (h1 -> h2 -> h3, no skipped levels)
- [ ] Tables have headers (`<th>`) and captions when appropriate
- [ ] Page regions use landmarks (`<main>`, `<nav>`, `<aside>`, `<footer>`)

### Common Screen Readers

| Reader | Platform | Testing Notes |
|---|---|---|
| VoiceOver | macOS/iOS | Built-in, Cmd+F5 to toggle |
| NVDA | Windows | Free, widely used |
| JAWS | Windows | Most common in enterprise |
| TalkBack | Android | Built-in, in accessibility settings |

---

## Accessibility Checklist

Before considering a UI component complete:

- [ ] Color contrast meets 4.5:1 (text) and 3:1 (large text, UI components)
- [ ] All functionality is keyboard accessible
- [ ] Focus order is logical and visible
- [ ] Images have appropriate alt text
- [ ] Form inputs have associated labels
- [ ] Error messages are descriptive and announced
- [ ] ARIA attributes are correct and complete
- [ ] Tested with at least one screen reader
- [ ] No content flashes more than 3 times per second
- [ ] Touch targets are at least 44x44 CSS pixels
