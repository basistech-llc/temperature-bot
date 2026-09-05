NODE_BIN := ./node_modules/.bin

node_modules/.bin/eslint: package.json package-lock.json
	npm ci --no-audit --no-fund

eslint: node_modules/.bin/eslint
	for fname in *.js ; do $(NODE_BIN)/eslint --config eslint.config.mjs $$fname | sed "s/:[0-9][0-9]//" | sed "s=^ *=$$fname: =" ; done

.PHONY: eslint
