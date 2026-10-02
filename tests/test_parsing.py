import unittest

from generate_feed import (
    canonical_vehicle_url,
    parse_listing_page,
    parse_vehicle_page,
    parse_year_make_model,
)


VEHICLE_HTML = """
<html><head>
  <meta property="og:title" content="2019 Mazda 6 | Grande Motors">
  <meta property="og:description" content="2019 Mazda 6 with safety technology.">
  <meta property="og:image" content="https://www.grandemotors.co.nz/Motorcentral/VehicleData/demo-1.jpg">
</head><body>
  <h2>2019 Mazda 6 GSX</h2>
  <div class="stock-no">Stock# 13662</div>
  <span class="price">$23,500</span>
  <div class="row collapse"><div>Engine</div><div>2500cc</div></div>
  <div class="row collapse"><div>Body</div><div>4 Door, Sedan</div></div>
  <div class="row collapse"><div>Odometer</div><div>100,960km</div></div>
  <div class="row collapse"><div>Ext Colour</div><div>Red</div></div>
  <div class="row collapse"><div>Transmission</div><div>Automatic, Front Wheel</div></div>
  <p>Motive Power: Petrol Fuel economy of 7.8L per 100km</p>
  <img src="../../Motorcentral/VehicleData/demo-1.jpg" alt="2019 Mazda 6 GSX">
  <img src="../../Motorcentral/VehicleData/demo-1-1.jpg" alt="2019 Mazda 6 GSX - Thumbnail">
</body></html>
"""


class ParsingTests(unittest.TestCase):
    def test_canonical_vehicle_url(self):
        actual = canonical_vehicle_url("/vehicle/2019-Mazda-6/13662?s=1")
        self.assertEqual(
            actual, "https://www.grandemotors.co.nz/vehicle/2019-Mazda-6/13662"
        )

    def test_listing_page_deduplicates_vehicle_links(self):
        html = """
        <a href='/vehicle/2019-Mazda-6/13662?s=1'>One</a>
        <a href='/vehicle/2019-Mazda-6/13662?s=1'>Duplicate</a>
        <a href='/vehicles?Page=20'>Last</a>
        """
        urls, max_page = parse_listing_page(html)
        self.assertEqual(len(urls), 1)
        self.assertEqual(max_page, 20)

    def test_multiword_make(self):
        year, make, model = parse_year_make_model(
            "https://www.grandemotors.co.nz/vehicle/2011-Mercedes-Benz-C200/13650",
            "2011 Mercedes-Benz C200 AMG Package",
        )
        self.assertEqual(year, 2011)
        self.assertEqual(make, "Mercedes-Benz")
        self.assertEqual(model, "C200")

    def test_vehicle_detail(self):
        vehicle = parse_vehicle_page(
            "https://www.grandemotors.co.nz/vehicle/2019-Mazda-6/13662",
            VEHICLE_HTML,
        )
        self.assertEqual(vehicle.stock_number, "13662")
        self.assertEqual(vehicle.price_nzd, 23500)
        self.assertEqual(vehicle.mileage_km, 100960)
        self.assertEqual(vehicle.make, "Mazda")
        self.assertEqual(vehicle.model, "6")
        self.assertEqual(vehicle.body_style, "SEDAN")
        self.assertEqual(vehicle.fuel_type, "GASOLINE")
        self.assertEqual(vehicle.drivetrain, "FWD")
        self.assertEqual(len(vehicle.images), 1)


if __name__ == "__main__":
    unittest.main()
