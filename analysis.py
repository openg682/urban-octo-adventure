import subprocess
import sys

# Function to install pandas if not installed
def install_pandas():
    try:
        import pandas as pd
        print("Pandas is already installed!")
    except ImportError:
        print("Pandas not found, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas"])

# Function to install numpy if not installed
def install_numpy():
    try:
        import numpy as np
        print("NumPy is already installed!")
    except ImportError:
        print("NumPy not found, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])

# Call the functions to ensure pandas and numpy are installed
install_pandas()
install_numpy()

print("\nEnsured pandas and numpy are installed.")

# You can now import and use pandas and numpy in your script
import pandas as pd
import numpy as np

df = pd.read_csv("unzipped_data/day_1/prices.csv")  # update path as needed

# Filter for only the 3 commodities
commodities = ["CROISSANT", "JAM", "DJEMBE"]
df_filtered = df[df['product'].isin(commodities)]

# Calculate mid prices and fair values
df_filtered['mid_price'] = (df_filtered['bid'] + df_filtered['ask']) / 2
fair_values = df_filtered.groupby('product')['mid_price'].mean()

print(fair_values)
