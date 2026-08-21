-- Classify changelog values so generic audit consumers do not present every
-- new_value as a fan speed. Existing unclassified rows remain visible as
-- "legacy" because their blank comments do not reliably distinguish drive,
-- fan-speed, temperature, and mode changes. The former web controls wrote a
-- second, comment-free rules-suspension row for each command; an integer Unix
-- timestamp from a browser user agent uniquely identifies those duplicate rows.
ALTER TABLE changelog
ADD COLUMN action TEXT NOT NULL DEFAULT 'legacy';

UPDATE changelog
SET action = CASE
    WHEN comment LIKE 'Rules disabled%' OR comment = 'set via Disable-for control'
        OR comment = 'disabled timer expired'
        OR (
            COALESCE(comment, '') = ''
            AND agent LIKE 'Mozilla/%'
            AND TRIM(new_value) NOT GLOB '*[^0-9]*'
            AND CAST(new_value AS INTEGER) >= 1000000000
        ) THEN 'rules_suspension'
    WHEN comment LIKE 'master rules switch %' THEN 'rules_master'
    WHEN comment = 'set range' THEN 'set_range'
    WHEN comment LIKE 'calculated temp multiplier for source %'
        THEN 'temperature_source'
    WHEN comment LIKE 'action-rule failure:%' THEN 'action_rule_failure'
    ELSE 'legacy'
END;
