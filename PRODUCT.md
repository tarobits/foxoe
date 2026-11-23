# FoxOE — Fox Operating Environment

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Confirmed: Python/FastAPI service, Vue/TypeScript frontend, and a Chromium
extension.

## Users

People using the owner's Raspberry Pi touchscreen kiosk to open and operate
applications, initially the existing label printer application.

## Product Purpose

Provide one kiosk environment with a touch dashboard and an Elgato Stream Deck
whose buttons adapt to the application currently displayed in the browser.
The dashboard is both a useful display and an application launcher.

## Operating Context

- Raspberry Pi 3B+ with a 1024×600 touchscreen and Chromium in kiosk mode.
- Elgato Stream Deck MK.2 connected to the Pi.
- Applications open in the same browser window.
- The label printer application already exists; its integration is separate from
  implementing the kiosk environment.
- This is a fresh implementation in the current workspace. Preserve the older
  sibling FoxOE project without modifying or importing its runtime data.

## Capabilities and Constraints

- Launch applications from both the touchscreen dashboard and the Stream Deck.
- Let the active kiosk application supply button layouts and receive actions.
- Support temporary interactions such as a numeric keypad.
- Provide a way back to the Home dashboard.
- Initially support control by the active application only. Remote services and
  background applications do not need control of the Stream Deck.
- Keep application input and physical controls synchronized through an API.
- Do not commit, push, or publish without explicit user consent.
- Keep the dashboard lightweight enough for the Pi 3B+.
- The Home screen has customizable information widgets above a separate,
  permanent app-launcher dock. Widgets may display external API data, including
  queues, or system statistics without opening an application.
- Apps on other machines may register automatically using a setup credential,
  providing named screens and raster images for the Stream Deck. Per-app update
  credentials isolate subsequent changes. Registration does not grant background
  control of the deck.
- The user approved HTTP/HTTPS host permissions for the extension in a dedicated
  kiosk browser profile so newly registered origins can integrate automatically.

## Brand Commitments

The product name is FoxOE, meaning Fox Operating Environment. The user supplied
DESIGN.md from Taro's Label Room as the visual authority: dark slate surfaces,
indigo actions, Heroicons, modest radii, and its existing motion vocabulary.
Its historical source paths describe the reference application, not this fresh
implementation. Adapt the composition for the kiosk without changing its palette.
FoxOE is licensed under PolyForm Noncommercial 1.0.0, as explicitly selected by
the user. Preserve third-party dependencies' separate license notices.

## Evidence on Hand

The user confirmed the MK.2 device, Chromium kiosk mode, touch launching, and
the decision to build fresh. The current workspace started empty. No physical
device connection or Pi access has been verified in this workspace.

## Product Principles

- Treat touch and physical buttons as complementary controls for the same tasks.
- Keep the current application and displayed Stream Deck actions consistent.
- Make application integrations small and explicit.
- Keep everyday kiosk controls concise and easy to operate by touch.
