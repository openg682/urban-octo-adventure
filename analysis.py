import zipfile
import os
import pandas as pd

# Path to your zip file
zip_path = "round-1-island-data-bottle.zip"
extract_path = "unzipped_data"

# Unzip the file
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_path)

# List contents to find relevant data files
for root, dirs, files in os.walk(extract_path):
    for file in files:
        print(os.path.join(root, file))
# Let's say you found a file like 'prices.csv' after extracting
df = pd.read_csv("unzipped_data/day_1/prices.csv")  # update path as needed

# Filter for only the 3 commodities
commodities = ["RAINFLOWER_RESIN", "KELP", "SQUID_INK"]
df_filtered = df[df['product'].isin(commodities)]

# Calculate mid prices and fair values
df_filtered['mid_price'] = (df_filtered['bid'] + df_filtered['ask']) / 2
fair_values = df_filtered.groupby('product')['mid_price'].mean()

print(fair_values)
