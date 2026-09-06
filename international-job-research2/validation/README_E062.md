# E0.6.2 fresh-blind validation boundary

`validation/e062_candidate_freeze.json` is the authoritative freeze manifest for E0.6.2.

The historical labeled sets used during E0.6.2 development are burned and may only be used for regression/development evidence. They must not be reused as promotion evidence.

The next promotion-valid evidence must use a production inventory collected after the E0.6.2 freeze is merged to `main`, with human labels locked without inspecting E0.6.2 predictions. The exact frozen evaluator blob must then be scored once against the predeclared gate. Until that gate passes, E0.6.2 remains `NOT_PROMOTED` and the final holdout remains sealed.
