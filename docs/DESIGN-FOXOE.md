---
name: FoxOE
description: Kiosk adaptation of the supplied Taro's Label Room visual system.
---

## Overview

FoxOE inherits its visual identity from the user-supplied [DESIGN.md](../DESIGN.md).
That document remains unchanged and authoritative for palette, typography,
controls, icons, focus treatment and motion. Its historical implementation links
refer to the reference application, not files to recreate in this project.

This supplement records the implemented kiosk composition. It does not replace
the inherited design system or establish a new visual identity. Product scope is
in [PRODUCT.md](../PRODUCT.md); the Home composition is recorded in the
[surface brief](../.impeccable/surfaces/home.md).

Source review on 2026-11-23 covered [shared styles](../frontend/style.css), the
[application shell](../frontend/App.vue), [widgets](../frontend/WidgetContent.vue),
[icons](../frontend/Icon.vue) and [English/German copy](../frontend/i18n.ts).
This is a code-level record, not a claim of browser accessibility, physical
Stream Deck operation or Raspberry Pi performance verification.

## Colors

The inherited dark slate palette is retained: dense canvas, raised widget
surfaces, deepest dock, indigo actions and brighter indigo focus treatment.
The CSS custom properties use the corresponding values from DESIGN.md.
Green indicates a connected device; red accompanies error text. Missing and
stale widget data have textual states rather than invented values.

Application-provided raster icons are content, separate from the shell palette.
The FoxOE brand mark uses the user's orange fox illustration, with its original
paths and gradient, without the source artwork's background or wordmark. This
brand accent does not replace indigo action controls. Stream Deck action symbols
use the same Heroicons as the dashboard; Home uses a house symbol.

## Typography

The Inter/system stack and the inherited page and section heading styles remain.
For the touch kiosk, body and form-control text use 16px rather than the
reference application's 14px body text. Field labels use 14px. Page headings
reduce from 31px to 27px at the kiosk layout's 700px breakpoint.

Clock and metric values use larger, tabular numerals. These are information
widgets, not a new general heading scale. Text widgets preserve line breaks;
resource values and names wrap within their available space. Launcher names
truncate within bounded tiles.

## Layout

The reference application's sidebar is replaced by the user-selected Home
composition: a compact header, a fitted widget canvas and a separate bottom
application dock. Home widgets do not scroll. Settings
use a separate scrolling region with sticky tabs; the Home dock is not displayed
in settings.

The widget grid has 24 columns, 48px row tracks and 8px gaps. Its logical canvas
is at least 968px wide and extends through the last occupied row. The entire
canvas, including widget contents, scales down uniformly to fit the available
space above the dock. Saved coordinates are unchanged; pointer movement accounts
for the scale. Widget padding is configurable (24px by default). The shell uses
the viewport height with a 400px minimum, and its header has 28px horizontal
padding. Dashboard and widget content overflow cannot be scrolled.

At widths of 700px or less, widgets retain their grid layout, shell spacing
contracts, forms wrap and the dock scrolls horizontally. Pointer drag/resize
handles are hidden at this breakpoint; the widget dialog retains numeric
position and size controls. Dock device status is hidden on narrow screens;
connection details remain available in system settings.

## Elevation & Depth

Widget panels use tonal separation and a fine border without the reference
application's small panel shadow. The toast has a restrained shadow; the native
dialog uses a dark backdrop. There is no decorative blur or illustrative layer.

## Shapes

Controls retain 6px corners; widget panels, dock tiles and app symbols use 8px
corners. These modest rounded rectangles extend the supplied visual language.
Controls use the Heroicons 24px outline family. Decorative icons are hidden from
assistive technology; icon-only actions receive translated accessible names.

## Components

Primary, secondary and inline actions preserve the inherited fill and text
roles. General buttons and form controls have 48px minimum heights. Widget
drag/resize controls have 44px minimum targets. Keyboard focus retains the 3px
indigo outline with a 3px offset; disabled controls use 0.45 opacity.

The widget editor uses a native modal dialog. Opening uses the inherited 240ms
arrival and closing retains the dialog for the inherited 100ms departure.
Reduced motion disables CSS movement and removes the JavaScript closing delay.
Home/settings and settings sections use matching surface transitions; notices
and credential disclosures use opacity transitions. Buttons retain the 0.98
press scale. All six inherited motion duration tokens and the shared easing
curve are defined in the stylesheet.

Widget contents update in place during polling. Keyed widgets use a transition
group with the existing surface arrival and departure styles. The editing
toolbar, widget controls and Home dock use the existing notice opacity
transitions for appearance and removal. Native dialog behavior supplies modal
focus handling; this source review does not establish rendered focus restoration
in every interaction.

Interface copy is supplied by the existing English/German translation catalog.
User-provided widget titles, application names and content are displayed as
content rather than translated UI labels.

## Do's and Don'ts

- Extend the supplied visual system and reuse the shared CSS before introducing
  another style variant.
- Keep the Home dock outside the scaled, non-scrolling widget canvas.
- Preserve 44px or larger interaction targets and room for focus outlines.
- Keep operational states explicit and interface copy concise and translated.
- Use the existing timing and easing tokens for new transitions, including
  closing states and reduced motion.
- Verify 1024×600 and narrow layouts, long content, keyboard interaction and
  opening/closing behavior when modifying the shell.
- Do not treat source-level consistency as proof of accessibility or hardware
  performance.
- Do not overwrite the supplied DESIGN.md when documenting FoxOE adaptations.
