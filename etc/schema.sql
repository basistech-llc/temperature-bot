CREATE TABLE changelog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logtime INTEGER NOT NULL,
                    ipaddr TEXT NOT NULL,
                    unit INTEGER NOT NULL,
                    new_value TEXT,
                    agent TEXT,
                    comment TEXT
                );

CREATE TABLE sqlite_sequence(name,seq);

CREATE TABLE sensor_names (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE templog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    logtime INTEGER NOT NULL,
    sensor_id INTEGER NOT NULL,
    temp10x INTEGER,
    FOREIGN KEY (sensor_id) REFERENCES sensor_names (id)
);

CREATE INDEX idx_templog_logtime ON templog (logtime);
CREATE INDEX idx_templog_sensor_id ON templog (sensor_id);
