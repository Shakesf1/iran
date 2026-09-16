-- get_bab_el_mandeb_transits_new() uses PostGIS functions (ST_Intersects,
-- ST_MakeLine, ::geography, ...) for the strait-crossing geometry, so this
-- isn't optional. The postgis/postgis image ships the extension; this just
-- activates it, which also creates spatial_ref_sys that the dump expects.
CREATE EXTENSION IF NOT EXISTS postgis;
