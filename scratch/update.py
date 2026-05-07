content = open('db/queries.py', 'r', encoding='utf-8').read()
old_str = '''def upsert_status_event(payload: dict) -> dict:
    if _DEMO_MODE:'''
new_str = '''def upsert_status_event(payload: dict) -> dict:
    event_date = payload.get("event_date")
    if isinstance(event_date, datetime) and event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    payload["event_date"] = event_date

    if _DEMO_MODE:'''
if old_str in content:
    with open('db/queries.py', 'w', encoding='utf-8') as f:
        f.write(content.replace(old_str, new_str))
    print('Queries updated')
else:
    print('Failed queries - string not found')

content = open('ui/frontend.py', 'r', encoding='utf-8').read()
old_str = '''        for rec in _q("get_entity_records", ubid):
            event_date = rec.get("activity_date") or rec.get("registration_date") or datetime.now(timezone.utc)
            _q("upsert_status_event", {
                "ubid_id": ubid, "raw_record_id": rec.get("raw_record_id"),
                "event_type": rec.get("status_raw") or "FILING",
                "event_source": rec.get("department_code"), "event_date": event_date,
                "activity_weight": 1.0, "derived_status": None,
                "details": {"business_name": rec.get("business_name"), "source_record_id": str(rec.get("raw_record_id"))},
            })
            inserted += 1'''
new_str = '''        for rec in _q("get_entity_records", ubid):
            try:
                event_date = rec.get("activity_date") or rec.get("registration_date") or datetime.now(timezone.utc)
                _q("upsert_status_event", {
                    "ubid_id": ubid, "raw_record_id": rec.get("raw_record_id"),
                    "event_type": rec.get("status_raw") or "FILING",
                    "event_source": rec.get("department_code"), "event_date": event_date,
                    "activity_weight": 1.0, "derived_status": None,
                    "details": {"business_name": rec.get("business_name"), "source_record_id": str(rec.get("raw_record_id"))},
                })
                inserted += 1
            except Exception as e:
                print(f"Error syncing status event for {ubid}: {e}")'''

if old_str in content:
    with open('ui/frontend.py', 'w', encoding='utf-8') as f:
        f.write(content.replace(old_str, new_str))
    print('UI updated')
else:
    print('Failed UI - string not found')
