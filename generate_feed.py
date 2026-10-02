#!/usr/bin/env python3
"""Build Meta catalogue feeds from Grande Motors' public vehicle listings.

The script reads only public pages from grandemotors.co.nz. It produces both an
automotive inventory feed and a standard commerce feed so the existing Meta
catalogue can use whichever format it was created for.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SITE_ROOT = "https://www.grandemotors.co.nz"
INVENTORY_URL = f"{SITE_ROOT}/vehicles"
DEALER_NAME = "Grande Motors Ltd"
DEALER_PHONE = "+64 22 637 3452"
DEALER_ADDRESS = "80 Smales Road, East Tamaki, Auckland 2013, New Zealand"
DEALER_ADDRESS_META = (
    "{addr1: '80 Smales Road', city: 'East Tamaki', region: 'Auckland', "
    "postal_code: '2013', country: 'NZ'}"
)
DEALER_LATITUDE = "-36.9417684"
DEALER_LONGITUDE = "174.9023989"
CURRENCY = "NZD"
FACEBOOK_PAGE_ID = "449068425578249"

KNOWN_MAKES = (
    "Mercedes-Benz",
    "Land Rover",
    "Alfa Romeo",
    "Aston Martin",
    "Great Wall",
    "Rolls-Royce",
    "SsangYong",
    "Volkswagen",
    "Mitsubishi",
    "Chevrolet",
    "Chrysler",
    "Hyundai",
    "Subaru",
    "Suzuki",
    "Toyota",
    "Nissan",
    "Honda",
    "Lexus",
    "Mazda",
    "Tesla",
    "Volvo",
    "Jaguar",
    "Porsche",
    "Renault",
    "Peugeot",
    "Citroen",
    "Daihatsu",
    "Isuzu",
    "Ford",
    "Holden",
    "BMW",
    "Audi",
    "Kia",
    "Mini",
    "Jeep",
)

BODY_STYLE_MAP = {
    "convertible": "CONVERTIBLE",
    "cabriolet": "CONVERTIBLE",
    "coupe": "COUPE",
    "hatchback": "HATCHBACK",
    "hatch": "HATCHBACK",
    "minivan": "MINIVAN",
    "people mover": "MINIVAN",
    "ute": "TRUCK",
    "pickup": "TRUCK",
    "truck": "TRUCK",
    "rv-suv": "SUV",
    "suv": "SUV",
    "sedan": "SEDAN",
    "saloon": "SEDAN",
    "station wagon": "WAGON",
    "wagon": "WAGON",
    "van": "VAN",
    "crossover": "CROSSOVER",
}

AUTOMOTIVE_HEADERS = [
    "vehicle_id",
    "title",
    "description",
    "url",
    "make",
    "model",
    "year",
    "mileage.value",
    "mileage.unit",
    "image[0].url",
    "image[0].tag[0]",
    "image[1].url",
    "image[2].url",
    "image[3].url",
    "image[4].url",
    "image[5].url",
    "image[6].url",
    "image[7].url",
    "image[8].url",
    "image[9].url",
    "body_style",
    "price",
    "exterior_color",
    "interior_color",
    "state_of_vehicle",
    "availability",
    "transmission",
    "drivetrain",
    "fuel_type",
    "condition",
    "vehicle_type",
    "stock_number",
    "dealer_id",
    "dealer_name",
    "dealer_phone",
    "fb_page_id",
    "address",
    "latitude",
    "longitude",
    "custom_label_0",
    "custom_label_1",
    "custom_label_2",
    "custom_label_3",
    "custom_label_4",
]

PRODUCT_HEADERS = [
    "id",
    "title",
    "description",
    "availability",
    "condition",
    "price",
    "link",
    "image_link",
    "additional_image_link",
    "brand",
    "product_type",
    "custom_label_0",
    "custom_label_1",
    "custom_label_2",
    "custom_label_3",
    "custom_label_4",
]


@dataclass
class Vehicle:
    stock_number: str
    title: str
    description: str
    url: str
    make: str
    model: str
    year: int
    mileage_km: int
    images: list[str]
    body_style: str
    price_nzd: int
    exterior_color: str = ""
    interior_color: str = ""
    transmission: str = ""
    drivetrain: str = ""
    fuel_type: str = ""
    engine_size: str = ""

    def automotive_row(self) -> dict[str, object]:
        row: dict[str, object] = {
            "vehicle_id": self.stock_number,
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "make": self.make,
            "model": self.model,
            "year": self.year,
            "mileage.value": self.mileage_km,
            "mileage.unit": "KM",
            "body_style": self.body_style,
            "price": f"{self.price_nzd} {CURRENCY}",
            "exterior_color": self.exterior_color,
            "interior_color": self.interior_color,
            "state_of_vehicle": "Used",
            "availability": "available",
            "transmission": self.transmission,
            "drivetrain": self.drivetrain,
            "fuel_type": self.fuel_type,
            "condition": "OTHER",
            "vehicle_type": "car_truck",
            "stock_number": self.stock_number,
            "dealer_id": "grande-motors",
            "dealer_name": DEALER_NAME,
            "dealer_phone": DEALER_PHONE,
            "fb_page_id": FACEBOOK_PAGE_ID,
            "address": DEALER_ADDRESS_META,
            "latitude": DEALER_LATITUDE,
            "longitude": DEALER_LONGITUDE,
            "custom_label_0": str(self.year),
            "custom_label_1": DEALER_NAME,
            "custom_label_2": self.body_style,
            "custom_label_3": self.fuel_type,
            "custom_label_4": self.transmission,
        }
        for index in range(10):
            row[f"image[{index}].url"] = (
                self.images[index] if index < len(self.images) else ""
            )
        row["image[0].tag[0]"] = "DEALER"
        return row

    def product_row(self) -> dict[str, object]:
        return {
            "id": self.stock_number,
            "title": self.title,
            "description": self.description,
            "availability": "in stock",
            "condition": "used",
            "price": f"{self.price_nzd:.2f} {CURRENCY}",
            "link": self.url,
            "image_link": self.images[0],
            "additional_image_link": ",".join(self.images[1:20]),
            "brand": self.make,
            "product_type": "Vehicles & Parts > Vehicles > Cars, Trucks & Vans",
            "custom_label_0": str(self.year),
            "custom_label_1": self.body_style,
            "custom_label_2": self.fuel_type,
            "custom_label_3": self.transmission,
            "custom_label_4": "Grande Motors",
        }


@dataclass
class Rejection:
    url: str
    reason: str


@dataclass
class FeedReport:
    generated_at_utc: str
    source_inventory_url: str
    discovered_vehicle_count: int
    accepted_vehicle_count: int
    rejected_vehicle_count: int
    request_failure_count: int
    elapsed_seconds: float
    rejected: list[dict[str, str]] = field(default_factory=list)


class FeedError(RuntimeError):
    """Raised when a feed cannot be safely generated."""


def compact_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def build_session() -> requests.Session:
    retries = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET",)),
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=12, pool_maxsize=12)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "GrandeMotorsCatalogFeed/1.0 "
                "(+https://www.grandemotors.co.nz/contact-us)"
            ),
            "Accept-Language": "en-NZ,en;q=0.9",
        }
    )
    session.mount("https://", adapter)
    return session


def fetch_text(session: requests.Session, url: str, timeout: int = 35) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def canonical_vehicle_url(href: str) -> str | None:
    absolute = urljoin(SITE_ROOT, href)
    parsed = urlsplit(absolute)
    if parsed.netloc.lower() not in {"grandemotors.co.nz", "www.grandemotors.co.nz"}:
        return None
    if not re.fullmatch(r"/vehicle/[^/]+/\d+/?", parsed.path, flags=re.IGNORECASE):
        return None
    clean_path = parsed.path.rstrip("/")
    return urlunsplit(("https", "www.grandemotors.co.nz", clean_path, "", ""))


def listing_page_number(href: str) -> int | None:
    parsed = urlsplit(urljoin(INVENTORY_URL, href))
    values = parse_qs(parsed.query).get("Page") or parse_qs(parsed.query).get("page")
    if not values:
        return None
    try:
        return int(values[0])
    except (TypeError, ValueError):
        return None


def parse_listing_page(html: str) -> tuple[list[str], int]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    max_page = 1
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        page = listing_page_number(href)
        if page is not None:
            max_page = max(max_page, page)
        vehicle_url = canonical_vehicle_url(href)
        if vehicle_url and vehicle_url not in seen:
            seen.add(vehicle_url)
            urls.append(vehicle_url)
    return urls, max_page


def discover_vehicle_urls(session: requests.Session, max_pages: int = 100) -> list[str]:
    first_html = fetch_text(session, INVENTORY_URL)
    first_urls, last_page = parse_listing_page(first_html)
    if last_page > max_pages:
        raise FeedError(
            f"Inventory claims {last_page} pages, above the safety limit of {max_pages}."
        )

    urls = list(first_urls)
    seen = set(first_urls)
    for page in range(2, last_page + 1):
        page_html = fetch_text(session, f"{INVENTORY_URL}?Page={page}")
        page_urls, _ = parse_listing_page(page_html)
        for vehicle_url in page_urls:
            if vehicle_url not in seen:
                seen.add(vehicle_url)
                urls.append(vehicle_url)
        logging.info("Discovered page %d/%d (%d vehicles total)", page, last_page, len(urls))
        time.sleep(0.08)

    if not urls:
        raise FeedError("No vehicle detail links were found on the public inventory pages.")
    return urls


def meta_content(soup: BeautifulSoup, property_name: str) -> str:
    tag = soup.find("meta", attrs={"property": property_name})
    if not tag:
        tag = soup.find("meta", attrs={"name": property_name})
    return compact_text(tag.get("content")) if tag else ""


def parse_stock_number(url: str, soup: BeautifulSoup) -> str:
    match = re.search(r"/vehicle/[^/]+/(\d+)", url, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    stock = soup.select_one(".stock-no")
    if stock:
        number = re.search(r"\d+", stock.get_text(" ", strip=True))
        if number:
            return number.group(0)
    return ""


def parse_year_make_model(url: str, title: str) -> tuple[int, str, str]:
    path_match = re.search(r"/vehicle/(\d{4})-([^/]+)/\d+", url, re.IGNORECASE)
    path_year = int(path_match.group(1)) if path_match else 0

    # The URL contains the clean model (for example Toyota-C-HR), while the
    # heading also contains sale copy and trim details. Prefer the URL so Meta's
    # make/model fields stay consistent across the catalogue.
    if path_match:
        slug = path_match.group(2)
        for candidate in sorted(KNOWN_MAKES, key=len, reverse=True):
            candidate_slug = candidate.replace(" ", "-")
            if slug.casefold().startswith(candidate_slug.casefold() + "-"):
                model = slug[len(candidate_slug) + 1 :]
                return path_year, candidate, compact_text(model)

    title_match = re.match(r"\s*((?:19|20)\d{2})\s+(.+?)\s*$", title)
    if title_match:
        year = int(title_match.group(1))
        remainder = title_match.group(2)
    elif path_match:
        year = path_year
        remainder = path_match.group(2).replace("-", " ")
    else:
        return 0, "", ""

    make = ""
    model_and_trim = ""
    normalized = remainder.casefold().replace("-", " ")
    for candidate in sorted(KNOWN_MAKES, key=len, reverse=True):
        candidate_normalized = candidate.casefold().replace("-", " ")
        if normalized == candidate_normalized or normalized.startswith(candidate_normalized + " "):
            make = candidate
            model_and_trim = remainder[len(candidate) :].strip(" -")
            if not model_and_trim and path_match:
                slug_remainder = path_match.group(2).replace("-", " ")
                model_and_trim = slug_remainder[len(candidate) :].strip(" -")
            break

    if not make:
        parts = remainder.split(maxsplit=1)
        make = parts[0] if parts else ""
        model_and_trim = parts[1] if len(parts) > 1 else ""

    # The Meta model field may include the site's variant text; this is preferable
    # to dropping the actual model when no separate model field exists in the page.
    return year, make, compact_text(model_and_trim)


def parse_specs(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}
    for row in soup.select(".row.collapse"):
        children = row.find_all("div", recursive=False)
        if len(children) < 2:
            continue
        label = compact_text(children[0].get_text(" ", strip=True)).rstrip(":")
        value = compact_text(children[1].get_text(" ", strip=True))
        if label and value and len(label) <= 40 and label not in specs:
            specs[label] = value
    return specs


def first_spec(specs: dict[str, str], *labels: str) -> str:
    folded = {key.casefold(): value for key, value in specs.items()}
    for label in labels:
        value = folded.get(label.casefold())
        if value:
            return value
    return ""


def parse_price(soup: BeautifulSoup) -> int:
    for element in soup.select("span.price"):
        text = compact_text(element.get_text(" ", strip=True))
        match = re.match(r"\$\s*(\d[\d,]*)(?:\.\d{1,2})?\b", text)
        if match:
            return int(match.group(1).replace(",", ""))
    og_description = meta_content(soup, "og:description")
    match = re.search(r"\$\s*(\d[\d,]*)", og_description)
    return int(match.group(1).replace(",", "")) if match else 0


def parse_mileage(specs: dict[str, str], page_text: str) -> int:
    raw = first_spec(specs, "Odometer", "Mileage")
    if not raw:
        match = re.search(r"(?:Odometer|Mileage)\s*([\d,]+)\s*km", page_text, re.I)
        raw = match.group(1) if match else ""
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else 0


def parse_body_style(specs: dict[str, str], title: str) -> str:
    raw = first_spec(specs, "Body", "Body Style")
    searchable = f"{raw} {title}".casefold()
    for token, meta_value in BODY_STYLE_MAP.items():
        if token in searchable:
            return meta_value
    return "OTHER"


def parse_transmission_and_drivetrain(specs: dict[str, str]) -> tuple[str, str]:
    raw = first_spec(specs, "Transmission")
    parts = [compact_text(part) for part in raw.split(",") if compact_text(part)]
    raw_transmission = parts[0] if parts else ""
    transmission_lower = raw_transmission.casefold()
    if transmission_lower.startswith("auto"):
        transmission = "Automatic"
    elif transmission_lower.startswith("manual"):
        transmission = "Manual"
    else:
        transmission = "Other" if raw_transmission else ""

    drivetrain = parts[1] if len(parts) > 1 else ""
    if not drivetrain:
        lower = raw.casefold()
        if "4wd" in lower or "four wheel" in lower or "all wheel" in lower or "awd" in lower:
            drivetrain = "AWD"
        elif "rear wheel" in lower or "rwd" in lower:
            drivetrain = "RWD"
        elif "front wheel" in lower or "fwd" in lower:
            drivetrain = "FWD"
    drivetrain_lower = drivetrain.casefold()
    if "front wheel" in drivetrain_lower or drivetrain_lower == "fwd":
        drivetrain = "FWD"
    elif "rear wheel" in drivetrain_lower or drivetrain_lower == "rwd":
        drivetrain = "RWD"
    elif "all wheel" in drivetrain_lower or drivetrain_lower == "awd":
        drivetrain = "AWD"
    elif "4wd" in drivetrain_lower or "4x4" in drivetrain_lower or "four wheel" in drivetrain_lower:
        drivetrain = "4X4"
    elif drivetrain:
        drivetrain = "Other"
    return transmission, drivetrain


def parse_fuel_type(
    soup: BeautifulSoup, specs: dict[str, str], page_text: str, title: str
) -> str:
    fuel = first_spec(specs, "Fuel", "Fuel Type", "Motive Power")
    if not fuel:
        match = re.search(
            r"Motive Power:\s*(.+?)(?:\s+Fuel economy|\s+Annual fuel cost|\s+Emissions|$)",
            page_text,
            flags=re.IGNORECASE,
        )
        fuel = compact_text(match.group(1)) if match else ""
    lower = fuel.casefold()
    title_lower = title.casefold()
    if not lower or lower == "unknown":
        if "hybrid" in title_lower or "e-power" in title_lower or "e:hev" in title_lower:
            lower = "hybrid"
        elif "electric" in title_lower or "nissan leaf" in title_lower or "tesla" in title_lower:
            lower = "electric"
        else:
            return "OTHER"
    if "plug" in lower and "hybrid" in lower:
        return "PLUG_IN_HYBRID"
    if "hybrid" in lower:
        return "HYBRID"
    if "electric" in lower:
        return "ELECTRIC"
    if "diesel" in lower:
        return "DIESEL"
    if "petrol" in lower or "gasoline" in lower:
        return "GASOLINE"
    if "flex" in lower:
        return "FLEX"
    return "OTHER"


def normalize_image_url(src: str, page_url: str) -> str:
    absolute = urljoin(page_url, src)
    parsed = urlsplit(absolute)
    return urlunsplit(("https", "www.grandemotors.co.nz", parsed.path, "", ""))


def parse_images(soup: BeautifulSoup, page_url: str, title: str) -> list[str]:
    images: list[str] = []
    seen: set[str] = set()
    title_base = compact_text(re.sub(r"\s+\|\s+Grande Motors.*$", "", title, flags=re.I))
    identity_prefix = " ".join(title_base.split()[:3]).casefold()

    for image in soup.find_all("img"):
        src = image.get("src") or image.get("data-src")
        if not src or "vehicledata" not in src.casefold():
            continue
        if "no-photo" in src.casefold() or src.casefold().endswith(".pdf"):
            continue
        alt = compact_text(image.get("alt"))
        if "thumbnail" in alt.casefold():
            continue
        # Stop related/listing-card images from entering the vehicle's gallery.
        if identity_prefix and alt and not alt.casefold().startswith(identity_prefix):
            continue
        url = normalize_image_url(src, page_url)
        if re.search(r"-\d+-1\.(?:jpe?g|png|webp)$", url, flags=re.I):
            continue
        if url not in seen:
            seen.add(url)
            images.append(url)

    if not images:
        og_image = meta_content(soup, "og:image")
        if og_image and "no-photo" not in og_image.casefold():
            images.append(normalize_image_url(og_image, page_url))
    return images


def build_description(title: str, og_description: str, specs: dict[str, str]) -> str:
    description = compact_text(og_description)
    description = re.sub(r"\s+\|\s+Grande Motors.*$", "", description, flags=re.I)
    if len(description) < 40:
        engine = first_spec(specs, "Engine")
        odometer = first_spec(specs, "Odometer", "Mileage")
        details = ", ".join(value for value in (engine, odometer) if value)
        description = f"{title}. {details}".rstrip(". ") + "."
    if DEALER_NAME.casefold() not in description.casefold():
        description = f"{description} Available from {DEALER_NAME}, East Tamaki, Auckland."
    return description[:4999]


def parse_vehicle_page(url: str, html: str) -> Vehicle:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h2")
    title = compact_text(heading.get_text(" ", strip=True)) if heading else ""
    if not title:
        title = meta_content(soup, "og:title")
        title = re.sub(r"\s*\|\s*Grande Motors.*$", "", title, flags=re.I).strip()
    specs = parse_specs(soup)
    page_text = compact_text(soup.get_text(" ", strip=True))
    stock_number = parse_stock_number(url, soup)
    year, make, model = parse_year_make_model(url, title)
    price = parse_price(soup)
    mileage = parse_mileage(specs, page_text)
    images = parse_images(soup, url, title)
    transmission, drivetrain = parse_transmission_and_drivetrain(specs)
    description = build_description(title, meta_content(soup, "og:description"), specs)

    missing = []
    for label, value in (
        ("stock number", stock_number),
        ("title", title),
        ("year", year),
        ("make", make),
        ("model", model),
        ("price", price),
        ("image", images),
    ):
        if not value:
            missing.append(label)
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))

    return Vehicle(
        stock_number=stock_number,
        title=title,
        description=description,
        url=url,
        make=make,
        model=model,
        year=year,
        mileage_km=mileage,
        images=images,
        body_style=parse_body_style(specs, title),
        price_nzd=price,
        exterior_color=first_spec(specs, "Ext Colour", "Exterior Colour", "Exterior Color"),
        interior_color=first_spec(specs, "Interior", "Interior Colour", "Interior Color"),
        transmission=transmission,
        drivetrain=drivetrain,
        fuel_type=parse_fuel_type(soup, specs, page_text, title),
        engine_size=first_spec(specs, "Engine", "Engine Size"),
    )


def fetch_and_parse_vehicle(url: str) -> Vehicle:
    # A separate session per worker avoids sharing mutable Session state across threads.
    session = build_session()
    html = fetch_text(session, url)
    return parse_vehicle_page(url, html)


def write_csv_atomic(path: Path, headers: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def generate(
    output_dir: Path,
    workers: int,
    limit: int | None,
    minimum_accepted: int,
    maximum_rejection_rate: float,
) -> FeedReport:
    started = time.monotonic()
    session = build_session()
    urls = discover_vehicle_urls(session)
    if limit is not None:
        urls = urls[:limit]

    logging.info("Fetching %d vehicle detail pages with %d workers", len(urls), workers)
    vehicles: list[Vehicle] = []
    rejections: list[Rejection] = []
    request_failures = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_and_parse_vehicle, url): url for url in urls}
        for index, future in enumerate(as_completed(futures), start=1):
            url = futures[future]
            try:
                vehicles.append(future.result())
            except requests.RequestException as exc:
                request_failures += 1
                rejections.append(Rejection(url=url, reason=f"request failed: {exc}"))
                logging.warning("Request failed for %s: %s", url, exc)
            except Exception as exc:  # The report must record malformed vehicles individually.
                rejections.append(Rejection(url=url, reason=str(exc)))
                logging.warning("Rejected %s: %s", url, exc)
            if index % 25 == 0 or index == len(urls):
                logging.info(
                    "Processed %d/%d detail pages (%d accepted, %d rejected)",
                    index,
                    len(urls),
                    len(vehicles),
                    len(rejections),
                )

    unique: dict[str, Vehicle] = {}
    for vehicle in vehicles:
        unique[vehicle.stock_number] = vehicle
    vehicles = sorted(unique.values(), key=lambda item: (item.make, item.model, item.year, item.stock_number))

    rejection_rate = len(rejections) / len(urls) if urls else 1.0
    effective_minimum = (
        max(1, math.ceil(len(urls) * (1 - maximum_rejection_rate)))
        if limit is not None
        else minimum_accepted
    )
    if len(vehicles) < effective_minimum:
        raise FeedError(
            f"Safety check failed: only {len(vehicles)} valid vehicles; "
            f"minimum is {effective_minimum}. Existing feed files were not replaced."
        )
    if rejection_rate > maximum_rejection_rate:
        raise FeedError(
            f"Safety check failed: rejection rate {rejection_rate:.1%} exceeds "
            f"{maximum_rejection_rate:.1%}. Existing feed files were not replaced."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(
        output_dir / "meta-automotive-feed.csv",
        AUTOMOTIVE_HEADERS,
        (vehicle.automotive_row() for vehicle in vehicles),
    )
    write_csv_atomic(
        output_dir / "meta-product-feed.csv",
        PRODUCT_HEADERS,
        (vehicle.product_row() for vehicle in vehicles),
    )
    write_json_atomic(
        output_dir / "vehicles.json",
        [asdict(vehicle) for vehicle in vehicles],
    )

    report = FeedReport(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        source_inventory_url=INVENTORY_URL,
        discovered_vehicle_count=len(urls),
        accepted_vehicle_count=len(vehicles),
        rejected_vehicle_count=len(rejections),
        request_failure_count=request_failures,
        elapsed_seconds=round(time.monotonic() - started, 2),
        rejected=[asdict(item) for item in rejections],
    )
    write_json_atomic(output_dir / "feed-report.json", asdict(report))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "feed",
        help="Directory for generated CSV/JSON files (default: ./feed)",
    )
    parser.add_argument("--workers", type=int, default=4, help="Concurrent detail requests")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N vehicles")
    parser.add_argument(
        "--minimum-accepted",
        type=int,
        default=50,
        help="Do not overwrite a full feed when fewer valid vehicles are found",
    )
    parser.add_argument(
        "--maximum-rejection-rate",
        type=float,
        default=0.15,
        help="Do not overwrite feeds when the rejected fraction exceeds this value",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.workers < 1 or args.workers > 8:
        raise SystemExit("--workers must be between 1 and 8")
    try:
        report = generate(
            output_dir=args.output_dir,
            workers=args.workers,
            limit=args.limit,
            minimum_accepted=args.minimum_accepted,
            maximum_rejection_rate=args.maximum_rejection_rate,
        )
    except FeedError as exc:
        logging.error("%s", exc)
        return 2
    logging.info(
        "Feed ready: %d accepted, %d rejected, %.2f seconds",
        report.accepted_vehicle_count,
        report.rejected_vehicle_count,
        report.elapsed_seconds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
