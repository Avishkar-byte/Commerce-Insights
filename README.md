# Olist Commerce Insights · Big Data Pipeline and Analytics Console

An end to end Big Data pipeline over the Olist Brazilian e-commerce dataset. Nine raw
CSV tables land in a replicated HDFS cluster, Apache Spark cleans and aggregates them
through a medallion architecture, the results are served from MongoDB, and a Streamlit
console answers four business questions about sales, delivery, satisfaction and sellers.

The whole system is containerised and runs locally on one laptop with 8 GB of RAM. No
cloud account, no managed service and no Linux install on the host.

Built as a course project for BCSE402L Big Data Analytics.

## The Problem

A marketplace generates transactional data across many tables that do not answer
questions on their own. The Olist dataset is nine CSVs and about 1.5 million rows with
eight foreign key relationships between them. Before anyone can ask "why are customers
unhappy", every one of those joins has to be resolved, and the answer has to survive
being sliced by month, by state and by product category.

Single machine tools handle this badly at the point where the joins and the window
functions meet. Spark handles it well, but only if the data model underneath is built so
that the numbers stay correct when the user changes a filter. That second part is the
real engineering problem here, and most of the design decisions below exist to solve it.

The headline finding the console surfaces: average review score falls from 4.29 for
orders delivered on time to 1.67 for orders that arrive 8 to 14 days late. Satisfaction
does not decay gradually, it collapses, and it collapses early.

## Setup and Run Instructions

### Prerequisites

- Docker Desktop with the WSL2 backend, capped at 4 GB RAM
- Git
- About 10 GB free disk space for images and volumes

Nothing else is installed on the host. Python, Java, Hadoop, Spark and MongoDB all live
inside containers.

### 1. Generate the secrets file

`.env` holds the MongoDB passwords and is gitignored. Generate it with random values.
This prints only the variable names, never the values.

```powershell
function New-Pw { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ }) }
$lines = @(
  "MONGO_ROOT_USER=olist_root",
  "MONGO_ROOT_PASSWORD=$(New-Pw)",
  "MONGO_DB=olist_analytics",
  "OLIST_PIPELINE_PASSWORD=$(New-Pw)",
  "OLIST_DASHBOARD_PASSWORD=$(New-Pw)",
  "DASHBOARD_BIND=127.0.0.1"
)
[IO.File]::WriteAllText("$PWD\.env", ($lines -join "`n") + "`n")
Get-Content .env | ForEach-Object { ($_ -split '=')[0] }
```

MongoDB users are created from these values on the first start of an empty `mongo-data`
volume. Changing a password in `.env` afterwards does not change it in MongoDB.

### 2. Add the dataset

Place the nine Olist CSVs in `data\raw\`. If the folder is empty, `download` fetches them
with the Kaggle API, which needs a token at `secrets\kaggle.json`. If the files are
already there, the download step is skipped and no token is needed.

### 3. Build and run

```powershell
.\tasks.ps1 build       # build the spark and dashboard images
.\tasks.ps1 up          # HDFS cluster + MongoDB
.\tasks.ps1 pipeline    # download, ingest, silver, gold, validate, export
.\tasks.ps1 serve       # stop HDFS, start the dashboard
```

Console UI: http://localhost:8501
NameNode UI: http://localhost:9870
Spark UI: http://localhost:4040 while a job is running

A full run from an empty HDFS takes about 4 minutes 38 seconds on an Intel i5 with 8 GB.

### 4. Other commands

Every command goes through `tasks.ps1`, which stops at the first failure.

| Command | Does |
| --- | --- |
| `build` | build the spark and dashboard images |
| `up` | pipeline mode: HDFS cluster and MongoDB |
| `serve` | serve mode: stop HDFS, start MongoDB and the dashboard |
| `down` | stop all containers, volumes are never removed |
| `status` | container list, live DataNode count, resource use |
| `download` | fetch the CSVs into `data/raw`, skips files already present |
| `ingest` | upload `data/raw` into `/olist/raw` in HDFS |
| `silver` / `gold` / `export` | run the corresponding Spark job |
| `validate [--mongo]` | 17 reconciliation and row count checks |
| `pipeline` | the whole chain, from `up` to `validate --mongo` |
| `test` / `lint` | pytest, 57 tests / ruff |
| `hdfs <args>` | pass through, for example `.\tasks.ps1 hdfs dfs -ls -R /olist` |
| `mongo-check` | list MongoDB collections with document counts |
| `notebook` | Jupyter Lab on http://localhost:8888 |
| `shell` | bash inside the spark container |
| `failover-demo` | stop a DataNode, prove reads still work, restart it |
| `reset-hdfs` | delete `/olist` after confirmation, volumes are kept |
| `logs <service>` | last 100 log lines for one service |

## Approach and Architecture

### High level data flow

```
data/raw/*.csv                    nine Kaggle CSVs, 120 MB
  |
  |  hdfs dfs -put, from the namenode container
  v
HDFS cluster                      1 NameNode + 2 DataNodes, replication 2
  /olist/raw                      bronze: untouched CSV
  |
  |  pipeline/jobs/silver.py, Spark 3.5 on local[2]
  v
  /olist/silver                   typed, cleaned, joined Parquet
      customers, sellers, products, geo_zip
      orders_fact    99,441 rows, one per order
      items_fact    112,650 rows, one per order item
  |
  |  pipeline/jobs/gold.py
  v
  /olist/gold                     aggregates, one folder per collection
      order_metrics, delivery_distance, review_by_delay,
      payment_mix, seller_scorecard
  |
  |  pipeline/jobs/export_mongo.py, MongoDB Spark Connector 10.5
  v
MongoDB 8.0                       71,526 documents, compound indexed
  |
  |  server side $match then $group, small frames only
  v
Streamlit console                 Home, Sales, Delivery, Satisfaction, Sellers
```

### Key engineering decisions and trade offs

**Gold stores sums and counts, never averages.** This is the decision everything else
depends on. A stored average cannot be recombined: averaging the per month averages of
two months with different order counts gives the wrong answer. So the gold layer stores
`late_orders` and `delivered_orders`, never `late_rate`. Every ratio is computed once, in
`dashboard/lib/metrics.py`, after MongoDB has summed the selection. The cost is more
columns and a slightly larger collection. The benefit is that any combination of month
range, state and category produces a correct number without precomputing that
combination. `seller_scorecard` is the single exception, because it holds one all time
document per seller and is never re-aggregated.

**Every order gets exactly one primary category.** An order can contain items from
several categories. Counting it once per category would double count orders and make
category totals non additive, so the order is attributed to its highest priced item, with
ties broken by the lowest `order_item_id` so the result is deterministic. The cost is
real: multi category orders are attributed to one of them. The justification is measured,
not assumed. 89.4 percent of orders contain a single item, so the distortion affects
about one order in ten and only on the category dimension. Orders with no items at all
are labelled rather than dropped, and excluded wherever categories are ranked.

**Explicit schemas everywhere, `inferSchema` never.** Brazilian postcodes have
significant leading zeros. Letting Spark infer types reads `01310` as the integer 1310
and silently corrupts every postcode beginning with zero, which then breaks the
geolocation join and the distance calculation downstream. All nine tables have a declared
`StructType` and all postcodes are strings left padded to five characters.

**Replication is a property of the writing client, not just the cluster.** The cluster
sets `dfs.replication=2`, and files uploaded with `hdfs dfs -put` honoured it. Files
written by Spark did not. The Spark image ships no `hdfs-site.xml`, so its HDFS client
fell back to Hadoop's default of three replicas, a target two DataNodes can never meet,
and `fsck` reported 100 percent of silver and gold blocks under replicated. The disk
usage ratio gave it away: raw consumed exactly twice its logical size while silver
consumed three times. The fix passes `spark.hadoop.dfs.replication` from
`config/settings.yaml` into the SparkSession so client and cluster agree.

**Haversine as Spark column expressions, no Python UDF.** Distance between customer and
seller is built from `pyspark.sql.functions` so the work stays inside the JVM rather than
serialising every row into a Python worker. One subtlety cost real debugging time:
`F.least()` ignores nulls, so clamping the haversine argument with `least(a, 1.0)` turned
a null coordinate into 1.0 and produced a bogus 20,015 km antipodal distance instead of
an unknown. The clamp is now a `when` expression that preserves null. A unit test covers
it.

**Two run modes, because 4 GB is the budget.** The whole stack does not fit in memory at
once. Pipeline mode runs the HDFS cluster plus MongoDB with the Spark container started
per job, at about 3 to 3.5 GB. Serve mode stops HDFS and runs MongoDB plus the dashboard,
under 1 GB. Per container memory limits and JVM heap sizes are declared in
`docker-compose.yml` rather than left to chance.

**All filtering is pushed into MongoDB.** The dashboard never pulls a collection and
filters in pandas. Every query is a `$match` then `$group` against a compound index on
the three filter dimensions, so what crosses the wire is the grouped result, typically a
few dozen rows.

**The dashboard cannot import pyspark.** It reads only MongoDB, enforced by convention
and by the fact that `dashboard/requirements.txt` does not contain it. This keeps the
serving container at 512 MB and keeps the presentation layer honest about where numbers
come from.

**Pinned dependency versions.** An unpinned requirements file meant a rebuild silently
pulled pandas 3.0 and numpy 2.4, new majors that were not in the validated image. Both
requirements files now pin exact versions, so a rebuild before a demo reproduces the
image that was tested.

## Stack

| Layer | Choice |
| --- | --- |
| Storage | Hadoop HDFS 3.3.6, 1 NameNode and 2 DataNodes, replication 2, Parquet |
| Processing | Apache Spark 3.5.9 via PySpark, `local[2]`, Java 17 |
| Serving store | MongoDB 8.0, compound indexed, embedded arrays for seller documents |
| Connector | MongoDB Spark Connector 10.5.0, with a PyMongo fallback path |
| Presentation | Streamlit 1.64, Plotly 7.1, Inter |
| Orchestration | Docker Compose, four profiles, plus `tasks.ps1` as the single entry point |
| Config | One `config/settings.yaml`, no hard coded hosts, paths, windows or bucket edges |
| Tests | pytest, 57 tests, local SparkSession only, no HDFS or MongoDB |
| Lint | ruff, rule set pinned explicitly |

## The Four Dashboard Functions

All four share one sidebar with three global filters: purchase month range, customer
states and product categories. Filters persist across pages.

| Page | Question | What it shows |
| --- | --- | --- |
| Sales | How is the business doing | GMV, orders, average order value, freight share, monthly growth, top categories, payment mix, revenue by state |
| Delivery | Where and why are deliveries late | Late rate choropleth by state, monthly trend, late rate and transit time by seller to customer distance |
| Satisfaction | What drives bad reviews | Average review by delay bucket, score distribution per bucket, lowest rated categories |
| Sellers | Which sellers help or hurt the platform | Leaderboard with a health score, per seller detail against the platform average, monthly trend and category mix |

Two definitions worth calling out. `dispatch_late_rate` compares the carrier handover
against the seller's own shipping limit, which separates seller delay from carrier delay,
and it is null rather than false when either timestamp is missing, because an unknown is
not a success. `health_score` is
`100 * (0.4 * (avg_review - 1) / 4 + 0.3 * (1 - dispatch_late_rate) + 0.3 * (1 - cancel_rate))`,
and those weights are a documented design choice, not a standard.

States with fewer than 100 delivered orders in the current selection are drawn in neutral
grey on the map rather than placed on the delay colour scale, because a late rate
computed from a handful of orders is not meaningful.

## Validation Results

`.\tasks.ps1 validate --mongo` runs 17 checks. All 17 pass, on a pipeline rebuilt from an
empty HDFS, with results identical to the previous run.

| Check | Result |
| --- | --- |
| Raw orders and customers | 99,441 rows each, as expected |
| Distinct `customer_unique_id` | 96,096, as expected |
| Silver `orders_fact` | 99,441 rows, `order_id` unique, `year_month` never null |
| GMV reconciliation | gold 13,591,643.70 against items_fact 13,591,643.70, difference 0.0000 |
| Order reconciliation | gold 99,441 equals silver 99,441 |
| Seller rates within 0 to 1 | zero out of range across all three rates |
| MongoDB document counts | all five collections match gold, `meta` present |

Row counts by layer:

| Layer | Table or collection | Rows |
| --- | --- | --- |
| raw | orders, customers | 99,441 each |
| raw | order_items, order_payments, order_reviews | 112,650 / 103,886 / 99,224 |
| raw | products, sellers, geolocation | 32,951 / 3,095 / 1,000,163 |
| silver | orders_fact, items_fact | 99,441 / 112,650 |
| silver | customers, sellers, products, geo_zip | 99,441 / 3,095 / 32,951 / 19,010 |
| gold | order_metrics | 11,975 |
| gold | delivery_distance | 20,062 |
| gold | review_by_delay | 17,006 |
| gold | payment_mix | 19,388 |
| gold | seller_scorecard | 3,095 |

HDFS replication across all three layers, from `.\tasks.ps1 hdfs fsck /olist`:

```
Total blocks (validated):  62 (avg. block size 2532948 B)
Under-replicated blocks:   0 (0.0 %)
Average block replication: 2.0
Missing blocks:            0
Corrupt blocks:            0
```

Fault tolerance is demonstrated by `.\tasks.ps1 failover-demo`, which reads a file from
HDFS, stops `datanode2`, waits for the NameNode to mark it dead, reads the same file
again successfully with one live node, then restarts it and waits for two live nodes. The
heartbeat recheck interval is lowered to 30 seconds so the node is marked dead in about
90 seconds instead of roughly 10 minutes.

The dashboard is verified headlessly across five pages and six filter scenarios,
including a single low volume state, a one month range and a selection that returns no
data at all. Thirty combinations, zero exceptions.

## Exploratory Analysis

`notebooks/01_eda.ipynb` reads the silver layer from HDFS and writes seven figures into
`reports/figures/`. Two of its findings are used above to justify design decisions rather
than being presented on their own: 89.4 percent of orders contain a single item, and only
3.12 percent of customers ever place a second order. The second is why the console
targets delivery, satisfaction and seller performance instead of retention, which would
be statistically thin on a 3 percent repeat base.

## Limitations and Next Steps

**The dataset is large for a laptop and small for Big Data.** About 100 thousand orders
is not a volume that requires a cluster. The honest argument is about the architecture
rather than the current row count: the same code scales by adding DataNodes for storage
and Spark workers for compute, with no changes to the jobs. Replication, the failover
demo and the Spark DAG are the evidence that the distributed parts are real rather than
decorative.

**The pipeline is batch, not streaming.** There is no continuous ingestion. Refreshing
the console means re-running the pipeline, which takes about 4 minutes 38 seconds.

**Reviews are attached to orders, not to sellers.** In a multi seller order every seller
carries that order's review, so `avg_review` in the scorecard is shared rather than
attributed. There is no way to split it with the data available.

**Geolocation resolves to postcode prefix, not address.** Distances between customer and
seller are therefore approximate, and about 1,265 orders have no usable coordinate pair.
Those are kept and bucketed as unknown rather than dropped, because dropping them would
bias the late rate.

**The payment mix uses each order's primary payment type.** Splitting a single order
across several payment types would break additivity against the other order level
collections, so the mix reports the dominant type per order. This slightly understates
vouchers, which are often combined with a card.

**Health score weights are unvalidated.** They order sellers sensibly but are a design
choice with no external benchmark behind them.

**Single host deployment.** Replication protects against losing a DataNode, not against
losing the machine. There is no high availability NameNode and no off host backup.

**GST and fiscal handling is out of scope.** Expense heads and categories are exported,
but there is no invoice matching and no filing format.

### What would come next, in order

1. Partition the silver layer by `year_month` and compare Parquet against ORC, the
   cheapest available performance work.
2. Streaming ingestion with Kafka and Spark Structured Streaming, so delay alerts become
   near real time instead of batch.
3. A late delivery prediction at checkout, using distance, seller history and category,
   which turns the current descriptive finding into something actionable.
4. Multi name payee resolution for sellers appearing under more than one trade name.
5. Formal data quality gates in place of hand written assertions.

## Additional Notes

The dataset is the Brazilian E-Commerce Public Dataset by Olist, published on Kaggle at
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce and licensed CC BY-NC-SA 4.0.
Credit to Olist and Kaggle. The raw data is not committed to this repository.

All ports are published on `127.0.0.1` only, so nothing is reachable from other devices
on the network. The single exception is the dashboard in LAN demo mode, enabled by
setting `DASHBOARD_BIND=0.0.0.0`. MongoDB is never exposed. Three MongoDB users are
created with separate privileges: one for initialisation, one with readWrite used by the
pipeline, and one read only user used by the dashboard.

Files use LF line endings except `*.ps1`, enforced by `.gitattributes`, because the run
scripts are PowerShell and the rest of the stack is Linux.

The Brazil states GeoJSON in `dashboard/assets/` is from the Code for America "Click That
Hood" project, MIT licensed, with its source recorded in `dashboard/assets/README.md`. If
the file is absent the delivery page falls back to a ranked bar chart rather than failing.
