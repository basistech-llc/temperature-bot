ALTER TABLE devices ADD COLUMN display_name TEXT;
ALTER TABLE devices ADD COLUMN device_type TEXT;
ALTER TABLE devices ADD COLUMN rules_enabled INTEGER NOT NULL DEFAULT 1;

UPDATE devices
SET device_type = 'ERV'
WHERE device_type IS NULL
  AND lower(device_name) LIKE 'erv%';

UPDATE devices
SET device_type = 'FCU'
WHERE device_type IS NULL
  AND ae200_device_id IS NOT NULL
  AND lower(device_name) NOT LIKE 'erv%';
