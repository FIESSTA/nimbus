create table requests(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rid varchar(36) UNIQUE NOT NULL,
    src_filename varchar(1024) NOT NULL,
    dst_filename varchar(1024) NOT NULL,
    group_id varchar(64) NOT NULL,
    group_count INTEGER NOT NULL,
    hostname varchar(1024) NOT NULL,
    port INTEGER NOT NULL DEFAULT 2893,
    state INTEGER DEFAULT 0,
    message TEXT,
    entry_time DATETIME,
    UNIQUE(group_id, hostname, port, dst_filename)
);
