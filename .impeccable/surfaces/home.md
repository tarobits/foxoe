# FoxOE Home

Mode: Operate. Platform: web. Target: Raspberry Pi 3B+, 1024×600 touch display.

## Direction contract

The user selected information widgets above a separate, permanent app-launcher
dock. DESIGN.md is the visual authority. Retain its dark slate surfaces, indigo,
Heroicons, system/Inter font stack, rounded rectangles, focus treatment, and motion
timings. No palette replacement or illustrative artwork is needed.

The first viewport is the working dashboard: a compact FoxOE header with editing
and settings controls, a configurable 24-column information grid, and a dock of
touch launchers at the bottom. Scale the entire widget canvas and its contents
to fit above the dock without scrolling, preserving saved grid positions.
Widgets support clock, text, numeric values, and lists from local statistics or
configured JSON sources. Missing/stale data is explicit, never fabricated.

Editing permits rearranging/resizing widgets and choosing their content, while
configuration forms use the same visual language. Controls have at least 44px
touch targets (48px where practical), opening and closing transitions, and reduced
motion support. Narrow screens retain the fitted grid above the horizontal dock.
Widget controls scale with the canvas; header and dock controls remain unscaled.

Signature interaction: one application launch updates both the kiosk page and
the physical Stream Deck context. Information polling does not replay entrances.

FORM: user-selected dock layout after seed:a391c92a95e4b264 and a direct scope
clarification. Static preview: ../mocks/decision/split-dashboard.html. This is a
code-led screen; previews contain clearly labelled example data only.

Known verification limits: no Pi or physical Stream Deck connection is available
in this workspace; the in-app browser host was unavailable during layout choice.
