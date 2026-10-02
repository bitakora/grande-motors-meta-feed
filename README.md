# Grande Motors — free Meta vehicle feed

This project turns the public stock shown on `grandemotors.co.nz/vehicles` into
catalogue feeds that Meta can refresh automatically. It does not require access
to Motorcentral's source code or a paid feed provider.

## What it creates

- `feed/meta-automotive-feed.csv` — for a Meta automotive/vehicle catalogue.
- `feed/meta-product-feed.csv` — fallback for a standard Commerce product catalogue.
- `feed/vehicles.json` — a readable archive of the parsed stock.
- `feed/feed-report.json` — run totals and every rejected vehicle/reason.

The script reads the inventory index and each public vehicle detail page. It
uses the stock number as the stable catalogue ID. A complete daily rebuild means
new vehicles appear automatically and vehicles removed from the website also
drop out of the next feed refresh.

Vehicles without a public numeric price or usable photo are reported but are not
sent to Meta because those are required catalogue fields.

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
   catalogue, or the product CSV if the existing catalogue is a standard
   Commerce catalogue.
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
