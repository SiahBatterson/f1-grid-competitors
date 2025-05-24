import fastf1
import pandas as pd

def calculate_points(year, gp_name):
    try:
        event = fastf1.get_event(year, gp_name)
        quali = event.get_session('Qualifying')
        race = event.get_session('Race')
        quali.load(telemetry=False, weather=False, laps=False)
        race.load(telemetry=False, weather=False, laps=False)

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
        df['points_from_race'] = 21 - df['position_race']
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
        print(f"⚠️ Error: {e}")
        return pd.DataFrame()
