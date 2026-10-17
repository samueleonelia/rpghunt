# Test set

Hand-checked ground truth used to score the deal scraper at every build gate.

- `<date>.json`: real deals live on that date, found and verified by hand (Researcher agent). Each one must be found by the scraper.
- `<date>-fakes.json`: planted fake deals (`expected: "reject"`). Each one must be rejected. `fake_kind` says what is wrong.
- `fixtures/`: local fake shop pages for fakes that need a controlled page. A `fixture:<file>` URL means "serve this file locally".
- `<date>-sources.md`: where the real deals were found, and which sources blocked us.

Scores per gate: real deals found, real deals missed, fakes let through (must be 0).
