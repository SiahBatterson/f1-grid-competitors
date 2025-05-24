import fastf1

fastf1.Cache.enable_cache('f1_cache')

years = [2024, 2025]
session_types_to_try = ['Race', 'Qualifying', 'Sprint Qualifying', 'Sprint']

for year in years:
    print(f"\n📅 Loading sessions for {year}...")
    try:
        schedule = fastf1.get_event_schedule(year)
    except Exception as e:
        print(f"❌ Failed to load schedule for {year}: {e}")
        continue

    for _, row in schedule.iterrows():
        event_name = row['EventName']
        event_date = row['EventDate'].date()

        print(f"\n🧠 [{year}] Event: {event_name} ({event_date})")

        try:
            event = fastf1.get_event(year, event_name)
        except Exception as e:
            print(f"❌ Failed to get event data: {e}")
            continue

        session_loaded = False
        for session_type in session_types_to_try:
            try:
                session = event.get_session(session_type)
                session.load()
                print(f"✅ Loaded {session_type}")
                session_loaded = True
                break
            except Exception as e:
                print(f"↪️ Skipped {session_type}: {e}")
        
        if not session_loaded:
            print("⚠️ No valid session loaded for this event.")

print("\n✅ All load attempts complete.")
