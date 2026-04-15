# PropertySorted Scraper

Scrapes property listings from [propertysorted.com](https://www.propertysorted.com) and saves them to a CSV.

## Output

`propertysorted.csv` with columns: Link, Bedrooms, Bathrooms, Area_m2, Price_per_meter, Address, City, Location_1, Location_2, Unit, Type and Rent_Sale.

## How it works

**Phase 1** — Opens a browser, navigates buy/rent pages, and collects all listing URLs.
**Phase 2** — Fetches each listing and extracts property details.
