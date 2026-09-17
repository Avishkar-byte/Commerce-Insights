# Dashboard assets

## brazil_states.geojson

Boundaries of the 26 Brazilian states plus the Federal District (27 features),
used by the delivery page (F2) to draw late rate by customer state.

| | |
| --- | --- |
| Source | https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson |
| Project | Code for America, "Click That 'Hood" |
| Licence | MIT (see https://github.com/codeforamerica/click_that_hood) |
| Downloaded | 17 September 2026 |
| Join key | `properties.sigla`, the two-letter state abbreviation (`SP`, `RJ`, ...) |

The map joins `properties.sigla` to the `customer_state` field in
`order_metrics`. States with fewer than 100 delivered orders in the current
selection are drawn in the neutral grey `#8A94A6` rather than on the delay
colour scale, because a late rate from a handful of orders is not meaningful.

If this file is missing, the delivery page falls back to a horizontal bar
chart, so the page still works.
