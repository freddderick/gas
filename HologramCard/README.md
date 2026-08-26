# Reflective Hologram Card

A holographic trading card — *Aurora Drake*, 130 HP, ★★★ Secret Rare — that tilts,
catches the light, and casts a reflection on the surface below. One HTML file: no
build step and no dependencies. The only external request is the Archivo webfont,
which falls back cleanly to system faces offline.

```sh
open HologramCard/index.html      # macOS
xdg-open HologramCard/index.html  # Linux
```

## What it does

- **3D tilt** driven by the pointer, arrow keys, or (on a phone) the gyroscope.
- **Four foils** — Rainbow, Cosmos, Prism and Gold — swapped from the button row.
- **Flip** to the card back, which is holographic too.
- **Reflection**: a live mirrored copy of the card, plus a pool of coloured light
  that shifts hue with the tilt.
- Card art is hand-written SVG (aurora, moon, drake, ridges, lake) — no images.

## How the hologram works

The effect is four stacked layers inside each card face, composited with CSS blend
modes. All of them read the same custom properties, which JavaScript writes once
per animation frame:

| Property          | Meaning                                  |
| ----------------- | ---------------------------------------- |
| `--px` / `--py`   | pointer position over the card, `0..1`   |
| `--rx` / `--ry`   | tilt angles derived from those           |
| `--active`        | `1` while the card is being tilted        |
| `--flip`          | `0deg` or `180deg`                        |

1. **`.foil`** — two repeating gradients (a coloured band pattern and a darker
   streak pattern) blended with `background-blend-mode`, then blended onto the card
   with `mix-blend-mode`. Its `background-position` is a function of `--px` / `--py`,
   so the bands slide *against* the tilt the way real foil does. `filter: contrast()`
   crushes the mid-tones so the bands stay bright instead of turning to mush.
2. **`.sparkle`** — an inline SVG `feTurbulence` noise texture, crushed with
   `contrast(5)` into isolated glitter specks and tinted by a rotating conic gradient.
3. **`.glare`** — a radial highlight centred on the pointer, blended with `overlay`.
4. **`.edge`** — the bevel, plus a light bar that sweeps the border as you tilt.

Each finish only overrides the two gradients, the blend modes and a brightness
multiplier — see the `.stage.finish-*` rules. `color-dodge` can only brighten, which
turns warm foils pink over a violet card, so Gold and Cosmos use `hard-light` instead.

The reflection is a `cloneNode(true)` of the whole card placed *outside* `.deck` but
*inside* `.stage`, so it inherits every one of those custom properties for free and
stays in sync with no extra JavaScript. Its wrapper flips it with `scaleY(-1)`,
inverts `--rx`, and clips it to the top third behind a `mask-image` fade.

## Accessibility

- The card is focusable: arrow keys tilt it, Enter or Space flips it, and it carries
  an `aria-label` describing the card.
- `prefers-reduced-motion: reduce` drops the idle float and the tilt easing.
- The reflection is `aria-hidden` and `inert`, so the clone is invisible to assistive
  tech and to the tab order.
- Card text sits above the foil on a dark plate so it stays legible at every tilt.

## Layout notes

The card is sized from a single `--w` custom property on `.stage` (clamped between
258px and 320px) and everything else — height, type scale, reflection height — is
derived from it, so the whole thing scales by editing one value.

## Browser support

Needs `mix-blend-mode`, `backdrop-filter`, `aspect-ratio` and `mask-image`: current
Chrome, Safari and Firefox. iOS Safari gates `deviceorientation` behind a user
gesture, which is what the **Use device tilt** button (touch devices only) is for.
