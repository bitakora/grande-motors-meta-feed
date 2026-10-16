# Grande Motors — free Meta vehicle feed

This project turns the public stock shown on `grandemotors.co.nz/vehicles` into
catalogue feeds that Meta can refresh automatically. It does not require access
to Motorcentral's source code or a paid feed provider.

## What it creates

- `feed/meta-automotive-feed.csv` — for a Meta automotive/vehicle catalogue.
- `feed/meta-product-feed.csv` — legacy standard-Commerce output, not the active vehicle catalogue source.
- `feed/vehicles.json` — a readable archive of the parsed stock.
- `feed/feed-report.json` — run totals and every rejected vehicle/reason.

The script reads the inventory index and each public vehicle detail page. It
uses the stock number as the stable catalogue ID. A complete daily rebuild means
new vehicles appear automatically and vehicles removed from the website also
drop out of the next feed refresh.

Vehicles without a public numeric price or usable photo are reported but are not
sent to Meta because those are required catalogue fields.

## Active vehicle catalogue

The live **Grande Motors — Vehicle Inventory** catalogue is a **Vehicles** catalogue
under Grande Motors Ltd (business portfolio `1667149258160258`). Its catalogue ID
is `2161205071468582` and automotive data-source ID is `1671680804516609`.
It replaces its inventory daily at 10:00 GMT+13:00 from the automotive feed URL.
The previous personal product catalogue has been preserved, but is not the active
vehicle inventory destination. Importing cars does not publish Page posts or
launch ads.

Prices are read only from each vehicle's own primary price panel. POA, zero-price
and missing-price listings are excluded; related-car prices and metadata snippets
are never used as a fallback. The feed's price field retains the website's
advertised vehicle price. Explicit extra on-road costs and their total are stated
in the description when supplied by the website. Transit wording in a title is
also disclosed in the description, without promising immediate collection.

Descriptions use the vehicle heading and structured specifications rather than
truncated Open Graph snippets or general dealership advertising claims.

## Run on a computer

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe generate_feed.py
```

For a quick five-vehicle test:

```powershell
.\.venv\Scripts\python.exe generate_feed.py --limit 5 --output-dir test-output
```

## Free daily automation

The included GitHub Actions workflow runs once a day and commits changed feed
files. To make Meta able to download the CSV:

1. Put this folder in a public GitHub repository.
2. In the repository, open **Settings > Pages**.
3. Set the source to **Deploy from a branch**, select `main`, choose `/ (root)`,
   then save.
4. Confirm the public feed URL opens. It will look like:
   `https://YOUR-GITHUB-NAME.github.io/YOUR-REPOSITORY/feed/meta-automotive-feed.csv`.
5. In Meta Commerce Manager, open the Grande Motors catalogue and add a data
   source using **Data feed > Use a URL**. Use the automotive CSV for a vehicle
   catalogue. Do not use the legacy product CSV as a substitute for the active
   Vehicles catalogue.
6. Schedule Meta to fetch the URL daily, after the GitHub workflow has run.

The workflow is scheduled for 17:17 UTC each day (early morning in New Zealand).
It can also be run immediately from the repository's **Actions** tab.

The automotive feed is already tied to the Grande Motors Facebook Page ID
`449068425578249` and the dealership address at 80 Smales Road, East Tamaki.

## Safety checks

The generator will not replace existing feed files when:

- fewer than 50 valid vehicles are parsed during a full run; or
- more than 15% of discovered vehicles are rejected.

This protects the catalogue from being accidentally emptied if the website's
HTML changes. The detailed reason for normal individual exclusions appears in
`feed/feed-report.json`.

## Important distinction

The catalogue lets Meta power vehicle ads and catalogue-based placements on
Facebook and Instagram. It does not create normal organic Page posts. A separate
posting workflow can be added later for selected new arrivals without flooding
followers with every stock change.
