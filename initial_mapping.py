import osmnx as ox
import networkx as nx
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime
import pytz
import streamlit as st

# 1. SETTINGS
ox.settings.use_cache = True
ox.settings.requests_timeout = 300


# 2. Extracting the 'Walk' network for BCN
print("Scanning Barcelona...")
gpkg_path = "/Users/Rhys/Quiet_Routing_Engine/noise_data_2017.gpkg"
G = ox.graph_from_address("Arc de Triomf, Barcelona, Spain", dist=3000, network_type="walk")

#ox.save_graphml(G, filepath="barcelona_walk.graphml")

# 3. Unpack the edges - leaving nodes aside for now, as we are more interested in roads than intersections for this project.
_, edges = ox.graph_to_gdfs(G) #Roads (edges) into a GeoDataFrame.


#FETCHING TIME IN BARCELONA - HARDCODING LOCAL TIME TO AVOID ISSUES WITH TIMEZONE CONFIGURATION IN DIFFERENT ENVIRONMENTS. 
#FOR A MUlTICITY APPLICATION, THIS WOULD NEED TO BE CONFIGURED TO FETCH LOCAL TIME BASED ON THE CITY IN QUESTION.
def get_local_time():
    tz = pytz.timezone('Europe/Madrid')
    bcn_hour = datetime.now(tz).hour
    return bcn_hour
# Selecting Noise Column Based on time
def get_noise_column():
    hour = get_local_time()
    if 7 <= hour < 19: 
        col = 'TOTAL_D'
    elif 19 <= hour < 23:
        col = 'TOTAL_E'
    else: 
        col = 'TOTAL_N'
    print(f"Applying weighting for hour {[hour]}, using column {col}")
    return col

# -------------------- SLIDER FOR NOISE SENSITIVITY (k) --------------------
k_label = st.select_slider(       #Tuning parameter to adjust influence of noise on the overall cost. 
        'Walking preference',
        options=['Fastest', 'Balanced', 'Quiet', 'Serene'],
        value='Fastest' #Hardcoded starting point, with the slider in use this will change, however. 
    )
mapping = {
        'Fastest': 0.5,
        'Balanced': 1.5,
        'Quiet': 3,
        'Serene': 5
    }
k = mapping[k_label]



# --- PHASE 3: GeoPackage-based and time sensitive noise ratings ---
@st.cache_data
def apply_real_noise_weights(_edges, gpkg_path, k):     #Have put _edges so that it doesn't cache. 
    noise_gdf = gpd.read_file(gpkg_path, layer='2017_Tramer_Mapa_Estrategic_Soroll_BCN')  


    # CRS Alignment (Degrees vs Meters in different maps (OpenData BCN vs. OSMNX) need to be homogenised)
    noise_gdf = noise_gdf.to_crs(_edges.crs)
    bcn_crs = "EPSG:25831" # UTM Zone 31N, commonly used for Barcelona. RAN INTO DATA CONFIGURATION ERRORS AND NEED TO HOMOGENISE.
   
   
   # Spatial Join (Snapping closest noise data to the streets)
    edges_projected = _edges.to_crs(bcn_crs)
    noise_projected = noise_gdf.to_crs(bcn_crs)
    
    
    joined = gpd.sjoin_nearest(
        edges_projected, 
        noise_projected, 
        how="left", 
        distance_col="dist" 
    )

    joined = joined[~joined.index.duplicated(keep='first')] 
    
     # Converting column to floats - they're stored as strings in the GeoPackage. Added regex too to find upper bound of noise range.
    noise_values = pd.to_numeric(joined[get_noise_column()].str.extract("- (\d+)")[0], errors='coerce').fillna(75) # Assuming 75 dB for streets without noise data, which is a conservative estimate to avoid false positives.

    edges_projected['noise_values'] = noise_values
    noise_normalised = (noise_values - noise_values.min()) / (noise_values.max() - noise_values.min()) # Normalising values between 0 and 1. 
    
    return edges_projected['length'] * (noise_normalised) ** k # Using a power function because 75dB is twice as loud as 65 dB to a human.

edges['weighted_cost'] = apply_real_noise_weights(edges, gpkg_path, k) #Column of weighted costs 

#print(edges.sort_values('weighted_cost', ascending=False)[['highway', 'length', 'weighted_cost']].head())
#print(gpd.read_file(gpkg_path, layer='2017_Tramer_Mapa_Estrategic_Soroll_BCN'))


print(edges['weighted_cost'].isna().sum())
print(f"Total edges: {len(edges)}")

"""

# 6. ------------------------------------ Routing Comparison ------------------------------------

weights_dict = edges['weighted_cost'].to_dict() #Precautionary step to ensure weights are formatted such that they can be pushed back easily to graph.

nx.set_edge_attributes(G, weights_dict, 'weighted_cost') # Push scores back to the graph

start_point = ox.geocoder.geocode("Parc Joan Miró, Barcelona")
end_point = ox.geocoder.geocode("Sagrada Família, Barcelona")

orig = ox.distance.nearest_nodes(G, X=start_point[1], Y=start_point[0])
dest = ox.distance.nearest_nodes(G, X=end_point[1], Y=end_point[0])

print("Calculating routes...")
route_fast = ox.shortest_path(G, orig, dest, weight='length')
route_quiet = ox.shortest_path(G, orig, dest, weight='weighted_cost')

# CHECK LENGTHS BEFORE PLOTTING.
route_fast_edges = ox.routing.route_to_gdf(G, route_fast)
len_fast = route_fast_edges['length'].sum()
route_quiet_edges = ox.routing.route_to_gdf(G, route_quiet)
len_quiet = route_quiet_edges['length'].sum()

print(f"Fast Route: {len_fast:.2f} meters")
print(f"Quiet Route: {len_quiet:.2f} meters")

# 7. Visualize: Red = Fast, Green = Quiet
print("Plotting results...")
fig, ax = ox.plot_graph_routes(G, [route_fast, route_quiet], 
                               route_colors=['r', 'g'], 
                               route_linewidth=4, node_size=0)
plt.show()

print(f"k value: {k}")
"""
"""
INTERFACE 
#Folium 
import folium

# 1. Create the base map
m = folium.Map(location=[41.391, 2.180], zoom_start=16)

# 2. Add the Fast Route (Red)
cols = ['lat', 'lon'] # Get coordinates for the route
route_coords = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in route_fast]
folium.PolyLine(route_coords, color="red", weight=5, opacity=0.7, tooltip="Fastest").add_to(m)

# 3. Add the Quiet Route (Green)
quiet_coords = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in route_quiet]
folium.PolyLine(quiet_coords, color="green", weight=5, opacity=0.9, tooltip="Quietest").add_to(m)

# 4. Save as HTML
m.save("barcelona_demo.html")
print("Interactive map saved to 'barcelona_demo.html'. Open this file in your browser.") """
