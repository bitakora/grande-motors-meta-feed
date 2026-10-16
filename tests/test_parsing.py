import unittest
from bs4 import BeautifulSoup

from generate_feed import (
    canonical_vehicle_url,
    parse_listing_page,
    parse_price,
    parse_on_road_costs,
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
  <div class="price-container-content"><span class="price">$23,500</span></div>
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

    def test_poa_does_not_take_price_from_related_car(self):
        soup = BeautifulSoup('''
          <div class="price-container-content"><span class="price">POA</span></div>
          <div class="vehicle-info"><span class="price">$24,500</span></div>
          <meta property="og:description" content="Other offers from $24,500">
        ''', "html.parser")
        self.assertEqual(parse_price(soup), 0)

    def test_missing_primary_price_fails_closed(self):
        soup = BeautifulSoup('<span class="price">$24,500</span>', "html.parser")
        self.assertEqual(parse_price(soup), 0)

    def test_sale_price_ignores_old_price_and_keeps_orc_separate(self):
        soup = BeautifulSoup('''
          <div class="price-container-content">
            <span class="old-price">was $16,500</span>
            <span class="price"><span class="special"><span class="amount">
              $13,500<span class="on-road-costs"> plus $600 ORC</span>
            </span></span></span>
          </div>
        ''', "html.parser")
        self.assertEqual(parse_price(soup), 13500)
        self.assertEqual(parse_on_road_costs(soup), ("plus $600 ORC", 600))

    def test_orc_does_not_leak_from_related_car(self):
        soup = BeautifulSoup('''
          <div class="price-container-content"><span class="price">$23,500</span></div>
          <span class="price">$24,500<span class="on-road-costs"> plus $600 ORC</span></span>
        ''', "html.parser")
        self.assertEqual(parse_on_road_costs(soup), ("", None))

    def test_zero_price_is_not_replaced_by_recommendation(self):
        soup = BeautifulSoup('''
          <div class="price-container-content"><span class="price">$0</span></div>
          <span class="price">$24,500</span>
        ''', "html.parser")
        self.assertEqual(parse_price(soup), 0)

    def test_description_discloses_orc_and_transit_without_og_claims(self):
        html = VEHICLE_HTML.replace(
            '<span class="price">$23,500</span>',
            '<span class="price">$23,500<span class="on-road-costs"> plus $600 ORC</span></span>',
        ).replace('<h2>2019 Mazda 6 GSX</h2>', '<h2>2019 Mazda 6 GSX In Transit</h2>')
        vehicle = parse_vehicle_page(
            "https://www.grandemotors.co.nz/vehicle/2019-Mazda-6/13662", html
        )
        self.assertEqual(vehicle.price_nzd, 23500)
        self.assertEqual(vehicle.on_road_costs_nzd, 600)
        self.assertTrue(vehicle.in_transit)
        self.assertIn("Total including these on-road costs: NZ$24,100", vehicle.description)
        self.assertIn("advertised as in transit", vehicle.description)
        self.assertIn("100,960km", vehicle.description)
        self.assertNotIn("with safety technology", vehicle.description)


if __name__ == "__main__":
    unittest.main()
