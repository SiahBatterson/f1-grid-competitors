import fastf1
import pandas as pd
import os

from fastf1.core import Laps

# Cache location
CACHE_DIR = 'f1_cache'
os.makedirs(CACHE_DIR, exist_ok=True)

fastf1.Cache.enable_cache(CACHE_DIR)

# Copy of calculate_points
def calculate_points(year, gp_name):
    try:
        event = fastf1.get_event(year, gp_name)
        quali = event.get_session('Qualifying')
        race = event.get_session('Race')

        quali.load()
        race.load()

        q_results = quali.results
        r_results = race.results

        if q_results is None or r_results is None:
            return pd.DataFrame()

        df = pd.merge(
            q_results[['Abbreviation', 'Position']].rename(columns={'Position': 'position_quali'}),
            r_results[['Abbreviation', 'Position']].rename(columns={'Position': 'position_race'}),
            on='Abbreviation'
        )

        df['positions_gained'] = df['position_quali'] - df['position_race']
        df['positions_gained'] = df['positions_gained'].apply(lambda x: max(0, x))
        df['points_from_race'] = (21 - df['position_race']) * 1
        df['points_from_gain'] = df['positions_gained'] * 2
        df['points_from_quali'] = (21 - df['position_quali']) * 3
        df['total_points'] = df['points_from_race'] + df['points_from_gain'] + df['points_from_quali']

        df = df.rename(columns={
            'Abbreviation': 'Driver',
            'position_quali': 'Quali',
            'position_race': 'Race',
            'positions_gained': '+Pos',
            'total_points': 'Total Points'
        })

        df['Q/R/+O'] = df.apply(lambda row: f"{row['points_from_quali']}/{row['points_from_race']}/{row['points_from_gain']}", axis=1)
        return df[['Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points']]

    except Exception as e:
        print(f"Error processing {year} {gp_name}: {e}")
        return pd.DataFrame()


# Script to fetch and store results
years = [2024, 2025]
for year in years:
    output_file = os.path.join(CACHE_DIR, f'driver_ratings_{year}.csv')

    if os.path.exists(output_file):
        print(f"✅ Ratings for {year} already cached.")
        continue

    print(f"\n📅 Processing season {year}...")
    try:
        schedule = fastf1.get_event_schedule(year)
    except Exception as e:
        print(f"❌ Failed to load schedule for {year}: {e}")
        continue

    season_results = []

    for _, row in schedule.iterrows():
        event_name = row['EventName']
        print(f"➡️ {event_name}")
        df = calculate_points(year, event_name)
        if not df.empty:
            df['Race'] = event_name  # Rename column if needed to disambiguate
            df['Season'] = year
            season_results.append(df)

    if season_results:
        season_df = pd.concat(season_results, ignore_index=True)
        season_df.to_csv(output_file, index=False)
        print(f"✅ Cached {len(season_df)} rows to {output_file}")
    else:
        print(f"⚠️ No valid results for {year}")
