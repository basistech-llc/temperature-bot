ALTER TABLE rooms
ADD COLUMN fcu_device_id INTEGER REFERENCES devices(device_id);

CREATE UNIQUE INDEX idx_rooms_fcu_device_id
ON rooms(fcu_device_id)
WHERE fcu_device_id IS NOT NULL;

-- Preserve an FCU's existing room when possible. If legacy data assigned
-- several FCUs to one room, the lowest device id keeps it and the others get
-- their own rooms below.
UPDATE rooms
SET fcu_device_id = (
    SELECT d.device_id
    FROM devices d
    WHERE d.room_id = rooms.room_id
      AND d.device_type = 'FCU'
    ORDER BY d.device_id
    LIMIT 1
)
WHERE fcu_device_id IS NULL;

-- Generate the first available display-name-based room for each FCU that does
-- not already own one. Candidate ranking handles both existing Name (N) rooms
-- and several FCUs with the same display name.
WITH RECURSIVE
unowned_fcus AS (
    SELECT
        d.device_id,
        COALESCE(NULLIF(TRIM(d.display_name), ''), d.device_name) AS base_name,
        ROW_NUMBER() OVER (
            PARTITION BY COALESCE(NULLIF(TRIM(d.display_name), ''), d.device_name)
            ORDER BY d.device_id
        ) AS base_rank
    FROM devices d
    WHERE d.device_type = 'FCU'
      AND NOT EXISTS (
          SELECT 1 FROM rooms r WHERE r.fcu_device_id = d.device_id
      )
),
candidate_numbers(suffix) AS (
    SELECT 1
    UNION ALL
    SELECT suffix + 1
    FROM candidate_numbers
    WHERE suffix <= (
        SELECT COUNT(*) FROM rooms
    ) + (
        SELECT COUNT(*) FROM devices WHERE device_type = 'FCU'
    )
),
available_names AS (
    SELECT
        f.device_id,
        f.base_name,
        f.base_rank,
        n.suffix,
        CASE
            WHEN n.suffix = 1 THEN f.base_name
            ELSE f.base_name || ' (' || n.suffix || ')'
        END AS candidate_name
    FROM unowned_fcus f
    CROSS JOIN candidate_numbers n
),
ranked_names AS (
    SELECT
        device_id,
        base_rank,
        candidate_name,
        ROW_NUMBER() OVER (
            PARTITION BY base_name, device_id
            ORDER BY suffix
        ) AS available_rank
    FROM available_names a
    WHERE NOT EXISTS (
        SELECT 1 FROM rooms r WHERE r.room_name = a.candidate_name
    )
)
INSERT INTO rooms (room_name, fcu_device_id)
SELECT candidate_name, device_id
FROM ranked_names
WHERE available_rank = base_rank;

UPDATE devices
SET room_id = (
    SELECT r.room_id
    FROM rooms r
    WHERE r.fcu_device_id = devices.device_id
)
WHERE device_type = 'FCU';

-- Room assignment starts clean for every non-FCU. New physical devices also
-- default to NULL and therefore appear in the virtual Unassigned group.
UPDATE devices
SET room_id = NULL
WHERE device_type IS NULL OR device_type <> 'FCU';

CREATE UNIQUE INDEX idx_devices_fcu_room_id
ON devices(room_id)
WHERE device_type = 'FCU' AND room_id IS NOT NULL;
