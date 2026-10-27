# Stagify identity

Stagify uses the user-supplied, hand-drawn crew of four penguins as its identity.
The black-and-white drawing replaces the earlier geometric logo explorations.

Assets under `docs/assets/brand/`:

- `stagify-original.jpg`: the supplied artwork, preserved without modification.
- `stagify-mark.png`: a transparent-background derivative for the documentation
  header and homepage, created with the built-in image-generation editor.

The transparent asset retains white interiors. Display it on a white surface so
the black outlines and all four penguins remain legible in either site theme.
The README and PyPI use the original white-backed artwork so their rendering
does not depend on host-specific dark-mode CSS.

The documentation identity is black, white, and neutral grays. Primary navigation,
sidebars, local search, code copy controls, and a page table of contents follow
familiar documentation conventions. Artwork and framework branding remain Stagify's.

Background removal prompt: see [image-edit-prompt.md](image-edit-prompt.md).
