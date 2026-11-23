# FoxOE integration API

## Server registration

Send `POST https://<pi-host>:8766/v1/apps` with `Content-Type: application/json`
and `Authorization: Bearer <setup credential>`. The credential belongs on the
application server, never in client-side JavaScript.

```json
{
  "schemaVersion": 1,
  "id": "label-printer",
  "name": "Label printer",
  "url": "https://printer.example/app",
  "icon": "printer",
  "screens": [
    {
      "id": "print-actions",
      "buttons": [
        {"id": "print", "label": "Print", "icon": "printer"},
        {"id": "quantity", "label": "Quantity", "icon": "keypad"},
        null,
        {"id": "cancel", "label": "Cancel", "icon": "close", "disabled": true}
      ]
    }
  ]
}
```

Success is **201**, with `id`, `revision`, and an `appCredential` returned once.
Store that credential securely. A duplicate ID returns **409**; the setup
credential cannot overwrite an existing app.

To update, send the complete manifest to `PUT /v1/apps/{id}` using that app's
credential. Success is **200**. The ID must match; an app credential cannot update
another app. Removing an app through FoxOE Settings revokes its update credential.
Concurrent dashboard edits are protected by configuration revisions. An app's
registration update replaces its own manifest, not other apps or widgets.

Authentication errors return **401**; invalid manifests return **422**; oversized
bodies return **413**; too many active registration requests return **429**.
Failures return an `error` identifier, never credentials or submitted image data.
The API accepts at most two concurrent authenticated registration requests, a
2 MiB request body, 14 apps, 16 screens per app, and 14 configurable keys per screen.
Key 15 is always FoxOE Home. Buttons use row-major order on the 5×3 MK.2.

### Icons and text size

Applications and buttons accept `icon: null` for no built-in symbol and
`textSize` for the Stream Deck label size in pixels (integer **8–32**, default
**14**). Omitting `icon` preserves the default `window` icon. A `null` button
still means an empty, inactive slot; a button with `icon: null` remains clickable.

```js
await deck.show({ id: 'count', buttons: [
  { id: 'quantity', label: '42', icon: null, textSize: 32 },
  { id: 'profile', label: 'Profile', icon: 'user', textSize: 14 },
] });
await deck.updateButton('quantity', { textSize: 24, icon: null, image: null });
```

The same fields on the registration manifest configure its app launcher key.
Text size affects the physical keys and their preview, not touchscreen app labels.
Text wraps within the key and is truncated with an ellipsis when necessary.
Large text reduces the space available for its symbol. The reserved Home key
keeps its house icon and default size.

Every Heroicons 24px outline icon is supported, including `user`, `users`,
`user-circle`, `folder`, `lock-closed`, `power`, and `academic-cap`.
Use the exact identifiers from [the icon catalog](../foxoe/icon_catalog.json),
also searchable in dashboard settings. Catalog keys are API identifiers;
values are upstream Heroicons component names. Existing aliases (`keypad`,
`close`, `back`, `reload`, `settings`, `edit`, `remove`, `resize`, `move`, `system`)
remain supported, along with the `foxoe` brand mark. Unknown names and empty
strings are rejected; use JSON `null` to hide the icon.

### Images

Applications can register custom launcher and button icons in the same request.
The launcher uses the app's `image` field; each screen button can reference its
own uploaded `image`. The same asset name can be reused by multiple buttons:

```js
manifest.images = {
  appLogo: `data:image/png;base64,${appLogoBytes.toString('base64')}`,
  print: `data:image/png;base64,${printIconBytes.toString('base64')}`,
};
manifest.image = 'appLogo';
manifest.screens = [{
  id: 'main',
  buttons: [{ id: 'print', label: 'Print', icon: 'printer', image: 'print' }],
}];
```

Custom artwork fills the physical key. Without an `image`, FoxOE draws the
selected built-in `icon` above its label, or centers the text when `icon` is null.
An uploaded `image` takes precedence over `icon` and `textSize`; clear `image`
as well for a text-only key.
The reserved Home key always uses a house icon. Custom assets remain scoped to
the registering app and can be replaced using its update credential.

PNG, JPEG, and WebP are accepted. SVG, animations, external image URLs, invalid
image references, decoded images over 1,048,576 pixels, and files over 256 KiB are
rejected. Each app may register up to 32 named images. FoxOE crops/resizes to
72×72, strips metadata by re-encoding, and stores normalized PNGs by content hash.
An image fills the physical key; its button label remains available in the UI
and action metadata. Disabled images are dimmed. Replacing or removing a manifest
prunes unreferenced image blobs transactionally.

## Active browser application

Bundle `sdk/foxoe.js` with the application's frontend. Do not load it from the
Pi's HTTP listener into a remote HTTPS page; the extension provides the bridge,
so the app needs no loopback network connection or credentials.

```js
import { createDeck, keypadLayout } from './foxoe.js';

const deck = createDeck();
const stopConnection = deck.onConnection(async connected => {
  if (connected) await deck.showScreen('print-actions');
});
const stopActions = deck.onAction(async ({ id, layout }) => {
  if (id === 'print') {
    await printCurrentLabel(); // Keep the app's existing validation/permissions.
    await deck.updateButton('print', { disabled: true });
  }
});

// A temporary layout preserves the current screen beneath it.
await deck.push(keypadLayout({
  backspace: translations.deleteDigit,
  cancel: translations.cancel,
  confirm: translations.confirm
}));
await deck.pop();

// On component teardown:
stopConnection();
stopActions();
deck.dispose();
```

Catch rejected promises when pages disconnect. A page can also call
`show({id, buttons})`, `push({id, buttons})`, `pushScreen(id)`, and
`updateButton(id, {label, icon, image, disabled, textSize})`. `show` replaces the layout
stack; `push` adds a temporary screen; `pop` restores the previous one. At most
eight layouts may be stacked. App-supplied labels should use that app's locale.
Image names must belong to the registered app.

The extension accepts messages only from the selected kiosk tab's top-level
current document. URL scopes match the configured origin and path segment:
`/app` permits `/app/jobs` but not `/app-elsewhere`. Other tabs, old documents,
unregistered URLs, and iframes cannot provide layouts. A registered screen is
not automatically active: the frontend chooses it when connected.

Changing pages or losing focus invalidates controls. Browser disconnects release
ownership. A press captured for an old layout generation is discarded, and Home
cannot be replaced by an application. Only one browser connection owns the deck.

## Local dashboard API

The dashboard uses `GET /api/config`, `PUT /api/config`, `GET /api/state`, and
`GET /api/data`. Writes require the exact local browser Origin and a matching
configuration `revision`; a stale revision returns **409**. These routes are not
the remote integration API. The local bridge token and registration credential
are deliberately different credentials with different endpoints and purposes.
