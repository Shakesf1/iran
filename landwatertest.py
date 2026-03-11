import geopandas as gpd
from shapely.geometry import Point

# load land polygons
land = gpd.read_file("./ne_10m_land/ne_10m_land.shp")

# AIS positions
lon = [56.172188, 56.859612]
lat = [24.991064, 24.991064]

# create GeoSeries of points
points = gpd.GeoSeries(
    [Point(x, y) for x, y in zip(lon, lat)],
    crs="EPSG:4326"
)

# project to metric CRS
land_m = land.to_crs(epsg=3857)
points_m = points.to_crs(epsg=3857)

# merge land polygons (faster spatial test)
land_geom = land_m.union_all()

# 200 m inland tolerance
land_buffer = land_geom.buffer(200)

labels = []

for p in points_m:
    if land_geom.contains(p):
        labels.append("bad")
    elif land_buffer.contains(p):
        labels.append("coastal_noise")
    else:
        labels.append("water")

print(labels)