#!/usr/bin/awk -f
# Convert djlint blocks -> "file:line:col: message"
# Works with outputs like:
#   app/templates/device_log.html
#   H025 29:10 Tag seems...

# if line looks like --> path:number:offset change to file, line, cold, msg

# match lines like: H025 29:10 Message...
/^   --> (.*):([0-9]):([0-9])/ {
    printf "%s:%d:%d: %s\n", $1, $2, $3, "fixme"
}

/^   --> ([^:]*)/ {
    split($2, lc, ":"); path=lc[1]; line=lc[2]; col=lc[2]
    printf "%s:%s: error\n", path, line
}

# just print
/./ {
 print $0
}
