eslint:
	for fname in *.js ; do npx eslint $$fname | sed "s/:[0-9][0-9]//" | sed "s=^ *=$$fname: =" ; done
