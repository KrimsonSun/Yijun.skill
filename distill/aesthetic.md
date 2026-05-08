# Aesthetic — Glassmorphic Pink

Source of truth: `frontend/src/App.css` in `Emma_EmotionsAssistant`. This file is the contract — any new component (game panel, MCP control, modal) **must** use these tokens. The rubric checks computed colors and effects against the values below.

> Last distilled from: `frontend/src/App.css`. Re-run Phase 1 to refresh.

---

## CSS variables (canonical)

```css
:root {
  /* Primary pink palette */
  --primary-color: #ff69b4;        /* hot pink — buttons, accents, emoji-tone */
  --primary-light: #ffb3d9;        /* hover/active glow */
  --primary-dark:  #ff1493;        /* pressed states */

  /* Background */
  --bg-color: #fce4ec;             /* page bg — never pure white */

  /* Glass surfaces */
  --glass-bg:     rgba(255, 255, 255, 0.6);
  --glass-border: rgba(255, 255, 255, 0.7);

  /* Chat bubbles */
  --user-bg:      rgba(255, 230, 240, 0.75);   /* user messages */
  --assistant-bg: rgba(255, 255, 255, 0.85);   /* Emma's messages */

  /* Shadow — pink-tinted, not gray */
  --panel-shadow: 0 8px 32px 0 rgba(255, 105, 180, 0.15);
}
```

**Rules for new components:**
- **Never** use `#ffffff` directly. Always reach for `--glass-bg` or `--assistant-bg`.
- **Never** use a gray shadow. Always `--panel-shadow` or a variant tinted with `rgba(255,105,180,*)`.
- **Never** use Material/Bootstrap/Tailwind defaults — they'll clash with the pink saturation.

---

## Effects

### Backdrop blur

Every "panel" surface (chat panel, MCP panel, game panel, modal) uses:

```css
backdrop-filter: blur(20px);
-webkit-backdrop-filter: blur(20px);
background: var(--glass-bg);
border: 1px solid var(--glass-border);
border-radius: 16px;
box-shadow: var(--panel-shadow);
```

The 20px blur is the visual identity. **Don't** lower it for "performance" — lower it only if the eval flags Live2D fps regression on the canvas.

### Animations

```css
@keyframes slideIn {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Apply to: new chat bubbles, mounted panels, modal entrance */
.bubble, .panel-enter { animation: fadeInUp 0.3s ease-out; }
.notification         { animation: slideIn 0.3s ease-out; }
```

Duration is **always 0.3s** for chat-adjacent UI. Game panels can use 0.4s if mounting heavier widgets.

### Paw-print marquee

A subtle 🐾 marquee scrolls across the chat background at `opacity: 0.15`. This is a **must-have** identity element — the rubric checks for it.

```css
.paw-marquee {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.15;
  font-size: 18px;
  white-space: nowrap;
  animation: pawScroll 60s linear infinite;
}

@keyframes pawScroll {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}
```

Content: `🐾 🐾 🐾 ` repeated to fill viewport width × 2.

---

## Typography

```
font-family: 'PingFang SC', 'Microsoft YaHei', -apple-system, sans-serif;
header:  26px / 700
body:    14px / 400
caption: 12px / 400
```

CN font stack first; the system stack fallback only matters for English-only screens.

---

## Live2D canvas

```
size: 350px × 500px
shader precision: MEDIUMP
position: bottom-right of viewport, z-index above bg, below modals
```

Canvas attribute `data-current-motion` reflects the most recently played motion (added by skill — `Live2DViewer.jsx` patch). The Playwright eval polls this attribute to verify MCP-triggered animations fired.

---

## Breakpoints

```css
@media (max-width: 1024px) { /* tablet — Live2D scales to 280×400, MCP panel collapses */ }
@media (max-width: 768px)  { /* mobile — Live2D becomes a 200×280 corner avatar, paw marquee hidden */ }
@media (max-width: 480px)  { /* small mobile — single-column, tabs replace side panels */ }
```

Do **not** add intermediate breakpoints. If a new panel needs a different layout, it lands inside one of these three.

---

## Forbidden aesthetic shifts

- Dark mode: not currently in scope. If added later, build a separate token set; do not mutate `--bg-color` to dark — the pink palette breaks.
- Other primary colors: blue / purple / green primaries break warmth. If a sub-feature needs differentiation, use `--primary-light` shade variations only.
- Sharp corners / heavy shadows: the identity is soft. `border-radius` minimum is `12px`; max `24px`.
- Stroked / outlined buttons as primary CTA: always solid pink fill on primary actions.

---

## Rubric mapping

The Playwright `aesthetic.spec.ts` checks:
- `.user-bubble` background sample falls within ΔE<3 of `--user-bg`.
- `.paw-marquee` element exists and has `opacity` between 0.1 and 0.2.
- Any `.panel` has `backdrop-filter` containing `blur(20px)`.
- `data-current-motion` attribute exists on Live2D canvas.
- No element has `box-shadow` with gray rgba (`rgba(0,0,0,*)`); shadows must contain `255,105,180` or `--primary-*`.
