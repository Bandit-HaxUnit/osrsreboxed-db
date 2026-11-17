# Recorded shop interface titles

`shop-display-names.json` is source evidence for exact strings sent in OSRS
`shop_main_init` (1074), where a recorded title differs from the Wiki page key.
Each source names the transcript revision/recording, line and inventory gameval.
These are observations of the interface title, not changes to Wiki page identity,
stock, currency or NPC bindings.

The Wiki page `Auburn Pub` also uses `Auburn Pub` in its infobox; three recordings
send `The Auburn Pub`. The disambiguated Wiki page `The Pandemonium (pub)` has
infobox name `The Pandemonium`, matching the recorded title. Keep both page keys
unchanged for joins; export the recorded string separately as `display_name`.
Other pubs have no correction unless directly supported by a recording.

Regenerate offline from the checked-in raw shops, owners and NPC options:

```sh
python -c "from scripts.shops import shops_properties, shops_items; shops_properties.process(); shops_items.fetch(); shops_items.process()"
```

Run `test/test_shop_display_names.py` and `test/test_shops_database.py`, then repeat
generation and compare output bytes. Never edit the exports or copy them here.
Consumers must join by the stable page key and use `display_name` only for display.
