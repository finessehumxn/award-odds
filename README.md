# award-odds

Before you apply for a federal grant, see who actually won it.

## Why

Eligibility rules say who may apply. Award history says who does win. Those are different
groups, and the gap between them is where small organisations lose weeks on applications they
were never in the running for.

`award-odds` takes one federal assistance listing (the old CFDA number, such as `93.243`), pulls
the last few years of new grant awards from the public [USASpending.gov](https://www.usaspending.gov)
API, and reports who won: how many awards, how many distinct recipients, typical award size, how
concentrated the money is, the top recipients, and what kind of organisations they were. Give it
your organisation type and budget and it adds a fit readout where every factor shows the evidence
it came from and the rule it was judged by.

There is no language model in this tool. Retrieval decides.

This is a deliberately small, open-source slice of the idea behind MCGrantz, a commercial grant
tool by the same author. None of the product's scoring, data pipeline or prompts are in here.

## Quickstart

Requires Python 3.12. No API key.

```sh
git clone https://github.com/finessehumxn/award-odds
cd award-odds
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'

award-odds 10.310 --org-type nonprofit --budget 300000
```

Real output from 2026-10-07 (USDA's Agriculture and Food Research Initiative), lightly trimmed:

```
Assistance listing 10.310  |  new grant awards 2021-10-07 to 2026-10-07
Source: USASpending.gov (public API, no key)

AWARDS
  awards                 3,553
  unique recipients      414
  total award dollars    $1,963,397,862

AWARD SIZE (single-listing awards, n=3,421)
  p25                    $225,000
  median                 $500,000
  p75                    $650,000
  max                    $15,000,000

CONCENTRATION
  top 10 recipients took 30.5% of award dollars

TOP RECIPIENTS (by award dollars)
   1. OHIO STATE UNIVERSITY, THE                             68 awards       $68,725,981    3.5%
   2. PURDUE UNIVERSITY                                      94 awards       $67,577,248    3.4%
   3. TEXAS A&M AGRILIFE RESEARCH                            95 awards       $66,652,608    3.4%
   ...

RECIPIENT TYPE MIX (award counts, USASpending classification)
  nonprofit                  264    7.4%
  higher education         3,077   86.6%
  state government            10    0.3%
  business                    14    0.4%
  individuals                  2    0.1%
  no type recorded           186    5.2%

FIT FOR: nonprofit, budget $300,000
  [moderate] Recipient type
             evidence: 264 of 3,553 awards (7.4%) went to recipients classified as nonprofit
             rule:     strong if >= 20% of awards, weak if < 5%, else moderate
  [strong  ] Budget vs past awards
             evidence: $300,000 is inside the middle 50% of past awards (p10 $79,368, p25 $225,000, p75 $650,000, p90 $799,996; n=3,421)
             rule:     strong if inside the middle 50% (p25-p75), moderate if inside p10-p90, else weak
  [moderate] Concentration
             evidence: top 10 of 414 recipients took 30.5% of award dollars
             rule:     weak if top 10 recipients took >= 50% of dollars, strong if < 25%, else moderate

VERDICT: Possible
  fired: R4  Anything else -> Possible.
  ...

NOTES
  - 131 awards had a zero or negative amount (deobligations or corrections) and are left out of size and dollar figures.
  ...
```

The same listing for a local government asking for $2,000,000:

```
FIT FOR: local government, budget $2,000,000
  [weak    ] Recipient type
             evidence: 0 of 3,553 awards (0.0%) went to recipients classified as local government
  [weak    ] Budget vs past awards
             evidence: $2,000,000 is larger than 90% of past awards (p10 $79,368, p25 $225,000, p75 $650,000, p90 $799,996; n=3,421)
  [moderate] Concentration
             evidence: top 10 of 414 recipients took 30.5% of award dollars

VERDICT: Long shot
  fired: R1  Your type won under 5% of awards -> Long shot.
```

And SAMHSA's Projects of Regional and National Significance (`93.243`) for a nonprofit asking
for $250,000. Note the second line under NOTES, covered in Limits below:

```
AWARDS
  awards                 3,356
  unique recipients      2,020

AWARD SIZE (single-listing awards, n=2,463)
  p25                    $500,000
  median                 $1,342,107
  p75                    $2,267,002

FIT FOR: nonprofit, budget $250,000
  [strong  ] Recipient type
             evidence: 1,529 of 3,356 awards (45.6%) went to recipients classified as nonprofit
  [moderate] Budget vs past awards
             evidence: $250,000 is outside the middle 50% but inside p10-p90 (p10 $240,000, p25 $500,000, p75 $2,267,002, p90 $3,519,686; n=2,463)
  [moderate] Concentration
             evidence: top 10 of 2,020 recipients took 30.6% of award dollars

VERDICT: Good fit
  fired: R3  Your type won at least 20% of awards and no factor is weak -> Good fit.

NOTES
  - 286 awards had a zero or negative amount (deobligations or corrections) and are left out of size and dollar figures.
  - 612 awards (65.4% of award dollars) also carry money from other assistance listings. ...
```

Options:

```
award-odds LISTING [--years 5] [--org-type TYPE] [--budget DOLLARS] [--max-pages 50] [--json]

  --org-type   nonprofit | university | state_gov | local_gov | tribal | for_profit | small_business
  --budget     total you plan to request over the whole project period
  --max-pages  cap on 100-row pages fetched (default 50, i.e. 5,000 awards)
  --json       machine-readable output, including every factor and rule
```

## How the verdict is computed

Three factors, each rated strong, moderate or weak. Each one prints its evidence.

| Factor | Evidence | strong | moderate | weak |
|---|---|---|---|---|
| Recipient type | share of awards that went to your type | at least 20% | 5% to under 20% | under 5% |
| Budget vs past awards | where your budget falls in the award size distribution | inside p25 to p75 | inside p10 to p90 | outside p10 to p90 |
| Concentration | share of award dollars taken by the top 10 recipients | under 25% | 25% to under 50% | 50% or more |

The budget factor appears only with `--budget`. The verdict needs `--org-type`. Rules are applied
in order and the first match wins:

```
R1  Your type won under 5% of awards -> Long shot.
R2  Two or more factors are weak -> Long shot.
R3  Your type won at least 20% of awards and no factor is weak -> Good fit.
R4  Anything else -> Possible.
```

Every threshold is a constant in [`src/award_odds/verdict.py`](src/award_odds/verdict.py), the
rule text is generated from those constants, and the tests pin each boundary. R1 is meant to be
blunt: if almost nobody like you has won this program recently, the tool says so, even when the
budget and concentration look fine.

## Where the numbers come from

All data comes from two public endpoints:

- `POST /api/v2/search/spending_by_award_count/` for the total award count and for one count per
  recipient type (using the `recipient_type_names` filter).
- `POST /api/v2/search/spending_by_award/` for award rows, 100 per page, sorted largest first,
  following `page_metadata.hasNext`.

Filters: grant award types `02`, `03`, `04`, `05` (block, formula, project, cooperative
agreement), the listing number, and a time window with `date_type: new_awards_only`, so the
window counts awards that started in it rather than old awards that merely had activity.

The client spaces requests by at least 0.25 s, uses a 30 s timeout, and retries 429, 5xx and
connection errors with exponential backoff (honouring `Retry-After`). During development the API
began dropping connections after several back-to-back full runs and recovered on its own some
minutes later; when retries run out the tool exits with an error instead of printing partial
numbers.

## Decisions and what I rejected

**No language model in the scoring path, or anywhere.** The question "who won this program" is a
database query. A model would make the answer more fluent and less checkable, and the failure
mode of a model is plausible invention. A tool that tells someone their odds has to be the kind of
thing they can argue with, so every number here traces to an API response.

**Rules shown instead of a model score.** I rejected a single 0-100 number. A number without its
factors cannot be disputed, and a weighted blend hides which factor drove it. Three factors and
four ordered rules are crude, but anyone can see which rule fired and disagree with a specific
threshold.

**USASpending, not Grants.gov.** Grants.gov is where opportunities are posted: eligibility,
deadlines, estimated amounts. It does not record who won. USASpending records awards actually
made, with recipients and amounts. This tool asks about winners, so it reads the award record.

**Recipient type from count queries, not award rows.** Award rows from `spending_by_award` do not
carry a usable recipient type for grants. The search filter does. So the mix is one count query per
category, which is cheap and uses USASpending's own classification rather than guessing from
names. The API returns 0, not an error, for a misspelled category, so each category name was
checked against live responses.

**Award sizes from single-listing awards.** Some awards carry money from more than one listing.
See Limits.

## Limits

- **Federal grants only.** No foundations, no state or local programs, no contracts.
- **Recipient-type classification in USASpending is imperfect.** Some awards have no type
  recorded (shown as "no type recorded"; the tool warns above 10%). Categories reflect
  how the recipient registered, which may not match how you would describe them. In the listings
  tried while building this, the small-business category returned 0 awards.
- **Award amounts are whole-award totals.** USASpending's award amount covers the life of the
  award and every listing on it. On `93.243`, 612 awards holding 65.4% of award dollars also
  carried money from another listing (the largest also draw on State Opioid Response, `93.788`).
  Award sizes use single-listing awards only; total dollars, concentration and top recipients
  still use whole-award amounts and are overstated for those awards. The output says when this
  applies. Splitting awards by listing would need the transactions endpoint, which is not done.
- **Budget means the whole request.** Because award amounts are lifetime totals, compare your
  total request across the project period, not one year.
- **Zero and negative amounts** (deobligations, corrections) are counted and excluded from size
  and dollar figures.
- **Large programs may be truncated.** The default fetch caps at 5,000 awards; past that, sizes
  and concentration cover the largest awards only, and the output says so.
- **Past awards are not future odds.** A program can change priorities, and the data does not
  include who applied and lost.
- **Grounded is not calibrated.** The verdict is anchored in real award distributions. It has not
  been tested against application outcomes, because public data does not contain them, so it
  should not be read as a probability.

## Development

```sh
pip install -e '.[test]'
pytest                       # offline: recorded API responses in tests/fixtures
AWARD_ODDS_LIVE=1 pytest     # adds one smoke test against the real API
```

Fixtures were recorded from the live API on 2026-10-07: the complete response set for listing
`66.951` (131 awards, two pages, all type counts) and four trimmed award rows from `93.243`.

## License

MIT. See [LICENSE](LICENSE).
