UPDATE devlog
SET
    logtime = CAST(logtime AS INTEGER),
    duration = MAX(1, CAST(ROUND(duration) AS INTEGER))
WHERE typeof(logtime) <> 'integer'
   OR typeof(duration) <> 'integer';
