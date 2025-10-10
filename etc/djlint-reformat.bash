#!/usr/bin/awk -f
# Convert djlint blocks -> "file:line:col: message"
# Works with outputs like:
#   app/templates/device_log.html
#   H025 29:10 Tag seems...

# treat a bare path line as “current file”
/^[[:graph:]][[:graph:][:space:]\/._~-]*\.(html|htm|j2|jinja|njk|twig|mustache|hbs|gohtml)$/ {
  file=$0; next
}

# match lines like: H025 29:10 Message...
/^[A-Za-z][0-9]+[[:space:]]+[0-9]+:[0-9]+[[:space:]]/ {
  split($2, lc, ":"); line=lc[1]; col=lc[2]
  msg=$0; sub(/^[^ ]+ +[0-9]+:[0-9]+ +/, "", msg)
  if (file && line && col) printf "%s:%d:%d: %s\n", file, line, col, msg
}
