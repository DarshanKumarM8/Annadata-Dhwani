-- Allow the IVR language selector to persist English for existing databases.
ALTER TABLE districts
  DROP CONSTRAINT IF EXISTS districts_default_lang_check;
ALTER TABLE districts
  ADD CONSTRAINT districts_default_lang_check
  CHECK (default_lang IN ('kn', 'hi', 'mr', 'en'));

ALTER TABLE farmers
  DROP CONSTRAINT IF EXISTS farmers_lang_check;
ALTER TABLE farmers
  ADD CONSTRAINT farmers_lang_check
  CHECK (lang IN ('kn', 'hi', 'mr', 'en'));
