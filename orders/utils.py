import requests

class AddressDistanceValidator:
    """Kiểm tra khu vực nội thành, lấy toạ độ, tính khoảng cách, và tính thời gian giao hang tối thiểu."""

    DISTRICT_WHITELIST = [
        "quận 1","quận 3","quận 4","quận 5","quận 6","quận 7","quận 8","quận 10",
        "quận 11","quận 12","phú nhuận","gò vấp",
        "bình thạnh","tân bình","tân phú"
    ]

    def __init__(self, shop_address, ors_api_key):
        self.shop_address = shop_address
        self.ors_api_key = ors_api_key

    def is_in_inner_city(self, address: str):
        addr = address.lower()
        return any(d in addr for d in self.DISTRICT_WHITELIST)

    def get_coords(self, address: str):
        url = "https://api.openrouteservice.org/geocode/search"
        params = {
            "api_key": self.ors_api_key,
            "text": address,
            "boundary.country": "VN",
            "size": 1,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            coords = data["features"][0]["geometry"]["coordinates"]
            return coords  # [lon, lat]
        except Exception:
            return None

    def get_distance_km(self, customer_address: str):
        # Lấy toạ độ shop và khách
        shop_coords = self.get_coords(self.shop_address)
        cust_coords = self.get_coords(customer_address)
        if not shop_coords or not cust_coords:
            return None
        # Tính khoảng cách bằng directions API
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {"Authorization": self.ors_api_key}
        data = {
            "coordinates": [shop_coords, cust_coords]
        }
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            meters = data["features"][0]["properties"]["segments"][0]["distance"]
            return meters / 1000
        except Exception:
            return None

    def get_min_receive_datetime(self, distance_km, now):
        from datetime import timedelta
        mins = 120
        if distance_km > 10:
            mins += int((distance_km - 10) // 5) * 30
        return now + timedelta(minutes=mins)