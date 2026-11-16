# ClinicFlow Design Rules

ClinicFlow should look like serious clinical software that someone designed on purpose. It should not look like a SaaS starter template or something an AI produced in one pass. Receptionists and practitioners use it all day under time pressure, so put clarity, density and safety ahead of decoration.

If this file and `docs/BLUEPRINT.md` §9 disagree, this file wins.

---

## 1. Typography

### Typefaces

| Use | Typeface | Notes |
|---|---|---|
| UI and body text | **IBM Plex Sans** | 400 and 500 for text, 600 for headings |
| Headings | **IBM Plex Sans** 600 | Same family as body. Hierarchy comes from size and weight, not a second display font |
| Data, IDs, amounts, times, codes | **IBM Plex Mono** | Patient numbers, invoice numbers, ICD codes, NAD amounts in tables |

**Why not Inter or Manrope:** Inter is the default typeface of almost every AI-generated and shadcn-template interface, and Manrope is common on AI-built landing pages. Together they make the product look generic straight away. IBM Plex is a coherent sans and mono family. It has true tabular figures, an unambiguous `0/O` and `1/l/I`, and an institutional, technical feel that suits healthcare.

**Optional:** for the mobile patient portal, you can use **Atkinson Hyperlegible** (designed for low-vision readers) for body text if user testing supports it.

### Banned typefaces

Don't use these anywhere in the product: Inter, Manrope, Poppins, Plus Jakarta Sans, DM Sans, Outfit, Sora, Space Grotesk, Geist, Montserrat, Nunito, Roboto, or the system font stack as a "design choice".

### Rules

- Load fonts with `next/font` (self-hosted, `display: swap`). Use only the weights you need: 400, 500 and 600, plus 400 for Mono.
- Type scale for the desktop app, in px: 12 / 13 / 14 / 16 / 18 / 22 / 28. Base size is **14px**, because these are dense data screens. The patient portal uses a 16px base.
- Use `font-variant-numeric: tabular-nums` on every number in tables, calendars, queues and invoices.
- Use sentence case for headings, buttons and labels. No ALL CAPS except short table column headers at 12px with letter spacing.
- No gradient text, no oversized marketing headings inside the app, and no emoji in UI text.

---

## 2. Colour

### Tokens

Define these as CSS variables in `globals.css` and map them into Tailwind. **Never use Tailwind's default palette classes** (`indigo-500`, `slate-700`, `violet-600`, `emerald-400` and so on) in components. Use only tokens.

| Token | Value | Use |
|---|---|---|
| `--primary` | `#126B67` | Primary actions, active navigation, focus ring, links |
| `--primary-hover` | `#0E5653` | Hover and pressed state |
| `--primary-subtle` | `#E3F0EF` | Selected rows, active tab background |
| `--secondary` | `#527F9B` | Fills, borders and non-text accents only |
| `--secondary-text` | `#416B86` | Secondary text in the accent colour (passes AA) |
| `--background` | `#F5F8F8` | App background |
| `--surface` | `#FFFFFF` | Panels, tables, forms |
| `--surface-muted` | `#EEF3F3` | Table header, sidebar, read-only fields |
| `--border` | `#D5DFDF` | Dividers and input borders |
| `--text` | `#203334` | Body text |
| `--text-muted` | `#586C6D` | Secondary text and helper text |
| `--success` / `--success-text` | `#26856B` / `#1F6F59` | Completed, paid, signed |
| `--warning` / `--warning-text` | `#D69A38` / `#8F6419` | Pending, due soon, expiring licence |
| `--danger` / `--danger-text` | `#C64E4E` / `#A33A3A` | Allergies, rejected, overdue, destructive actions |

**Contrast:** the base `--warning` (2.3:1), `--secondary`, `--success`, `--danger` and the blueprint's `#687C7D` muted text fail WCAG AA (4.5:1) as small text on the app background. Use them for fills, icons, borders and badge backgrounds. Use the `-text` variants for text. All `-text` tokens and `--text-muted` pass AA on both `--surface` and `--background`.

### Rules

- **No gradients.** That includes backgrounds, buttons, headers and text.
- No purple, indigo or violet anywhere. These are the strongest marker of an AI-generated UI.
- No glassmorphism, `backdrop-blur` panels, glows, neon accents or coloured shadows.
- Colour carries meaning. Use `--primary` for interaction and status colours for state. Never use colour for decoration.
- **Never use colour alone.** Every status also has a text label, and usually an icon. Clinicians may be colour-blind, and printouts are often greyscale.
- Red is reserved for clinical risk (allergies, critical results) and destructive actions. Don't use red for "Cancelled" appointments; that is neutral grey.
- Light theme only for v1. Don't build a dark mode until there is a real requirement.

---

## 3. Icons

- **One set: Lucide.** Stroke width **1.5** everywhere, sizes **16px** inline and in tables, **20px** in navigation. Never mix icon sets.
- An icon appears only where it helps scanning: navigation, status, and common row actions. Don't put icons on every heading, card title or form label.
- Icon-only buttons are allowed only for universally understood actions (close, more, edit in a table row). They need an `aria-label` and a tooltip.
- Icons inherit `currentColor`. No multi-colour icons, no icons in coloured circles or rounded squares, no decorative icon tiles on dashboard cards.

### Banned icons and patterns

- `Sparkles` and similar "AI magic" icons. There are no AI features, so never imply them.
- `Rocket`, `Zap`, `Flame` and `Crown`, used for marketing tone.
- Emoji as icons, including 👋 greetings, ✅ and 🚀.
- Medical clip-art clichés used as decoration: stethoscope logos on every page, heartbeat lines, floating pills, cartoon doctors.

---

## 4. Banned generic-AI patterns

Don't produce any of the following:

- **The KPI card grid:** four rounded cards with a big number, an icon in a tinted circle, and a fake "+12.5% from last month" trend. Show real metrics only when there is real data and a reason to show them, usually in a table or a single compact summary row.
- **"Welcome back, Dr. Smith 👋"** headers and other cheerful greetings. Open on the work: today's list, the queue.
- `rounded-2xl` cards with drop shadows wrapping every section. Default radius is **6px**, or 4px for inputs and badges. Prefer flat panels with a 1px `--border` and no shadow. Use a shadow only for floating layers (popovers, dialogs, dropdowns).
- Stock shadcn styling left unchanged. Restyle components to these tokens, radius and density.
- Marketing copy inside the app, such as "Streamline your workflow", "Supercharge your practice" or "Seamlessly manage…". Use plain, specific labels.
- Huge padding and whitespace in data views, or tables with 64px rows. Reception needs to see as many rows as possible.
- Decorative charts with no decision behind them, donut charts of trivial splits, and sparklines everywhere.
- Hover scale or bounce animations, parallax, confetti, and animated gradient borders. Motion is limited to a 120–180 ms ease on opacity and position for overlays and state changes, and it respects `prefers-reduced-motion`.
- Blob shapes, 3D illustrations, isometric people and abstract background art.
- Pill badges on everything, and avatars with gradient rings.
- Centred layouts for application screens. App screens are left-aligned and grid-based.
- Placeholder data that looks real, such as "John Doe" or "Acme Clinic", in shipped UI. Use clearly synthetic seed data and keep it in fixtures only.

---

## 5. Layout and density

- **Desktop app:** a left sidebar (collapsible, 220px), a top bar with branch switcher, patient search and user menu, and a content area with a 24px gutter.
- Base spacing unit is **4px**. Common gaps are 8, 12, 16 and 24.
- **Tables are the primary component.** Use 36–40px rows at default density, sticky headers, right-aligned numbers, monospace IDs and amounts, sortable columns, and pagination. A compact density toggle is welcome.
- Forms are single-column on narrow screens and two-column on wide ones. Labels go above fields and are always visible; never use placeholder-only labels. Required fields are marked. Errors appear inline and are linked with `aria-describedby`.
- **Reception and administration** are designed for 1366×768 and up.
- **Doctor screens** must also work on a tablet.
- **The patient portal** is mobile-first: designed from 360px wide, with touch targets of at least 44px.

---

## 6. Clinical safety UI

These are required on every clinical screen:

- **Patient identity banner** pinned at the top of every patient-context screen. It shows full name, date of birth with age, sex, and patient number in monospace. This prevents documenting on the wrong patient.
- **Allergy indicator** in the identity banner. It uses `--danger` with the text "Allergies:" followed by the substances, or an explicit "No known allergies" or "Allergies not recorded". It must never be blank.
- Clinical note state (Draft, Signed or Amended) is always visible with its signer and timestamp. A signed note is visibly read-only.
- Destructive or irreversible actions (sign note, cancel prescription, void invoice, merge patients) need a confirmation dialog that names the object, such as "Sign note for Jane N. Shikongo (P-000231)?". Never use a generic "Are you sure?".
- When a staff member uses break-glass access, a persistent warning bar shows for the rest of the session.

---

## 7. Content and formatting (Namibia)

- **Currency:** `N$1,250.00`, always with two decimals. In tables, right-align and use monospace.
- **Dates:** `16 Nov 2026` in the UI and `2026-11-16` in exports. No US formats.
- **Time:** 24-hour (`14:30`). Default timezone is `Africa/Windhoek`.
- **Phone numbers:** stored as E.164 (`+264…`), displayed grouped.
- **Spelling:** British English (organisation, licence, cancelled, colour), matching the blueprint.
- **Voice:** plain, neutral and clinical. Name things the way clinic staff do, such as "Check in", "Medical aid" and "Cash-up".
- Empty states say what is missing and give the next action, for example: "No appointments today. Book appointment". No illustrations.

---

## 8. Accessibility (minimum bar)

- WCAG 2.2 AA. Every text and token pairing meets 4.5:1, or 3:1 for large text and UI component boundaries.
- Visible focus ring on every interactive element: 2px `--primary` with a 2px offset.
- Full keyboard operation of the calendar, queue and tables.
- Status is announced to screen readers (`aria-live` for queue updates and toast messages).

---

## Review checklist for UI changes

Before you finish any UI work, check:

- [ ] Only tokens are used. No raw hex values and no Tailwind default palette classes in components.
- [ ] Only IBM Plex Sans and IBM Plex Mono. Numbers use tabular figures.
- [ ] No gradients, no purple, no glass or glow, and no emoji.
- [ ] Lucide icons only, at stroke 1.5, and only where they help.
- [ ] No KPI-card grid, no greeting header, and no marketing copy.
- [ ] Status shows text as well as colour.
- [ ] Patient identity banner and allergy indicator appear on clinical screens.
- [ ] Layout works at 1366px (staff) or 360px (patient portal).
- [ ] Keyboard and focus states work.
